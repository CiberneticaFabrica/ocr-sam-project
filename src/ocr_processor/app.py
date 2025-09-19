# src/ocr_processor/app.py
import json
import boto3
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from services.ocr_service import OCRService
from services.mistral_service import MistralService
from services.storage_service import StorageService
from services.tracking_service import TrackingService
from shared.config import Config
from shared.exceptions import OCRBaseException
from shared.utils import ResponseFormatter, Logger

# Setup logging
logger = Logger.setup_logger(__name__)
config = Config()

# Initialize services
ocr_service = OCRService()
mistral_service = MistralService()
storage_service = StorageService()
tracking_service = TrackingService()

def lambda_handler(event, context) -> Dict[str, Any]:
    """
    Main Lambda handler for OCR processing
    Refactored to be cleaner and more focused
    """
    try:
        logger.info(f"🚀 Starting OCR processing - Records: {len(event.get('Records', []))}")
        
        # Process SQS messages
        results = []
        for record in event.get('Records', []):
            result = process_sqs_message(record, context)
            results.append(result)
        
        # Return summary
        successful = len([r for r in results if r.get('success', False)])
        total = len(results)
        
        Logger.log_success(logger, f"OCR processing completed", {
            'successful': successful,
            'total': total,
            'success_rate': f"{successful/total*100:.1f}%" if total > 0 else "0%"
        })
        
        return ResponseFormatter.success_response({
            'processed': total,
            'successful': successful,
            'failed': total - successful,
            'results': results
        })
        
    except Exception as e:
        Logger.log_error(logger, f"Fatal error in OCR processor", {'error': str(e)})
        return ResponseFormatter.error_response(f"OCR processing failed: {str(e)}", 500)

def process_sqs_message(record: Dict[str, Any], context) -> Dict[str, Any]:
    """Process individual SQS message"""
    try:
        # Parse message
        message_body = json.loads(record['body'])
        job_id = message_body.get('job_id')
        batch_id = message_body.get('batch_id')
        
        Logger.log_processing_step(logger, f"Processing job {job_id}", {
            'batch_id': batch_id,
            'source': message_body.get('source', 'unknown')
        })
        
        # Update status to processing
        tracking_service.update_job_status(job_id, 'processing', 'Starting OCR extraction')
        
        # Determine processing type
        if 'oficio_data' in message_body:
            # Batch processing (from document_processor)
            return process_batch_oficio(message_body, context)
        else:
            # Individual processing (legacy support)
            return process_individual_job(job_id, context)
            
    except Exception as e:
        job_id = 'unknown'
        try:
            message_body = json.loads(record['body'])
            job_id = message_body.get('job_id', 'unknown')
            tracking_service.update_job_status(job_id, 'error', f'Processing error: {str(e)}')
        except:
            pass
        
        Logger.log_error(logger, f"Error processing SQS message", {
            'job_id': job_id,
            'error': str(e)
        })
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(e)
        }

