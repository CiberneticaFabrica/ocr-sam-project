import json
import boto3
import logging
import os
import requests
import base64
from datetime import datetime
from typing import Dict, Any, Optional
import time

# Importar utilidades compartidas
try:
    # En producción con Layer
    from shared.utils import (
        clean_value_lambda, format_persons_for_lambda, format_autos_for_lambda,
        generate_stats_for_lambda, calculate_extraction_percentage,
        log_extraction_summary, detect_document_type, prepare_document,
        build_api_payload, get_legal_classification_prompt
    )
except ImportError:
    # Para desarrollo local, agregar el path relativo
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
    from shared.utils import (
        clean_value_lambda, format_persons_for_lambda, format_autos_for_lambda,
        generate_stats_for_lambda, calculate_extraction_percentage,
        log_extraction_summary, detect_document_type, prepare_document,
        build_api_payload, get_legal_classification_prompt
    )

# Configuración de logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Clientes AWS
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')

# Configuración
RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET', 
                                os.environ.get('S3_BUCKET_NAME', 'documentdigitalizador'))
MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY')
CRM_QUEUE_URL = os.environ.get('CRM_QUEUE_URL')  # NUEVA COLA PARA CRM
TRACKING_TABLE = os.environ.get('TRACKING_TABLE')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Función Lambda para procesamiento OCR de documentos con integración CRM
    """
    try:
        logger.info(f"🔄 Processor event received: {json.dumps(event, default=str)}")
        
        # Procesar mensajes de SQS
        if 'Records' in event:
            return process_sqs_messages(event['Records'], context)
        
        # Procesamiento directo (para testing)
        else:
            return process_single_job(event, context)
            
    except Exception as e:
        logger.error(f"❌ Error en processor: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }

def process_sqs_messages(records: list, context) -> Dict[str, Any]:
    """
    Procesa múltiples mensajes de SQS
    """
    results = []
    
    for record in records:
        try:
            # Parsear el mensaje de SQS
            message_body = json.loads(record['body'])
            job_id = message_body.get('job_id')
            
            logger.info(f"🔄 Procesando job desde SQS: {job_id}")
            
            # Determinar tipo de procesamiento
            if 'oficio_data' in message_body:
                # Nuevo flujo: procesamiento de oficio individual del lote
                result = process_batch_oficio_job(message_body, context)
            else:
                # Flujo existente: job individual
                result = process_individual_ocr_job(job_id, context)
            
            results.append({
                'job_id': job_id,
                'success': result.get('success', False),
                'messageId': record.get('messageId')
            })
            
        except Exception as e:
            logger.error(f"❌ Error procesando mensaje SQS: {str(e)}")
            results.append({
                'messageId': record.get('messageId'),
                'success': False,
                'error': str(e)
            })
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed_jobs': len(results),
            'results': results
        })
    }

def process_batch_oficio_job(message_data: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Procesa un oficio individual del lote de email
    """
    try:
        job_id = message_data['job_id']
        batch_id = message_data['batch_id']
        oficio_data = message_data['oficio_data']
        
        logger.info(f"📄 Procesando oficio del lote: {job_id} (batch: {batch_id})")
        
        # Actualizar estado en DynamoDB
        update_oficio_status(batch_id, job_id, 'processing', 'OCR iniciado')
        
        # Obtener PDF del oficio desde S3
        s3_key = oficio_data['s3_key']
        pdf_content = get_pdf_from_s3(s3_key)
        
        # Preparar datos para OCR
        input_data = {
            'pdf_content': base64.b64encode(pdf_content).decode('utf-8'),
            'annotation_type': 'document',
            'custom_prompt': 'Extract and structure key information from this legal document',
            'job_id': job_id,
            'batch_id': batch_id,
            'source': 'email_batch'
        }
        
        # Procesar con OCR
        ocr_result = process_ocr_with_mistral(input_data, context)
        
        if ocr_result['success']:
            # Guardar resultado OCR
            save_ocr_result_to_s3(job_id, ocr_result)
            
            # Actualizar estado OCR completado
            update_oficio_status(batch_id, job_id, 'ocr_completed', 'OCR exitoso')
            
            # Enviar a cola de CRM si está configurada
            if CRM_QUEUE_URL:
                send_to_crm_queue(job_id, batch_id, message_data)
                logger.info(f"📤 Job {job_id} enviado a cola CRM")
            else:
                # Marcar como completado si no hay integración CRM
                update_oficio_status(batch_id, job_id, 'completed', 'Procesamiento completado')
            
            return {
                'success': True,
                'job_id': job_id,
                'batch_id': batch_id,
                'message': 'Oficio procesado exitosamente'
            }
        else:
            # Error en OCR
            error_msg = ocr_result.get('error', 'Error desconocido en OCR')
            update_oficio_status(batch_id, job_id, 'error', f'Error OCR: {error_msg}')
            
            return {
                'success': False,
                'job_id': job_id,
                'batch_id': batch_id,
                'error': error_msg
            }
        
    except Exception as e:
        logger.error(f"❌ Error procesando oficio del lote: {str(e)}")
        try:
            update_oficio_status(message_data.get('batch_id'), message_data.get('job_id'), 
                               'error', f'Error de procesamiento: {str(e)}')
        except:
            pass
        
        return {
            'success': False,
            'job_id': message_data.get('job_id'),
            'error': str(e)
        }

