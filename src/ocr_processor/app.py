# src/ocr_processor/app.py - VERSIÓN INTEGRADA MEJORADA

import json
import boto3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

# Importar servicios mejorados
from services.ocr_service import OCRService, OCRResult  # Original OCR service
from services.storage_service import StorageService
from services.tracking_service import TrackingService
from shared.config import Config
from shared.exceptions import OCRBaseException
from shared.utils import ResponseFormatter, Logger
from services.post_ocr_validator import PostOCRValidator

# Setup logging
logger = Logger.setup_logger(__name__)
config = Config()

# Inicializar servicios
logger.info("📄 Using Enhanced OCR (Mistral AI)")
ocr_service = OCRService()  # Use enhanced Mistral OCR service

storage_service = StorageService()
tracking_service = TrackingService()

# CloudWatch para métricas
cloudwatch = boto3.client('cloudwatch')
sqs_client = boto3.client('sqs')

def put_custom_metric(metric_name: str, value: float, unit: str = 'Count', 
                     dimensions: Dict[str, str] = None):
    """Enviar métrica personalizada a CloudWatch"""
    try:
        metric_data = {
            'MetricName': metric_name,
            'Value': value,
            'Unit': unit,
            'Timestamp': datetime.utcnow()
        }
        
        if dimensions:
            metric_data['Dimensions'] = [{'Name': k, 'Value': v} for k, v in dimensions.items()]
        
        cloudwatch.put_metric_data(
            Namespace='OCR/Processing',
            MetricData=[metric_data]
        )
    except Exception as e:
        logger.warning(f"Failed to send metric {metric_name}: {str(e)}")

def lambda_handler(event, context) -> Dict[str, Any]:
    """
    Main Lambda handler for enhanced OCR processing
    """
    try:
        logger.info(f"🚀 Enhanced OCR processing started - Records: {len(event.get('Records', []))}")
        
        # Process SQS messages
        results = []
        for record in event.get('Records', []):
            result = process_sqs_message(record, context)
            results.append(result)
        
        # Return summary
        successful = len([r for r in results if r.get('success', False)])
        total = len(results)
        
        Logger.log_success(logger, f"Enhanced OCR processing completed", {
            'successful': successful,
            'total': total,
            'success_rate': f"{successful/total*100:.1f}%" if total > 0 else "0%"
        })
        
        # Send batch metrics
        put_custom_metric('BatchProcessed', total)
        put_custom_metric('BatchSuccessful', successful)
        put_custom_metric('BatchFailed', total - successful)
        
        return ResponseFormatter.success_response({
            'processed': total,
            'successful': successful,
            'failed': total - successful,
            'results': results,
            'enhanced_processing': True
        })
        
    except Exception as e:
        Logger.log_error(logger, f"Fatal error in enhanced OCR processor", {'error': str(e)})
        return ResponseFormatter.error_response(f"Enhanced OCR processing failed: {str(e)}", 500)

def process_sqs_message(record: Dict[str, Any], context) -> Dict[str, Any]:
    """Process individual SQS message with enhanced OCR"""
    job_id = 'unknown'
    
    try:
        # Parse message
        message_body = json.loads(record['body'])
        job_id = message_body.get('job_id')
        batch_id = message_body.get('batch_id')
        source = message_body.get('source', 'unknown')
        
        Logger.log_processing_step(logger, f"Processing enhanced job {job_id}", {
            'batch_id': batch_id,
            'source': source
        })
        
        # Update status to processing
        tracking_service.update_job_status(job_id, 'ocr_processing', 
                                         'Starting enhanced OCR extraction')
        
        # Process according to source type
        if 'oficio_data' in message_body:
            return process_batch_oficio_enhanced(message_body, context)
        else:
            return process_individual_job_enhanced(job_id, context)
            
    except Exception as e:
        try:
            tracking_service.update_job_status(job_id, 'error', f'Enhanced processing error: {str(e)}')
        except:
            pass
        
        Logger.log_error(logger, f"Error processing enhanced SQS message", {
            'job_id': job_id,
            'error': str(e)
        })
        
        put_custom_metric('ProcessingError', 1, dimensions={'JobId': job_id})
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(e),
            'enhanced_processing': True
        }