def process_batch_oficio(message_data: Dict[str, Any], context) -> Dict[str, Any]:
    """Process oficio from batch (main flow)"""
    try:
        job_id = message_data['job_id']
        batch_id = message_data['batch_id']
        oficio_data = message_data['oficio_data']
        
        Logger.log_processing_step(logger, f"Processing batch oficio", {
            'job_id': job_id,
            'batch_id': batch_id
        })
        
        # Step 1: Download PDF from S3
        pdf_content = storage_service.download_oficio_pdf(oficio_data)
        
        # Step 2: Extract text using OCR
        Logger.log_processing_step(logger, f"Starting OCR extraction", {
            'job_id': job_id,
            'pdf_size_bytes': len(pdf_content)
        })
        
        ocr_result = ocr_service.extract_text_from_pdf(pdf_content)
        if not ocr_result.success:
            raise OCRBaseException(f"OCR failed: {ocr_result.error}")
        
        # Log OCR results for debugging
        Logger.log_processing_step(logger, f"OCR extraction completed", {
            'job_id': job_id,
            'text_length': len(ocr_result.text),
            'confidence': ocr_result.metadata.get('confidence', 'N/A'),
            'total_pages': ocr_result.metadata.get('total_pages', 'N/A'),
            'text_preview': ocr_result.text[:200] + '...' if len(ocr_result.text) > 200 else ocr_result.text
        })
        
        # Step 3: Process with Mistral AI
        ai_result = mistral_service.analyze_oficio_text(ocr_result.text, job_id)
        if not ai_result.success:
            raise OCRBaseException(f"AI analysis failed: {ai_result.error}")
        
        # Step 4: Format and store results
        formatted_result = format_ocr_result(ai_result.data, ocr_result.metadata)
        storage_service.save_ocr_result(job_id, formatted_result)
        
        # Step 5: Update tracking
        tracking_service.update_job_status(job_id, 'ocr_completed', 'OCR processing completed successfully')
        tracking_service.update_batch_progress(batch_id)
        
        # Step 6: Send to CRM queue if configured
        if config.CRM_QUEUE_URL:
            send_to_crm_queue(job_id, batch_id, message_data)
            Logger.log_processing_step(logger, f"Sent to CRM queue", {'job_id': job_id})
        else:
            tracking_service.update_job_status(job_id, 'completed', 'Processing completed')
        
        Logger.log_success(logger, f"Oficio processed successfully", {
            'job_id': job_id,
            'text_length': len(ocr_result.text),
            'confidence': ocr_result.metadata.get('confidence', 'N/A')
        })
        
        return {
            'success': True,
            'job_id': job_id,
            'batch_id': batch_id,
            'result': {
                'text_length': len(ocr_result.text),
                'confidence': ocr_result.metadata.get('confidence'),
                'fields_extracted': len(formatted_result.get('informacion_extraida', {}))
            }
        }
        
    except OCRBaseException as e:
        Logger.log_error(logger, f"OCR processing error", {
            'job_id': job_id,
            'error': str(e)
        })
        tracking_service.update_job_status(job_id, 'error', f'OCR error: {str(e)}')
        return {
            'success': False,
            'job_id': job_id,
            'error': str(e)
        }
    
    except Exception as e:
        Logger.log_error(logger, f"Unexpected error in batch processing", {
            'job_id': job_id,
            'error': str(e)
        })
        tracking_service.update_job_status(job_id, 'error', f'Processing error: {str(e)}')
        return {
            'success': False,
            'job_id': job_id,
            'error': str(e)
        }

def process_individual_job(job_id: str, context) -> Dict[str, Any]:
    """Process individual job (legacy support)"""
    try:
        Logger.log_processing_step(logger, f"Processing individual job", {'job_id': job_id})
        
        # Check remaining time
        remaining_time = context.get_remaining_time_in_millis() / 1000
        if remaining_time < 60:  # Need at least 1 minute
            raise OCRBaseException(f"Insufficient time remaining: {remaining_time:.1f}s")
        
        # Load job data
        job_data = tracking_service.get_job_data(job_id)
        if not job_data:
            raise OCRBaseException(f"Job data not found for {job_id}")
        
        # Process similar to batch, but with different data structure
        pdf_content = storage_service.download_job_pdf(job_id)
        
        ocr_result = ocr_service.extract_text_from_pdf(pdf_content)
        if not ocr_result.success:
            raise OCRBaseException(f"OCR failed: {ocr_result.error}")
        
        ai_result = mistral_service.analyze_oficio_text(ocr_result.text, job_id)
        if not ai_result.success:
            raise OCRBaseException(f"AI analysis failed: {ai_result.error}")
        
        formatted_result = format_ocr_result(ai_result.data, ocr_result.metadata)
        storage_service.save_ocr_result(job_id, formatted_result)
        
        tracking_service.update_job_status(job_id, 'completed', 'Individual job completed')
        
        Logger.log_success(logger, f"Individual job processed", {'job_id': job_id})
        
        return {
            'success': True,
            'job_id': job_id,
            'processing_type': 'individual'
        }
        
    except Exception as e:
        Logger.log_error(logger, f"Error in individual job processing", {
            'job_id': job_id,
            'error': str(e)
        })
        tracking_service.update_job_status(job_id, 'error', f'Individual job error: {str(e)}')
        return {
            'success': False,
            'job_id': job_id,
            'error': str(e)
        }

