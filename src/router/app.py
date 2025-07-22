import json
import boto3
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Any

# Configuración de logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Configuración
RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET', 
                                os.environ.get('S3_BUCKET_NAME', 'documentdigitalizador'))
PROCESSING_QUEUE_URL = os.environ.get('QUEUE_URL')
SAVE_TO_DYNAMODB = os.environ.get('SAVE_TO_DYNAMODB', 'false').lower() == 'true'
JOBS_TABLE_NAME = os.environ.get('DYNAMODB_TABLE') if SAVE_TO_DYNAMODB else None

# Clientes AWS
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')
dynamodb_client = boto3.client('dynamodb') if SAVE_TO_DYNAMODB else None

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Función Lambda Router que maneja el routing de requests OCR
    """
    try:
        logger.info(f"Router event received: {json.dumps(event, default=str)}")
        
        # Determinar el tipo de operación
        path = event.get('path', '')
        http_method = event.get('httpMethod', 'POST')
        
        logger.info(f"Path: {path}, Method: {http_method}")
        
        if http_method == 'POST' and 'document' in path:
            return handle_document_request(event, context)
        elif http_method == 'OPTIONS':
            return handle_cors_preflight()
        else:
            return create_error_response(404, 'Endpoint no encontrado')
            
    except Exception as e:
        logger.error(f"Error en router: {str(e)}")
        return create_error_response(500, f"Error interno: {str(e)}")

def handle_document_request(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Maneja requests de procesamiento de documentos
    """
    try:
        # Extraer datos del body
        if 'body' in event and isinstance(event['body'], str):
            try:
                body_data = json.loads(event['body'])
            except json.JSONDecodeError:
                return create_error_response(400, 'Body JSON inválido')
        else:
            body_data = event
        
        # Verificar modo de procesamiento
        async_mode = body_data.get('async', True)  # Por defecto asíncrono
        
        if async_mode:
            return handle_async_processing(body_data, context)
        else:
            return create_error_response(501, 'Modo síncrono no implementado en router. Use async=true')
    
    except Exception as e:
        logger.error(f"Error procesando documento: {str(e)}")
        return create_error_response(500, str(e))

def handle_async_processing(input_data: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Inicia procesamiento asíncrono
    """
    try:
        logger.info("Iniciando procesamiento asíncrono")
        
        # Generar ID único para el trabajo
        job_id = str(uuid.uuid4())
        
        # Verificar que tenemos los datos necesarios
        if not any(key in input_data for key in ['pdf_content', 'image_content', 'document_url']):
            return create_error_response(400, "Debe proporcionar 'pdf_content', 'image_content' o 'document_url'")
        
        logger.info(f"Creando job {job_id} con keys: {list(input_data.keys())}")
        
        # Guardar el payload completo en S3
        s3_client.put_object(
            Bucket=RESULTS_BUCKET,
            Key=f'jobs/{job_id}/input.json',
            Body=json.dumps(input_data, ensure_ascii=False),
            ContentType='application/json'
        )
        
        # Crear metadata del trabajo
        job_metadata = {
            'job_id': job_id,
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat(),
            'started_by': context.aws_request_id,
            'async_mode': True
        }
        
        # Guardar metadata en DynamoDB (opcional)
        if SAVE_TO_DYNAMODB and JOBS_TABLE_NAME:
            try:
                job_record = {
                    'job_id': {'S': job_id},
                    'status': {'S': 'pending'},
                    'created_at': {'S': datetime.utcnow().isoformat()},
                    'request_id': {'S': context.aws_request_id},
                    'async_mode': {'BOOL': True}
                }
                
                dynamodb_client.put_item(
                    TableName=JOBS_TABLE_NAME,
                    Item=job_record
                )
                logger.info(f"Job {job_id} guardado en DynamoDB")
            except Exception as e:
                logger.warning(f"Error guardando en DynamoDB: {str(e)}")
        
        # Guardar metadata en S3 (siempre)
        s3_client.put_object(
            Bucket=RESULTS_BUCKET,
            Key=f'jobs/{job_id}/metadata.json',
            Body=json.dumps(job_metadata),
            ContentType='application/json'
        )
        
        # Enviar mensaje a SQS para procesamiento
        if not PROCESSING_QUEUE_URL:
            raise ValueError("QUEUE_URL no configurada")
        
        sqs_message = {
            'job_id': job_id,
            'created_at': datetime.utcnow().isoformat()
        }
        
        sqs_client.send_message(
            QueueUrl=PROCESSING_QUEUE_URL,
            MessageBody=json.dumps(sqs_message)
        )
        
        logger.info(f"Job {job_id} enviado a SQS correctamente")
        
        return {
            'statusCode': 202,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'job_id': job_id,
                'status': 'pending',
                'message': 'Procesamiento iniciado correctamente',
                'check_status_url': f'/document/status/{job_id}',
                'estimated_time': '30-60 segundos',
                'async_mode': True
            }, ensure_ascii=False)
        }
        
    except Exception as e:
        logger.error(f"Error al iniciar procesamiento asíncrono: {str(e)}")
        return create_error_response(500, f"Error al iniciar procesamiento: {str(e)}")

def handle_cors_preflight() -> Dict[str, Any]:
    """
    Maneja requests CORS preflight
    """
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Amz-Date, X-Api-Key, X-Amz-Security-Token'
        },
        'body': json.dumps({'message': 'CORS preflight OK'})
    }

def create_error_response(status_code: int, error_message: str) -> Dict[str, Any]:
    """
    Crea una respuesta de error estandarizada
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'success': False,
            'error': error_message,
            'timestamp': datetime.utcnow().isoformat()
        }, ensure_ascii=False)
    }