def process_individual_ocr_job(job_id: str, context) -> Dict[str, Any]:
    """
    Procesa un trabajo OCR individual (flujo existente)
    """
    try:
        logger.info(f"🏁 INICIO - Procesando trabajo OCR individual {job_id}")
        
        # Calcular tiempo disponible
        remaining_time_ms = context.get_remaining_time_in_millis()
        remaining_time_seconds = remaining_time_ms / 1000
        
        logger.info(f"⏱️  Tiempo restante en Lambda: {remaining_time_seconds:.1f} segundos")
        
        # Verificar tiempo suficiente
        if remaining_time_seconds < 120:
            error_msg = f"Tiempo insuficiente para procesamiento: {remaining_time_seconds:.1f}s"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)
        
        # Calcular timeout máximo para API
        max_api_timeout = min(600, remaining_time_seconds - 90)  # Dejar 90s de buffer
        logger.info(f"🎯 Timeout máximo para API: {max_api_timeout:.1f} segundos")
        
        # Actualizar estado a procesando
        update_job_status(job_id, 'processing', {
            'started_processing_at': datetime.utcnow().isoformat(),
            'lambda_timeout_seconds': max_api_timeout,
            'lambda_request_id': context.aws_request_id
        })
        
        # Leer datos de entrada desde S3
        logger.info(f"📂 Leyendo input desde S3 para job {job_id}")
        input_data = read_job_input_from_s3(job_id)
        
        # Procesar con OCR
        ocr_result = process_ocr_with_mistral(input_data, context, max_api_timeout)
        
        if ocr_result['success']:
            # Guardar resultado en S3
            save_job_result_to_s3(job_id, ocr_result)
            
            # Generar URL del documento si es posible
            document_url = generate_document_presigned_url(job_id, input_data)
            
            # Actualizar estado a completado
            update_job_status(job_id, 'completed', {
                'completed_at': datetime.utcnow().isoformat(),
                'result_available': True,
                'document_url': document_url
            })
            
            logger.info(f"🏆 ===== TRABAJO {job_id} COMPLETADO EXITOSAMENTE =====")
            
            return {
                'success': True,
                'job_id': job_id,
                'document_url': document_url,
                'message': 'Procesamiento completado'
            }
        else:
            # Error en procesamiento
            error_msg = ocr_result.get('error', 'Error desconocido')
            
            # Guardar resultado de error
            save_job_result_to_s3(job_id, ocr_result)
            
            # Actualizar estado a error
            update_job_status(job_id, 'error', {
                'error_at': datetime.utcnow().isoformat(),
                'error_message': error_msg
            })
            
            return {
                'success': False,
                'job_id': job_id,
                'error': error_msg
            }
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"💥 ===== ERROR PROCESANDO TRABAJO {job_id} =====")
        logger.error(f"💥 Error: {error_message}")
        
        # Preparar resultado de error
        error_result = {
            'success': False,
            'error': error_message,
            'message': 'Error al procesar el documento',
            'error_at': datetime.utcnow().isoformat()
        }
        
        # Guardar resultado de error
        try:
            save_job_result_to_s3(job_id, error_result)
        except:
            logger.error("No se pudo guardar resultado de error en S3")
        
        # Actualizar estado a error
        update_job_status(job_id, 'error', {
            'error_at': datetime.utcnow().isoformat(),
            'error_message': error_message
        })
        
        return {
            'success': False,
            'job_id': job_id,
            'error': error_message
        }