def format_ocr_result(ai_data: Dict[str, Any], ocr_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Format OCR result for storage and CRM integration"""
    try:
        # Base structure
        formatted_result = {
            'palabras_clave_encontradas': ai_data.get('palabras_clave_encontradas', []),
            'tipo_oficio_detectado': ai_data.get('tipo_oficio_detectado', 'No identificado'),
            'nivel_confianza': ai_data.get('nivel_confianza', 'N/A'),
            'ocr_metadata': ocr_metadata,
            'processed_at': datetime.utcnow().isoformat(),
            'informacion_extraida': {}
        }
        
        # Extract and clean information
        info_extraida = ai_data.get('informacion_extraida', {})
        field_mapping = {
            'numero_oficio': 'numero_oficio',
            'autoridad': 'autoridad', 
            'fecha_emision': 'fecha_emision',
            'fecha_recibido': 'fecha_recibido',
            'oficiado_cliente': 'oficiado_cliente',
            'numero_identificacion': 'numero_identificacion',
            'expediente': 'expediente',
            'fecha_auto': 'fecha_auto',
            'numero_auto': 'numero_auto',
            'monto': 'monto',
            'sucursal_recibido': 'sucursal_recibido',
            'carpeta': 'carpeta',
            'vencimiento': 'vencimiento',
            'personas': 'personas'
        }
        
        # Process each field
        from shared.utils import TextCleaner
        for ai_field, result_field in field_mapping.items():
            value = info_extraida.get(ai_field)
            
            if value is not None:
                if ai_field == 'monto':
                    # Handle currency
                    cleaned_value = TextCleaner.extract_currency(str(value))
                    formatted_result['informacion_extraida'][result_field] = cleaned_value
                elif ai_field in ['fecha_emision', 'fecha_recibido', 'fecha_auto', 'vencimiento']:
                    # Handle dates
                    cleaned_value = TextCleaner.extract_date(str(value))
                    formatted_result['informacion_extraida'][result_field] = cleaned_value or str(value)
                elif ai_field == 'personas':
                    # Handle persons list
                    formatted_result['informacion_extraida'][result_field] = format_persons_list(value)
                else:
                    # Handle text fields
                    formatted_result['informacion_extraida'][result_field] = TextCleaner.clean_value(value)
        
        return formatted_result
        
    except Exception as e:
        Logger.log_error(logger, f"Error formatting OCR result", {'error': str(e)})
        # Return basic structure if formatting fails
        return {
            'error': f'Formatting error: {str(e)}',
            'raw_ai_data': ai_data,
            'processed_at': datetime.utcnow().isoformat()
        }

def format_persons_list(persons_data) -> List[Dict[str, Any]]:
    """Format persons list for CRM integration"""
    try:
        if not persons_data:
            return []
        
        if isinstance(persons_data, str):
            # Parse string representation
            import ast
            try:
                persons_data = ast.literal_eval(persons_data)
            except:
                return [{'nombre': persons_data, 'tipo': 'Persona mencionada'}]
        
        if isinstance(persons_data, list):
            formatted_persons = []
            for person in persons_data:
                if isinstance(person, dict):
                    formatted_persons.append({
                        'nombre': TextCleaner.clean_value(person.get('nombre', '')),
                        'tipo': person.get('tipo', 'Persona'),
                        'identificacion': TextCleaner.clean_value(person.get('identificacion', '')),
                        'rol': person.get('rol', 'No especificado')
                    })
                else:
                    formatted_persons.append({
                        'nombre': TextCleaner.clean_value(str(person)),
                        'tipo': 'Persona',
                        'identificacion': '',
                        'rol': 'No especificado'
                    })
            return formatted_persons
        
        return []
        
    except Exception as e:
        Logger.log_error(logger, f"Error formatting persons list", {'error': str(e)})
        return []

def send_to_crm_queue(job_id: str, batch_id: str, message_data: Dict[str, Any]) -> None:
    """Send processed result to CRM integration queue"""
    try:
        sqs_client = boto3.client('sqs')
        
        crm_message = {
            'job_id': job_id,
            'batch_id': batch_id,
            'source': message_data.get('source', 's3_direct'),
            'timestamp': datetime.utcnow().isoformat(),
            'processing_completed_at': datetime.utcnow().isoformat()
        }
        
        sqs_client.send_message(
            QueueUrl=config.CRM_QUEUE_URL,
            MessageBody=json.dumps(crm_message, ensure_ascii=False),
            MessageAttributes={
                'JobId': {
                    'StringValue': job_id,
                    'DataType': 'String'
                },
                'BatchId': {
                    'StringValue': batch_id,
                    'DataType': 'String'
                }
            }
        )
        
    except Exception as e:
        Logger.log_error(logger, f"Error sending to CRM queue", {
            'job_id': job_id,
            'error': str(e)
        })