def process_batch_oficio_enhanced(message_data: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Process oficio from batch using enhanced OCR service
    """
    job_id = message_data['job_id']
    batch_id = message_data['batch_id']
    
    try:
        Logger.log_processing_step(logger, f"Processing enhanced batch oficio", {
            'job_id': job_id,
            'batch_id': batch_id
        })
        
        # Check remaining execution time
        remaining_time = context.get_remaining_time_in_millis() / 1000
        if remaining_time < 120:  # Need at least 2 minutes
            raise OCRBaseException(f"Insufficient time remaining: {remaining_time:.1f}s")
        
        # Step 1: Download PDF from S3
        oficio_data = message_data['oficio_data']
        pdf_content = storage_service.download_oficio_pdf(oficio_data)
        
        logger.info(f"📥 Downloaded PDF: {len(pdf_content)} bytes")
        
        # Step 2: Enhanced OCR extraction
        ocr_result = ocr_service.extract_text_from_pdf(
            pdf_content, 
            job_id=job_id, 
            document_type='legal_document'
        )
        
        if not ocr_result.success:
            raise OCRBaseException(f"Enhanced OCR failed: {ocr_result.error}")
        
        # Step 2.5: Post-OCR validation and enrichment
        validator = PostOCRValidator()
        ocr_result_enriched = validator.enrich_ocr_result(ocr_result)
        
        # Step 3: Format and validate results
        formatted_result = format_enhanced_result(ocr_result_enriched, message_data)
        
        # Step 4: Store enhanced results
        storage_service.save_ocr_result(job_id, formatted_result)
        
        # Step 5: Update tracking with detailed info
        tracking_service.update_job_status(
            job_id, 
            'ocr_completed', 
            f'Enhanced OCR completed - Confidence: {ocr_result.confidence}'
        )
        
        # Step 6: Update batch progress
        tracking_service.update_batch_progress(batch_id)
        
        # Step 7: Send to CRM queue if configured
        if config.CRM_QUEUE_URL:
            send_to_crm_queue_enhanced(job_id, batch_id, message_data, formatted_result)
            Logger.log_processing_step(logger, f"Sent enhanced data to CRM queue", {'job_id': job_id})
        else:
            tracking_service.update_job_status(job_id, 'completed', 'Enhanced processing completed')
        
        # Detailed logging and metrics
        processing_stats = calculate_processing_stats(ocr_result, formatted_result)
        
        Logger.log_success(logger, f"Enhanced oficio processed successfully", {
            'job_id': job_id,
            **processing_stats
        })
        
        # Send detailed metrics
        send_processing_metrics(processing_stats, job_id)
        
        return {
            'success': True,
            'job_id': job_id,
            'batch_id': batch_id,
            'enhanced_processing': True,
            'result': processing_stats
        }
        
    except OCRBaseException as e:
        Logger.log_error(logger, f"Enhanced OCR processing error", {
            'job_id': job_id,
            'error': str(e)
        })
        tracking_service.update_job_status(job_id, 'error', f'Enhanced OCR error: {str(e)}')
        put_custom_metric('OCRError', 1, dimensions={'JobId': job_id})
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(e),
            'enhanced_processing': True
        }
    
    except Exception as e:
        Logger.log_error(logger, f"Unexpected error in enhanced batch processing", {
            'job_id': job_id,
            'error': str(e),
            'error_type': type(e).__name__
        })
        tracking_service.update_job_status(job_id, 'error', f'Processing error: {str(e)}')
        put_custom_metric('UnexpectedError', 1, dimensions={'JobId': job_id})
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(e),
            'enhanced_processing': True
        }

def process_individual_job_enhanced(job_id: str, context) -> Dict[str, Any]:
    """Process individual job with enhanced OCR"""
    try:
        Logger.log_processing_step(logger, f"Processing individual enhanced job", {'job_id': job_id})
        
        # Check remaining time
        remaining_time = context.get_remaining_time_in_millis() / 1000
        if remaining_time < 120:
            raise OCRBaseException(f"Insufficient time remaining: {remaining_time:.1f}s")
        
        # Load job data
        job_data = tracking_service.get_job_data(job_id)
        if not job_data:
            raise OCRBaseException(f"Job data not found for {job_id}")
        
        # Download PDF
        pdf_content = storage_service.download_job_pdf(job_id)
        
        # Enhanced OCR processing
        ocr_result = ocr_service.extract_text_from_pdf(
            pdf_content, 
            job_id=job_id, 
            document_type='legal_document'
        )
        
        if not ocr_result.success:
            raise OCRBaseException(f"Enhanced OCR failed: {ocr_result.error}")
        
        # Post-OCR validation and enrichment
        validator = PostOCRValidator()
        ocr_result_enriched = validator.enrich_ocr_result(ocr_result)
        
        # Format and store results
        formatted_result = format_enhanced_result(ocr_result_enriched, {'job_id': job_id})
        storage_service.save_ocr_result(job_id, formatted_result)
        
        # Update tracking
        tracking_service.update_job_status(
            job_id, 
            'completed', 
            f'Individual enhanced processing completed - Confidence: {ocr_result.confidence}'
        )
        
        # Calculate and log stats
        processing_stats = calculate_processing_stats(ocr_result, formatted_result)
        
        Logger.log_success(logger, f"Individual enhanced job processed", {
            'job_id': job_id,
            **processing_stats
        })
        
        # Send metrics
        send_processing_metrics(processing_stats, job_id)
        
        return {
            'success': True,
            'job_id': job_id,
            'processing_type': 'individual_enhanced',
            'result': processing_stats
        }
        
    except Exception as e:
        Logger.log_error(logger, f"Error in individual enhanced job processing", {
            'job_id': job_id,
            'error': str(e)
        })
        tracking_service.update_job_status(job_id, 'error', f'Individual enhanced job error: {str(e)}')
        put_custom_metric('IndividualJobError', 1, dimensions={'JobId': job_id})
        
        return {
            'success': False,
            'job_id': job_id,
            'error': str(e),
            'processing_type': 'individual_enhanced'
        }

def format_enhanced_result(ocr_result: OCRResult, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format enhanced OCR result maintaining compatibility with existing CRM structure
    """
    try:
        # Base structure
        formatted_result = {
            'success': True,
            'processed_at': datetime.utcnow().isoformat(),
            'job_id': ocr_result.metadata.get('job_id'),
            'processing_time': ocr_result.processing_time,
            'extraction_method': 'enhanced_mistral_ocr_v2',
            'confidence': ocr_result.confidence,
            'enhanced_processing': True
        }
        
        # Add structured data if available
        if ocr_result.structured_data:
            # Ensure structured_data is a dictionary
            if isinstance(ocr_result.structured_data, str):
                try:
                    structured_data = json.loads(ocr_result.structured_data)
                    logger.info(f"📄 Parsed structured_data from JSON string")
                except json.JSONDecodeError:
                    logger.warning(f"⚠️ Could not parse structured_data as JSON, using as text")
                    structured_data = {'texto_completo': ocr_result.structured_data}
            elif isinstance(ocr_result.structured_data, dict):
                structured_data = ocr_result.structured_data
            else:
                logger.warning(f"⚠️ Unexpected structured_data type: {type(ocr_result.structured_data)}")
                structured_data = {'texto_completo': str(ocr_result.structured_data)}
            
            # Classification information
            if 'clasificacion' in structured_data and isinstance(structured_data['clasificacion'], dict):
                classification = structured_data['clasificacion']
                formatted_result.update({
                    'tipo_oficio_detectado': classification.get('tipo_oficio', 'No identificado'),
                    'nivel_confianza': classification.get('confianza', 'medio'),
                    'clasificacion': classification
                })
            
            # General information
            if 'informacion_general' in structured_data and isinstance(structured_data['informacion_general'], dict):
                info_general = structured_data['informacion_general']
                formatted_result['informacion_extraida'] = {
                    'numero_oficio': clean_value(info_general.get('numero_oficio')),
                    'autoridad': clean_value(info_general.get('autoridad_emisora')),
                    'fecha_emision': parse_date_value(info_general.get('fecha')),
                    'destinatario': clean_value(info_general.get('destinatario')),
                    'asunto': clean_value(info_general.get('asunto'))
                }
            
            # 🔧 FIX CRÍTICO: Persons list - buscar en AMBOS campos
            personas_list = []
            monto_total = 0.0
            
            # Prioridad 1: lista_clientes (campo del OCR Mistral)
            if 'lista_clientes' in structured_data:
                lista_clientes = structured_data['lista_clientes']
                if isinstance(lista_clientes, list) and lista_clientes:
                    personas_list = lista_clientes
                    logger.info(f"✅ Found {len(personas_list)} persons in lista_clientes")
            
            # Prioridad 2: lista_personas (campo alternativo)
            elif 'lista_personas' in structured_data:
                lista_personas = structured_data['lista_personas']
                if isinstance(lista_personas, dict) and 'listado' in lista_personas:
                    personas_list = lista_personas['listado']
                    logger.info(f"✅ Found {len(personas_list)} persons in lista_personas.listado")
                elif isinstance(lista_personas, list):
                    personas_list = lista_personas
                    logger.info(f"✅ Found {len(personas_list)} persons in lista_personas")
            
            # Formatear personas para CRM si se encontraron
            if personas_list:
                formatted_personas = format_personas_for_crm(personas_list)
                monto_total = sum(p.get('monto_numerico', 0) for p in formatted_personas)
                
                formatted_result['lista_personas'] = {
                    'listado': formatted_personas,
                    'monto_total': monto_total
                }
                
                logger.info(f"✅ Formatted {len(formatted_personas)} persons for CRM")
                logger.info(f"💰 Total amount: {monto_total}")
            else:
                logger.warning(f"⚠️ No persons found in structured_data")
                formatted_result['lista_personas'] = {'listado': [], 'monto_total': 0}
            
            # Keywords found
            if 'palabras_clave_encontradas' in structured_data:
                formatted_result['palabras_clave_encontradas'] = structured_data['palabras_clave_encontradas']
            
            # Complete text
            formatted_result['texto_completo'] = structured_data.get('texto_completo', ocr_result.text)
            
            # Raw structured data for reference
            formatted_result['structured_data_raw'] = structured_data
        
        else:
            # Fallback for no structured data
            formatted_result.update({
                'tipo_oficio_detectado': 'Documento procesado',
                'nivel_confianza': ocr_result.confidence,
                'palabras_clave_encontradas': [],
                'informacion_extraida': extract_basic_info_from_text(ocr_result.text),
                'texto_completo': ocr_result.text,
                'lista_personas': {'listado': [], 'monto_total': 0}
            })
        
        # Enhanced metadata
        formatted_result['ocr_metadata'] = {
            'confidence': ocr_result.confidence,
            'text_length': len(ocr_result.text),
            'document_type': ocr_result.metadata.get('document_type', 'legal_document'),
            'has_structured_data': bool(ocr_result.structured_data),
            'extraction_method': 'enhanced_mistral_ocr_v2',
            'api_model': ocr_result.metadata.get('api_model', 'mistral-ocr-latest'),
            'processing_version': '2.1',
            'persons_found': len(formatted_result.get('lista_personas', {}).get('listado', []))
        }
        
        return formatted_result
        
    except Exception as e:
        Logger.log_error(logger, f"Error formatting enhanced OCR result", {'error': str(e)})
        # Return basic structure if formatting fails
        return {
            'success': True,
            'error': f'Formatting error: {str(e)}',
            'texto_completo': ocr_result.text,
            'processed_at': datetime.utcnow().isoformat(),
            'extraction_method': 'enhanced_mistral_ocr_v2_fallback',
            'enhanced_processing': True,
            'lista_personas': {'listado': [], 'monto_total': 0}
        }

def format_personas_for_crm(personas_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format personas list for CRM integration"""
    try:
        formatted_personas = []
        
        for i, persona in enumerate(personas_list):
            if not persona or not isinstance(persona, dict):
                continue
                
            # Extract and split full name
            nombre_completo = clean_value(persona.get('nombre_completo', ''))
            if not nombre_completo:
                continue
                
            nombres = nombre_completo.split()
            
            # 🔧 FIX: Obtener identificación de AMBOS campos posibles
            identificacion = (
                clean_value(persona.get('numero_identificacion', '')) or 
                clean_value(persona.get('identificacion', ''))
            )
            
            # Parse amount
            monto_str = clean_value(persona.get('monto', '0'))
            monto_numerico = persona.get('monto_numerico', 0.0)
            
            if monto_numerico == 0.0 and monto_str:
                try:
                    monto_clean = monto_str.replace('B/.', '').replace(',', '').strip()
                    monto_numerico = float(monto_clean) if monto_clean else 0.0
                except:
                    monto_numerico = 0.0
            
            formatted_person = {
                'secuencia': i + 1,
                'nombre_completo': nombre_completo,
                'nombre': nombres[0] if nombres else '',
                'apellido_paterno': nombres[1] if len(nombres) > 1 else '',
                'apellido_materno': nombres[2] if len(nombres) > 2 else '',
                'nombre_segundo': ' '.join(nombres[3:]) if len(nombres) > 3 else '',
                'identificacion': identificacion,
                'numero_identificacion': identificacion,  # Campo duplicado para compatibilidad
                'numero_cuenta': clean_value(persona.get('numero_cuenta', '')),
                'numero_ruc': clean_value(persona.get('numero_ruc', '')),
                'monto': monto_str,
                'monto_numerico': monto_numerico,
                'expediente': clean_value(persona.get('expediente', '')),
                'observaciones': clean_value(persona.get('observaciones', f'Persona extraída por OCR v2 - Secuencia: {i + 1}'))
            }
            
            # Log para debugging
            logger.info(f"👤 Formatted person {i+1}: {nombre_completo} (ID: {identificacion}, Monto: {monto_numerico})")
            
            formatted_personas.append(formatted_person)
        
        logger.info(f"✅ Successfully formatted {len(formatted_personas)} persons for CRM")
        return formatted_personas
        
    except Exception as e:
        Logger.log_error(logger, f"Error formatting personas list", {'error': str(e)})
        return []

def clean_value(value: Any) -> str:
    """Clean and normalize any value"""
    if value is None or value == 'null':
        return ''
    
    if isinstance(value, (int, float)):
        return str(value)
    
    if isinstance(value, str):
        return value.strip()
    
    return str(value).strip()

def parse_date_value(date_str: str) -> str:
    """Parse date value for CRM compatibility"""
    if not date_str or date_str.strip() in ['', 'null', 'None']:
        return ''
    
    # Add your date parsing logic here
    return date_str

def extract_basic_info_from_text(text: str) -> Dict[str, Any]:
    """Extract basic information from text when structured data is not available"""
    try:
        import re
        
        info = {}
        
        # Search for oficio number
        oficio_pattern = r'(?:oficio|no\.?)\s*:?\s*([A-Za-z0-9\-]+)'
        oficio_match = re.search(oficio_pattern, text, re.IGNORECASE)
        if oficio_match:
            info['numero_oficio'] = oficio_match.group(1)
        
        # Search for authority
        autoridad_patterns = [
            r'(juzgado [^\.]+)',
            r'(tribunal [^\.]+)',
            r'(ministerio [^\.]+)'
        ]
        for pattern in autoridad_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['autoridad'] = match.group(1)
                break
        
        # Search for dates
        date_pattern = r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})'
        date_matches = re.findall(date_pattern, text)
        if date_matches:
            info['fecha_emision'] = date_matches[0]
        
        return info
        
    except Exception as e:
        Logger.log_error(logger, f"Error extracting basic info from text", {'error': str(e)})
        return {}

def calculate_processing_stats(ocr_result: OCRResult, formatted_result: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate processing statistics with detailed content analysis"""
    
    # Base stats
    stats = {
        'text_length': len(ocr_result.text),
        'processing_time': ocr_result.processing_time,
        'confidence': ocr_result.confidence,
        'has_structured_data': bool(ocr_result.structured_data),
        'structured_fields_count': len(ocr_result.structured_data) if ocr_result.structured_data else 0,
        'persons_count': len(formatted_result.get('lista_personas', {}).get('listado', [])),
        'total_amount': formatted_result.get('lista_personas', {}).get('monto_total', 0),
        'classification': formatted_result.get('clasificacion', {}),
        'extraction_method': 'enhanced_mistral_ocr_v2'
    }
    
    # 🔍 LOGGING DETALLADO DE CONTENIDO EXTRAÍDO
    job_id = ocr_result.metadata.get('job_id', 'unknown')
    
    # Text preview (mostrar más caracteres)
    text_preview = ocr_result.text[:500] + '...' if len(ocr_result.text) > 500 else ocr_result.text
    Logger.log_success(logger, f"📄 OCR Text Preview", {
        'job_id': job_id,
        'text_preview': text_preview,
        'full_text_length': len(ocr_result.text)
    })
    
    # Texto completo completo (sin truncar)
    Logger.log_success(logger, f"📝 OCR Complete Text", {
        'job_id': job_id,
        'complete_text': ocr_result.text,
        'text_length': len(ocr_result.text)
    })
    
    # Detailed structured data analysis
    if ocr_result.structured_data and isinstance(ocr_result.structured_data, dict):
        structured_data = ocr_result.structured_data
        
        # Classification details
        if 'clasificacion' in structured_data and isinstance(structured_data['clasificacion'], dict):
            classification = structured_data['clasificacion']
            Logger.log_success(logger, f"🏷️ Document Classification Details", {
                'job_id': job_id,
                'tipo_oficio': classification.get('tipo_oficio', 'N/A'),
                'tramite': classification.get('tramite', 'N/A'),
                'departamento': classification.get('departamento', 'N/A'),
                'confianza': classification.get('confianza', 'N/A'),
                'id': classification.get('id', 'N/A')
            })
        
        # General information details
        if 'informacion_general' in structured_data and isinstance(structured_data['informacion_general'], dict):
            info_general = structured_data['informacion_general']
            Logger.log_success(logger, f"📋 General Information Details", {
                'job_id': job_id,
                'numero_oficio': info_general.get('numero_oficio', 'N/A'),
                'autoridad': info_general.get('autoridad_emisora', 'N/A'),
                'fecha': info_general.get('fecha', 'N/A'),
                'destinatario': info_general.get('destinatario', 'N/A'),
                'asunto': info_general.get('asunto', 'N/A')[:100] + '...' if info_general.get('asunto', '') else 'N/A'
            })
        
        # Persons details
        if 'lista_clientes' in structured_data and isinstance(structured_data['lista_clientes'], list):
            personas = structured_data['lista_clientes']
            Logger.log_success(logger, f"👥 Persons Found Details", {
                'job_id': job_id,
                'persons_count': len(personas),
                'persons_preview': [
                    {
                        'nombre': p.get('nombre_completo', 'N/A'),
                        'identificacion': p.get('numero_identificacion', 'N/A'),
                        'monto': p.get('monto', 'N/A')
                    } for p in personas[:3]  # Primeras 3 personas
                ]
            })
        
        # Keywords details
        if 'palabras_clave_encontradas' in structured_data and isinstance(structured_data['palabras_clave_encontradas'], list):
            keywords = structured_data['palabras_clave_encontradas']
            Logger.log_success(logger, f"🔑 Keywords Found Details", {
                'job_id': job_id,
                'keywords_count': len(keywords),
                'keywords_preview': keywords[:10]  # Primeras 10 palabras clave
            })
        
        # Complete text from structured data
        if 'texto_completo' in structured_data:
            texto_completo = structured_data['texto_completo']
            Logger.log_success(logger, f"📝 Complete Text from Structured Data", {
                'job_id': job_id,
                'texto_completo_length': len(texto_completo),
                'texto_completo_preview': texto_completo[:500] + '...' if len(texto_completo) > 500 else texto_completo
            })
            
            # Texto completo completo desde datos estructurados (sin truncar)
            Logger.log_success(logger, f"📄 Complete Structured Text (Full)", {
                'job_id': job_id,
                'complete_structured_text': texto_completo,
                'structured_text_length': len(texto_completo)
            })
    
    # Final result summary
    Logger.log_success(logger, f"📊 Final Enhanced Result Summary", {
        'job_id': job_id,
        'tipo_oficio_detectado': formatted_result.get('tipo_oficio_detectado', 'N/A'),
        'nivel_confianza': formatted_result.get('nivel_confianza', 'N/A'),
        'has_informacion_extraida': bool(formatted_result.get('informacion_extraida')),
        'keywords_count': len(formatted_result.get('palabras_clave_encontradas', [])),
        'has_observaciones': bool(formatted_result.get('observaciones', ''))
    })
    
    return stats

def send_processing_metrics(stats: Dict[str, Any], job_id: str):
    """Send detailed processing metrics to CloudWatch"""
    try:
        dimensions = {'JobId': job_id}
        
        put_custom_metric('ProcessingSuccess', 1, dimensions=dimensions)
        put_custom_metric('ProcessingTime', stats['processing_time'], 'Seconds', dimensions)
        put_custom_metric('TextLength', stats['text_length'], dimensions=dimensions)
        put_custom_metric('StructuredFieldsCount', stats['structured_fields_count'], dimensions=dimensions)
        put_custom_metric('PersonsCount', stats['persons_count'], dimensions=dimensions)
        
        if stats['total_amount'] > 0:
            put_custom_metric('TotalAmount', stats['total_amount'], 'None', dimensions)
        
        # Confidence level metrics
        confidence_mapping = {'alta': 3, 'media': 2, 'baja': 1}
        confidence_value = confidence_mapping.get(stats['confidence'], 2)
        put_custom_metric('ConfidenceLevel', confidence_value, dimensions=dimensions)
        
    except Exception as e:
        logger.warning(f"Failed to send processing metrics: {str(e)}")

def send_to_crm_queue_enhanced(job_id: str, batch_id: str, message_data: Dict[str, Any], 
                              enhanced_result: Dict[str, Any]) -> None:
    """Send enhanced processed result to CRM integration queue"""
    try:
        crm_message = {
            'job_id': job_id,
            'batch_id': batch_id,
            'source': message_data.get('source', 's3_direct'),
            'timestamp': datetime.utcnow().isoformat(),
            'processing_completed_at': datetime.utcnow().isoformat(),
            'enhanced_processing': True,
            'processing_version': '2.1',
            'has_structured_data': bool(enhanced_result.get('structured_data_raw')),
            'classification': enhanced_result.get('clasificacion', {}),
            'persons_count': len(enhanced_result.get('lista_personas', {}).get('listado', [])),
            'confidence': enhanced_result.get('confidence', 'medium')
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
                },
                'Enhanced': {
                    'StringValue': 'true',
                    'DataType': 'String'
                },
                'Version': {
                    'StringValue': '2.1',
                    'DataType': 'String'
                }
            }
        )
        
    except Exception as e:
        Logger.log_error(logger, f"Error sending enhanced data to CRM queue", {
            'job_id': job_id,
            'error': str(e)
        })