def process_ocr_with_mistral(input_data: Dict[str, Any], context, max_timeout: float = None) -> Dict[str, Any]:
    """
    Procesa documento con Mistral OCR API
    """
    try:
        # Verificar API key
        if not MISTRAL_API_KEY:
            raise ValueError("MISTRAL_API_KEY no configurada en variables de entorno")
        
        # Preparar el documento
        logger.info("📄 Preparando documento...")
        document_data = prepare_document(input_data)
        logger.info(f"✅ Documento preparado: {document_data.get('document_type', 'unknown')}")
        
        # Detectar tipo de documento
        document_type = detect_document_type(input_data)
        logger.info(f"🏷️  Tipo de documento detectado: {document_type}")
        
        # Preparar parámetros de procesamiento
        annotation_type = input_data.get('annotation_type', 'document')
        custom_prompt = input_data.get('custom_prompt', 'Extract and structure key information from this document')
        
        # Usar prompt especializado para documentos legales
        if document_type == 'legal_document' and custom_prompt == 'Extract and structure key information from this document':
            custom_prompt = get_legal_classification_prompt()
            logger.info("📝 Usando prompt especializado para documento legal")
        
        logger.info(f"⚙️  Annotation type: {annotation_type}")
        
        # Construir payload para API
        logger.info("🔧 Construyendo payload para API...")
        payload = build_api_payload(document_data, annotation_type, custom_prompt, input_data)
        
        # Log del tamaño del payload
        payload_size = len(json.dumps(payload))
        logger.info(f"📏 Tamaño del payload: ~{payload_size / 1024:.1f} KB")
        
        # Llamada a API con timeout protection
        timeout = max_timeout if max_timeout else 600
        logger.info("🚀 ===== INICIANDO LLAMADA A MISTRAL API =====")
        
        try:
            response = call_mistral_ocr_api_with_timeout_protection(payload, MISTRAL_API_KEY, timeout)
            logger.info("🎉 ===== API CALL COMPLETADA EXITOSAMENTE =====")
            
        except Exception as api_error:
            logger.error(f"💥 ===== API CALL FALLÓ =====")
            logger.error(f"💥 Error en API: {str(api_error)}")
            raise api_error
        
        logger.info("🔄 Procesando respuesta de API...")
        
        # Procesar respuesta
        processed_response = process_response_by_type(response, document_type, input_data)
        formatted_response = format_ocr_response_for_lambda(processed_response)
        clean_response = extract_clean_document_annotation(formatted_response)
        
        logger.info("📊 Generando estadísticas de extracción...")
        log_extraction_summary(clean_response)
        
        # Preparar resultado final
        result = {
            'success': True,
            'data': clean_response,
            'document_type': document_type,
            'message': 'Documento procesado exitosamente',
            'processed_at': datetime.utcnow().isoformat()
        }
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error en procesamiento OCR: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': 'Error al procesar el documento',
            'error_at': datetime.utcnow().isoformat()
        }

# =====================================
# FUNCIONES AUXILIARES
# =====================================

def get_pdf_from_s3(s3_key: str) -> bytes:
    """
    Obtiene PDF desde S3
    """
    try:
        response = s3_client.get_object(Bucket=RESULTS_BUCKET, Key=s3_key)
        return response['Body'].read()
    except Exception as e:
        logger.error(f"❌ Error obteniendo PDF desde S3: {str(e)}")
        raise

def save_ocr_result_to_s3(job_id: str, result: Dict[str, Any]):
    """
    Guarda resultado OCR en S3
    """
    try:
        # Guardar en la estructura existente
        s3_client.put_object(
            Bucket=RESULTS_BUCKET,
            Key=f'jobs/{job_id}/result.json',
            Body=json.dumps(result, ensure_ascii=False),
            ContentType='application/json'
        )
        
        # También guardar en estructura de oficios para compatibilidad
        if 'batch_id' in result:
            s3_client.put_object(
                Bucket=RESULTS_BUCKET,
                Key=f'oficios/results/{job_id}_result.json',
                Body=json.dumps(result, ensure_ascii=False),
                ContentType='application/json'
            )
        
        logger.info(f"✅ Resultado OCR guardado en S3 para job {job_id}")
        
    except Exception as e:
        logger.error(f"❌ Error guardando resultado OCR: {str(e)}")
        raise

