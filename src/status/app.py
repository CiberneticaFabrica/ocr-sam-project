import json
import boto3
import logging
import os
from datetime import datetime
from typing import Dict, Any

# Configuración de logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Cliente S3
s3_client = boto3.client('s3')

# Configuración
RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET', 
                                os.environ.get('S3_BUCKET_NAME', 'documentdigitalizador'))
SAVE_TO_DYNAMODB = os.environ.get('SAVE_TO_DYNAMODB', 'false').lower() == 'true'
JOBS_TABLE_NAME = os.environ.get('DYNAMODB_TABLE') if SAVE_TO_DYNAMODB else None

# Cliente DynamoDB (opcional)
dynamodb_client = boto3.client('dynamodb') if SAVE_TO_DYNAMODB else None

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function para consultar el estado de trabajos OCR
    """
    try:
        logger.info(f"Status request received: {json.dumps(event, default=str)}")
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return create_cors_response()
        
        # Extract job_id with better error handling
        job_id = extract_job_id_from_event(event)
        
        if not job_id:
            logger.error("job_id no proporcionado")
            return create_error_response(400, 'job_id es requerido')
        
        logger.info(f"Consultando estado del trabajo: {job_id}")
        
        # Consultar estado del trabajo
        return handle_status_check(job_id)
        
    except Exception as e:
        logger.error(f"Error consultando estado: {str(e)}")
        return create_error_response(500, f"Error interno: {str(e)}")

def extract_job_id_from_event(event: Dict[str, Any]) -> str:
    """
    Extract job_id from various possible locations in the event
    """
    # Try path parameters first
    if 'pathParameters' in event and event['pathParameters']:
        job_id = event['pathParameters'].get('job_id')
        if job_id:
            logger.info(f"job_id extraído de pathParameters: {job_id}")
            return job_id
    
    # Try query string parameters
    if 'queryStringParameters' in event and event['queryStringParameters']:
        job_id = event['queryStringParameters'].get('job_id')
        if job_id:
            logger.info(f"job_id extraído de queryStringParameters: {job_id}")
            return job_id
    
    # Try extracting from path directly
    path = event.get('path', '')
    logger.info(f"Path completo: {path}")
    
    if '/status/' in path:
        parts = path.split('/status/')
        if len(parts) > 1:
            job_id = parts[1].strip('/')  # Remove trailing slashes
            logger.info(f"job_id extraído del path: {job_id}")
            return job_id
    
    logger.warning("No se pudo extraer job_id del evento")
    return None

def handle_status_check(job_id: str) -> Dict[str, Any]:
    """
    Consulta el estado de un trabajo
    """
    try:
        logger.info(f"Consultando estado del trabajo: {job_id}")
        
        # Intentar obtener metadata del trabajo
        try:
            metadata_response = s3_client.get_object(
                Bucket=RESULTS_BUCKET,
                Key=f'jobs/{job_id}/metadata.json'
            )
            metadata = json.loads(metadata_response['Body'].read())
            logger.info(f"Metadata encontrada para job {job_id}: {metadata.get('status')}")
        except s3_client.exceptions.NoSuchKey:
            logger.warning(f"Trabajo no encontrado: {job_id}")
            return create_error_response(404, f'No se encontró el trabajo con ID: {job_id}')
        except Exception as e:
            logger.error(f"Error leyendo metadata: {str(e)}")
            return create_error_response(500, f'Error leyendo metadata del trabajo: {str(e)}')
        
        # Intentar obtener resultado si está disponible
        result_data = None
        try:
            result_response = s3_client.get_object(
                Bucket=RESULTS_BUCKET,
                Key=f'jobs/{job_id}/result.json'
            )
            result_data = json.loads(result_response['Body'].read())
            logger.info(f"Resultado encontrado para job {job_id}")
        except s3_client.exceptions.NoSuchKey:
            logger.info(f"Resultado aún no disponible para trabajo: {job_id}")
        except Exception as e:
            logger.warning(f"Error leyendo resultado: {str(e)}")
        
        # Preparar respuesta base
        response_data = {
            'success': True,
            'job_id': job_id,
            'status': metadata['status'],
            'created_at': metadata['created_at']
        }
        
        # Agregar información según el estado
        if metadata['status'] == 'completed' and result_data:
            response_data['result'] = result_data
            response_data['message'] = 'Procesamiento completado exitosamente'
            
            # Agregar URL del documento si está disponible
            if 'document_url' in metadata:
                response_data['document_url'] = metadata['document_url']
                response_data['document_available'] = True
            
        elif metadata['status'] == 'error' and result_data:
            response_data['error'] = result_data.get('error')
            response_data['error_message'] = result_data.get('message', 'Error al procesar el documento')
        elif metadata['status'] == 'processing':
            response_data['message'] = 'El documento está siendo procesado. Inténtalo de nuevo en unos momentos.'
        elif metadata['status'] == 'pending':
            response_data['message'] = 'El documento está en cola para ser procesado.'
        elif metadata['status'] == 'retrying':
            retry_attempt = metadata.get('retry_attempt', 0)
            response_data['message'] = f'Reintentando procesamiento (intento #{retry_attempt})'
            response_data['retry_attempt'] = retry_attempt
        
        # Agregar timestamps adicionales
        if 'updated_at' in metadata:
            response_data['updated_at'] = metadata['updated_at']
        if 'completed_at' in metadata:
            response_data['completed_at'] = metadata['completed_at']
        
        logger.info(f"Estado consultado exitosamente: {job_id}, estado: {metadata['status']}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': json.dumps(response_data, ensure_ascii=False)
        }
        
    except Exception as e:
        logger.error(f"Error consultando estado: {str(e)}")
        return create_error_response(500, str(e))

def create_cors_response():
    """
    Create proper CORS preflight response
    """
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Amz-Date, X-Api-Key, X-Amz-Security-Token',
            'Access-Control-Max-Age': '86400'
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
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        },
        'body': json.dumps({
            'success': False,
            'error': error_message,
            'timestamp': datetime.utcnow().isoformat()
        }, ensure_ascii=False)
    }