def send_to_crm_queue(job_id: str, batch_id: str, original_message: Dict[str, Any]):
    """
    Envía trabajo completado a cola CRM
    """
    try:
        crm_message = {
            'job_id': job_id,
            'batch_id': batch_id,
            'completed_at': datetime.utcnow().isoformat(),
            'source': 'ocr_processor',
            'original_message': original_message
        }
        
        sqs_client.send_message(
            QueueUrl=CRM_QUEUE_URL,
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
                'Source': {
                    'StringValue': 'ocr_processor',
                    'DataType': 'String'
                }
            }
        )
        
        logger.info(f"📤 Mensaje enviado a cola CRM para job {job_id}")
        
    except Exception as e:
        logger.error(f"❌ Error enviando a cola CRM: {str(e)}")
        raise

def update_oficio_status(batch_id: str, oficio_id: str, status: str, details: str = ''):
    """
    Actualiza estado de oficio en DynamoDB
    """
    if not TRACKING_TABLE:
        logger.warning("⚠️ TRACKING_TABLE no configurada, saltando actualización de estado")
        return
    
    try:
        table = dynamodb.Table(TRACKING_TABLE)
        
        update_expression = """
            SET #status = :status,
                updated_at = :updated_at
        """
        
        expression_values = {
            ':status': status,
            ':updated_at': datetime.utcnow().isoformat()
        }
        
        expression_names = {
            '#status': 'status'
        }
        
        # Agregar campos específicos según el estado
        if status == 'processing':
            update_expression += ", ocr_status = :ocr_status, ocr_started_at = :started_at"
            expression_values.update({
                ':ocr_status': 'processing',
                ':started_at': datetime.utcnow().isoformat()
            })
        elif status == 'ocr_completed':
            update_expression += ", ocr_status = :ocr_status, ocr_completed_at = :completed_at"
            expression_values.update({
                ':ocr_status': 'completed',
                ':completed_at': datetime.utcnow().isoformat()
            })
        elif status == 'completed':
            update_expression += ", completed_at = :completed_at"
            expression_values[':completed_at'] = datetime.utcnow().isoformat()
        elif status == 'error':
            update_expression += ", error_message = :error_msg"
            expression_values[':error_msg'] = details
        
        if details and status != 'error':
            update_expression += ", processing_details = :details"
            expression_values[':details'] = details
        
        table.update_item(
            Key={
                'batch_id': batch_id,
                'oficio_id': oficio_id
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"✅ Estado actualizado en DynamoDB: {oficio_id} -> {status}")
        
    except Exception as e:
        logger.error(f"❌ Error actualizando estado en DynamoDB: {str(e)}")

def process_single_job(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Procesa un job individual (para testing directo)
    """
    job_id = event.get('job_id')
    if not job_id:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'success': False,
                'error': 'job_id requerido'
            })
        }
    
    result = process_ocr_job(job_id, context)
    
    return {
        'statusCode': 200 if result.get('success') else 500,
        'body': json.dumps(result)
    }

def process_ocr_job(job_id: str, context) -> Dict[str, Any]:
    """
    Procesa un trabajo OCR completo con manejo de timeouts y reintentos
    """
    try:
        logger.info(f"🏁 INICIO - Procesando trabajo OCR {job_id}")
        
        # Calcular tiempo disponible
        remaining_time_ms = context.get_remaining_time_in_millis()
        remaining_time_seconds = remaining_time_ms / 1000
        
        logger.info(f"⏱️  Tiempo restante en Lambda: {remaining_time_seconds:.1f} segundos")
        
        # Verificar tiempo suficiente
        if remaining_time_seconds < 120:
            error_msg = f"Tiempo insuficiente para procesamiento: {remaining_time_seconds:.1f}s"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)
        
        # Calcular timeout máximo para API
        max_api_timeout = min(600, remaining_time_seconds - 90)  # Dejar 90s de buffer
        logger.info(f"🎯 Timeout máximo para API: {max_api_timeout:.1f} segundos")
        
        # Actualizar estado a procesando
        update_job_status(job_id, 'processing', {
            'started_processing_at': datetime.utcnow().isoformat(),
            'lambda_timeout_seconds': max_api_timeout,
            'lambda_request_id': context.aws_request_id
        })
        
        # Leer datos de entrada desde S3
        logger.info(f"📂 Leyendo input desde S3 para job {job_id}")
        input_data = read_job_input_from_s3(job_id)
        
        # Verificar API key
        if not MISTRAL_API_KEY:
            raise ValueError("MISTRAL_API_KEY no configurada en variables de entorno")
        
        # Preparar el documento
        logger.info("📄 Preparando documento...")
        document_data = prepare_document(input_data)
        logger.info(f"✅ Documento preparado: {document_data.get('document_type', 'unknown')}")
        
        # Detectar tipo de documento
        document_type = detect_document_type(input_data)
        logger.info(f"🏷️  Tipo de documento detectado: {document_type}")
        
        # Preparar parámetros de procesamiento
        annotation_type = input_data.get('annotation_type', 'document')
        custom_prompt = input_data.get('custom_prompt', 'Extract and structure key information from this document')
        
        # Usar prompt especializado para documentos legales
        if document_type == 'legal_document' and custom_prompt == 'Extract and structure key information from this document':
            custom_prompt = get_legal_classification_prompt()
            logger.info("📝 Usando prompt especializado para documento legal")
        
        logger.info(f"⚙️  Annotation type: {annotation_type}")
        
        # Construir payload para API
        logger.info("🔧 Construyendo payload para API...")
        payload = build_api_payload(document_data, annotation_type, custom_prompt, input_data)
        
        # Log del tamaño del payload
        payload_size = len(json.dumps(payload))
        logger.info(f"📏 Tamaño del payload: ~{payload_size / 1024:.1f} KB")
        
        # Actualizar estado antes de la llamada API
        update_job_status(job_id, 'processing', {
            'api_call_about_to_start': datetime.utcnow().isoformat(),
            'document_type': document_type,
            'annotation_type': annotation_type,
            'payload_size_kb': payload_size / 1024
        })
        
        # 🚨 LLAMADA CRÍTICA A LA API
        logger.info("🚀 ===== INICIANDO LLAMADA A MISTRAL API =====")
        
        try:
            response = call_mistral_ocr_api_with_timeout_protection(payload, MISTRAL_API_KEY, max_api_timeout)
            logger.info("🎉 ===== API CALL COMPLETADA EXITOSAMENTE =====")
            
        except Exception as api_error:
            logger.error(f"💥 ===== API CALL FALLÓ =====")
            logger.error(f"💥 Error en API: {str(api_error)}")
            
            # Actualizar estado con error de API
            update_job_status(job_id, 'processing', {
                'api_error_at': datetime.utcnow().isoformat(),
                'api_error_message': str(api_error),
                'api_error_type': type(api_error).__name__
            })
            
            raise api_error
        
        logger.info("🔄 Procesando respuesta de API...")
        
        # Procesar respuesta
        processed_response = process_response_by_type(response, document_type, input_data)
        formatted_response = format_ocr_response_for_lambda(processed_response)
        clean_response = extract_clean_document_annotation(formatted_response)
        
        logger.info("📊 Generando estadísticas de extracción...")
        log_extraction_summary(clean_response)
        
        # Generar URL del documento si es posible
        logger.info("🔗 Generando URL del documento...")
        document_url = generate_document_presigned_url(job_id, input_data)
        
        # Preparar resultado final
        result = {
            'success': True,
            'data': clean_response,
            'document_type': document_type,
            'message': 'Documento procesado exitosamente',
            'processed_at': datetime.utcnow().isoformat(),
            'async_mode': True
        }
        
        logger.info("💾 Guardando resultado en S3...")
        
        # Guardar resultado en S3
        save_job_result_to_s3(job_id, result)
        
        # Actualizar estado a completado
        update_job_status(job_id, 'completed', {
            'completed_at': datetime.utcnow().isoformat(),
            'result_available': True,
            'document_url': document_url
        })
        
        logger.info(f"🏆 ===== TRABAJO {job_id} COMPLETADO EXITOSAMENTE =====")
        
        return {
            'success': True,
            'job_id': job_id,
            'document_url': document_url,
            'message': 'Procesamiento completado'
        }
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"💥 ===== ERROR PROCESANDO TRABAJO {job_id} =====")
        logger.error(f"💥 Error: {error_message}")
        
        # Preparar resultado de error
        error_result = {
            'success': False,
            'error': error_message,
            'message': 'Error al procesar el documento',
            'error_at': datetime.utcnow().isoformat(),
            'async_mode': True
        }
        
        # Guardar resultado de error
        try:
            save_job_result_to_s3(job_id, error_result)
        except:
            logger.error("No se pudo guardar resultado de error en S3")
        
        # Actualizar estado a error
        update_job_status(job_id, 'error', {
            'error_at': datetime.utcnow().isoformat(),
            'error_message': error_message
        })
        
        return {
            'success': False,
            'job_id': job_id,
            'error': error_message
        }

# =====================================
# FUNCIONES DE PROCESAMIENTO OCR
# =====================================

def call_mistral_ocr_api_with_timeout_protection(payload: Dict[str, Any], api_key: str, max_timeout_seconds: float) -> Dict[str, Any]:
    """
    Llamada a Mistral API con timeout estricto
    """
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }
    
    url = 'https://api.mistral.ai/v1/ocr'
    timeout = min(max_timeout_seconds, 600)  # Máximo 10 minutos
    
    logger.info(f"🎯 Configurando timeout estricto de {timeout} segundos")
    
    start_time = datetime.utcnow()
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout
        )
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"📨 Respuesta recibida en {duration:.1f} segundos")
        
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Error de API: {error_msg}")
            raise Exception(error_msg)
            
    except requests.exceptions.Timeout:
        duration = (datetime.utcnow() - start_time).total_seconds()
        error_msg = f"API timeout después de {duration:.1f} segundos"
        logger.error(f"⏰ {error_msg}")
        raise Exception(error_msg)
        
    except requests.exceptions.RequestException as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        error_msg = f"Error de conexión después de {duration:.1f} segundos: {str(e)}"
        logger.error(f"🔌 {error_msg}")
        raise Exception(error_msg)

def process_response_by_type(response: Dict[str, Any], document_type: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procesa la respuesta según el tipo de documento detectado
    """
    if document_type == 'legal_document':
        logger.info("Procesando respuesta de documento legal")
        
        # Agregar metadatos específicos para documentos legales
        if 'choices' in response and len(response['choices']) > 0:
            choice = response['choices'][0]
            if 'message' in choice and 'content' in choice['message']:
                content = choice['message']['content']
                
                # Intentar parsear como JSON si es posible
                try:
                    parsed_content = json.loads(content)
                    
                    # Validar que tiene la estructura esperada de documento legal
                    if 'palabras_clave_encontradas' in parsed_content:
                        response['legal_classification'] = True
                        response['document_type'] = 'legal_document'
                        
                        # Agregar información de confianza al nivel superior
                        if 'nivel_confianza' in parsed_content:
                            response['classification_confidence'] = parsed_content['nivel_confianza']
                    
                except json.JSONDecodeError:
                    logger.warning("No se pudo parsear el contenido como JSON")
    
    return response

def format_ocr_response_for_lambda(raw_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Formatea la respuesta OCR con todos los campos del schema mejorado
    """
    try:
        # Extraer document_annotation del resultado
        document_annotation_str = None
        if 'data' in raw_response and 'document_annotation' in raw_response['data']:
            document_annotation_str = raw_response['data']['document_annotation']
        elif 'choices' in raw_response and len(raw_response['choices']) > 0:
            # Si viene directo de la API
            document_annotation_str = raw_response['choices'][0]['message']['content']
        
        if not document_annotation_str:
            return raw_response
        
        # Parsear el JSON string a objeto
        document_annotation = json.loads(document_annotation_str)
        
        # Extraer información general
        info_extraida = document_annotation.get('informacion_extraida', {})
        
        # Crear versión simplificada y limpia
        simplified_annotation = {
            "palabras_clave_encontradas": document_annotation.get('palabras_clave_encontradas', []),
            "tipo_oficio_detectado": document_annotation.get('tipo_oficio_detectado', 'No identificado'),
            "nivel_confianza": document_annotation.get('nivel_confianza', 'N/A'),
            
            "informacion_extraida": {
                # Campos originales
                "numero_oficio": clean_value_lambda(info_extraida.get('numero_oficio')),
                "autoridad": clean_value_lambda(info_extraida.get('autoridad')),
                "fecha_emision": clean_value_lambda(info_extraida.get('fecha_emision')),
                "fecha_recibido": clean_value_lambda(info_extraida.get('fecha_recibido')),
                "oficiado_cliente": clean_value_lambda(info_extraida.get('oficiado_cliente')),
                "numero_identificacion": clean_value_lambda(info_extraida.get('numero_identificacion')),
                "expediente": clean_value_lambda(info_extraida.get('expediente')),
                "fecha_auto": clean_value_lambda(info_extraida.get('fecha_auto')),
                "numero_auto": clean_value_lambda(info_extraida.get('numero_auto')),
                "monto": clean_value_lambda(info_extraida.get('monto')),
                "sucursal_recibido": clean_value_lambda(info_extraida.get('sucursal_recibido')),
                "carpeta": clean_value_lambda(info_extraida.get('carpeta')),
                "vencimiento": clean_value_lambda(info_extraida.get('vencimiento')),
                "sello_recibido": clean_value_lambda(info_extraida.get('sello_recibido')),
                "numero_resolucion": clean_value_lambda(info_extraida.get('numero_resolucion')),
                "fecha_resolucion": clean_value_lambda(info_extraida.get('fecha_resolucion')),
                "delito": clean_value_lambda(info_extraida.get('delito')),
                
                # NUEVOS CAMPOS AGREGADOS
                "sello_autoridad": clean_value_lambda(info_extraida.get('sello_autoridad')),
                "dirigido_global_bank": clean_value_lambda(info_extraida.get('dirigido_global_bank')),
                "tipo_producto": clean_value_lambda(info_extraida.get('tipo_producto')),
                "denuciante": clean_value_lambda(info_extraida.get('denuciante'))
            },
            
            # Listas formateadas
            "lista_personas": format_persons_for_lambda(document_annotation.get('lista_personas', [])),
            "lista_autos": format_autos_for_lambda(document_annotation.get('lista_autos', [])),
            
            # Estadísticas y análisis
            "estadisticas": generate_stats_for_lambda(document_annotation.get('lista_personas', [])),
            "analisis_extraccion": calculate_extraction_percentage(info_extraida, document_annotation.get('lista_personas', [])),
            
            # Campos de texto
            "texto_completo": document_annotation.get('texto_completo', ''),
            "observaciones": document_annotation.get('observaciones', ''),
            
            # INFORMACIÓN DE VALIDACIÓN
            "validacion": {
                "total_autos_extraidos": len(document_annotation.get('lista_autos', [])),
                "campos_nuevos_presentes": {
                    "tiene_sello_autoridad": bool(info_extraida.get('sello_autoridad')),
                    "tiene_tipo_producto": bool(info_extraida.get('tipo_producto')),
                    "tiene_denuciante": bool(info_extraida.get('denuciante')),
                    "tiene_autos": len(document_annotation.get('lista_autos', [])) > 0
                }
            }
        }
        
        # Reemplazar completamente el data con el annotation limpio
        return {
            "pages": raw_response.get('pages', []),
            "model": raw_response.get('model', ''),
            "document_annotation": simplified_annotation,
            "usage_info": raw_response.get('usage_info', {})
        }

    except Exception as e:
        logger.error(f"Error al formatear respuesta: {str(e)}")
        return raw_response

def extract_clean_document_annotation(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae únicamente el document_annotation limpio y formateado
    """
    try:
        if 'data' in response and 'document_annotation' in response['data']:
            if isinstance(response['data']['document_annotation'], str):
                return json.loads(response['data']['document_annotation'])
            else:
                return response['data']['document_annotation']
        
        elif 'document_annotation' in response:
            if isinstance(response['document_annotation'], str):
                return json.loads(response['document_annotation'])
            else:
                return response['document_annotation']
        
        else:
            return {"error": "No se encontró document_annotation"}
            
    except Exception as e:
        return {"error": f"Error extrayendo annotation: {str(e)}"}

# =====================================
# FUNCIONES DE S3 Y ESTADO
# =====================================

def read_job_input_from_s3(job_id: str) -> Dict[str, Any]:
    """
    Lee los datos de entrada de un job desde S3
    """
    try:
        input_response = s3_client.get_object(
            Bucket=RESULTS_BUCKET,
            Key=f'jobs/{job_id}/input.json'
        )
        input_data = json.loads(input_response['Body'].read())
        logger.info(f"✅ Input data cargada desde S3: {list(input_data.keys())}")
        return input_data
        
    except Exception as e:
        logger.error(f"❌ Error leyendo input desde S3: {str(e)}")
        raise Exception(f"Error leyendo datos de entrada: {str(e)}")

def save_job_result_to_s3(job_id: str, result: Dict[str, Any]):
    """
    Guarda el resultado de un job en S3
    """
    try:
        s3_client.put_object(
            Bucket=RESULTS_BUCKET,
            Key=f'jobs/{job_id}/result.json',
            Body=json.dumps(result, ensure_ascii=False),
            ContentType='application/json'
        )
        logger.info(f"✅ Resultado guardado en S3 para job {job_id}")
        
    except Exception as e:
        logger.error(f"❌ Error guardando resultado en S3: {str(e)}")
        raise

def update_job_status(job_id: str, status: str, additional_data: Dict[str, Any] = None):
    """
    Actualiza el estado de un trabajo en S3
    """
    try:
        # Obtener metadata actual
        try:
            metadata_response = s3_client.get_object(
                Bucket=RESULTS_BUCKET,
                Key=f'jobs/{job_id}/metadata.json'
            )
            metadata = json.loads(metadata_response['Body'].read())
        except s3_client.exceptions.NoSuchKey:
            # Crear metadata inicial si no existe
            metadata = {
                'job_id': job_id,
                'created_at': datetime.utcnow().isoformat(),
                'async_mode': True
            }
        
        # Actualizar estado
        metadata['status'] = status
        metadata['updated_at'] = datetime.utcnow().isoformat()
        
        # Agregar datos adicionales
        if additional_data:
            metadata.update(additional_data)
        
        # Guardar metadata actualizada
        s3_client.put_object(
            Bucket=RESULTS_BUCKET,
            Key=f'jobs/{job_id}/metadata.json',
            Body=json.dumps(metadata),
            ContentType='application/json'
        )
        
        logger.info(f"✅ Estado actualizado para job {job_id}: {status}")
        
    except Exception as e:
        logger.error(f"❌ Error actualizando estado del trabajo {job_id}: {str(e)}")

def generate_document_presigned_url(job_id: str, input_data: Dict[str, Any]) -> Optional[str]:
    """
    Genera URL presignada para acceder al documento original
    """
    try:
        # Si hay contenido PDF, guardarlo como archivo
        if 'pdf_content' in input_data:
            pdf_key = f'jobs/{job_id}/document.pdf'
            
            # Decodificar y guardar el PDF
            pdf_content = base64.b64decode(input_data['pdf_content'])
            s3_client.put_object(
                Bucket=RESULTS_BUCKET,
                Key=pdf_key,
                Body=pdf_content,
                ContentType='application/pdf'
            )
            
            # Generar URL presignada (válida por 24 horas)
            document_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': RESULTS_BUCKET, 'Key': pdf_key},
                ExpiresIn=86400  # 24 horas
            )
            
            logger.info(f"PDF guardado y URL generada para job {job_id}")
            return document_url
            
        elif 'image_content' in input_data:
            image_key = f'jobs/{job_id}/document.jpg'
            
            # Decodificar y guardar la imagen
            image_content = base64.b64decode(input_data['image_content'])
            s3_client.put_object(
                Bucket=RESULTS_BUCKET,
                Key=image_key,
                Body=image_content,
                ContentType='image/jpeg'
            )
            
            # Generar URL presignada
            document_url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': RESULTS_BUCKET, 'Key': image_key},
                ExpiresIn=86400
            )
            
            logger.info(f"Imagen guardada y URL generada para job {job_id}")
            return document_url
            
    except Exception as e:
        logger.warning(f"No se pudo generar URL del documento: {str(e)}")
        return None