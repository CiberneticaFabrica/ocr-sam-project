# src/retry/app.py
import json
import boto3
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Configurar logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clientes AWS
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')

# Variables de entorno
JOBS_TABLE_NAME = os.environ['JOBS_TABLE_NAME']
PROCESSING_QUEUE_URL = os.environ['QUEUE_URL']

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Busca jobs fallidos y los reintenta automáticamente
    Ejecuta cada 5 minutos via CloudWatch Events
    """
    try:
        logger.info("🔄 Iniciando búsqueda de jobs para retry")
        
        # Buscar jobs que necesitan retry
        failed_jobs = find_failed_jobs()
        retry_jobs = find_retry_jobs()
        
        total_retried = 0
        
        # Procesar jobs fallidos
        for job in failed_jobs:
            if should_retry_job(job):
                retry_job(job)
                total_retried += 1
        
        # Procesar jobs en estado retry
        for job in retry_jobs:
            if is_retry_time(job):
                retry_job(job)
                total_retried += 1
        
        logger.info(f"✅ Procesamiento completado. Jobs reintenados: {total_retried}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'jobs_retried': total_retried,
                'failed_jobs_found': len(failed_jobs),
                'retry_jobs_found': len(retry_jobs)
            })
        }
        
    except Exception as e:
        logger.error(f"❌ Error en retry function: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }

def find_failed_jobs() -> List[Dict[str, Any]]:
    """
    Busca jobs en estado 'error' que pueden ser reintenados
    """
    jobs_table = dynamodb.Table(JOBS_TABLE_NAME)
    
    try:
        # Buscar jobs con status = error
        response = jobs_table.scan(
            FilterExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': 'error'}
        )
        
        failed_jobs = response.get('Items', [])
        logger.info(f"📋 Encontrados {len(failed_jobs)} jobs fallidos")
        
        return failed_jobs
        
    except Exception as e:
        logger.error(f"Error buscando jobs fallidos: {str(e)}")
        return []

def find_retry_jobs() -> List[Dict[str, Any]]:
    """
    Busca jobs en estado 'retrying' que están listos para reintentar
    """
    jobs_table = dynamodb.Table(JOBS_TABLE_NAME)
    
    try:
        # Buscar jobs con status = retrying
        response = jobs_table.scan(
            FilterExpression='#status = :status',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': 'retrying'}
        )
        
        retry_jobs = response.get('Items', [])
        logger.info(f"🔄 Encontrados {len(retry_jobs)} jobs en retry")
        
        return retry_jobs
        
    except Exception as e:
        logger.error(f"Error buscando jobs en retry: {str(e)}")
        return []

def should_retry_job(job: Dict[str, Any]) -> bool:
    """
    Determina si un job fallido debe ser reintenado
    """
    # Verificar número de reintentos
    retry_count = int(job.get('retry_count', 0))
    max_retries = 3
    
    if retry_count >= max_retries:
        logger.info(f"Job {job['job_id']} alcanzó máximo de reintentos ({retry_count})")
        return False
    
    # Verificar tiempo desde último intento
    error_time = job.get('error_at', job.get('updated_at'))
    if error_time:
        try:
            error_dt = datetime.fromisoformat(error_time.replace('Z', '+00:00'))
            min_wait_time = timedelta(minutes=5 * (retry_count + 1))  # Backoff exponencial
            
            if datetime.utcnow() - error_dt.replace(tzinfo=None) < min_wait_time:
                logger.info(f"Job {job['job_id']} aún en periodo de espera")
                return False
        except:
            pass
    
    # Verificar si es un error retryable
    error_message = job.get('error_message', '').lower()
    retryable_errors = [
        'timeout', 'capacity exceeded', '429', 'rate limit',
        'connection', 'temporary', 'unavailable'
    ]
    
    is_retryable = any(error in error_message for error in retryable_errors)
    
    if not is_retryable:
        logger.info(f"Job {job['job_id']} tiene error no retryable: {error_message}")
        return False
    
    logger.info(f"✅ Job {job['job_id']} elegible para retry (intento {retry_count + 1})")
    return True

def is_retry_time(job: Dict[str, Any]) -> bool:
    """
    Verifica si es tiempo de reintentar un job en estado 'retrying'
    """
    retry_scheduled_at = job.get('retry_scheduled_at')
    if not retry_scheduled_at:
        return True  # Si no hay tiempo programado, reintentar ahora
    
    try:
        scheduled_dt = datetime.fromisoformat(retry_scheduled_at.replace('Z', '+00:00'))
        next_retry_seconds = int(job.get('next_retry_in_seconds', 300))
        retry_time = scheduled_dt + timedelta(seconds=next_retry_seconds)
        
        is_time = datetime.utcnow() >= retry_time.replace(tzinfo=None)
        
        if is_time:
            logger.info(f"⏰ Es tiempo de reintentar job {job['job_id']}")
        
        return is_time
        
    except Exception as e:
        logger.error(f"Error verificando tiempo de retry para {job['job_id']}: {str(e)}")
        return True  # Si hay error, reintentar

def retry_job(job: Dict[str, Any]) -> bool:
    """
    Reintenta un job específico
    """
    job_id = job['job_id']
    retry_count = int(job.get('retry_count', 0)) + 1
    
    try:
        logger.info(f"🔄 Reintenando job {job_id} (intento #{retry_count})")
        
        # Actualizar estado del job
        jobs_table = dynamodb.Table(JOBS_TABLE_NAME)
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression="""
                SET #status = :status,
                    retry_count = :retry_count,
                    retry_attempted_at = :retry_time,
                    updated_at = :updated_at
            """,
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'queued',
                ':retry_count': retry_count,
                ':retry_time': datetime.utcnow().isoformat(),
                ':updated_at': datetime.utcnow().isoformat()
            }
        )
        
        # Enviar mensaje a SQS para reprocesamiento
        message = {
            'job_id': job_id,
            'retry_attempt': retry_count,
            'original_created_at': job.get('created_at'),
            'retry_reason': job.get('error_message', 'Unknown error')
        }
        
        sqs.send_message(
            QueueUrl=PROCESSING_QUEUE_URL,
            MessageBody=json.dumps(message),
            MessageAttributes={
                'RetryAttempt': {
                    'StringValue': str(retry_count),
                    'DataType': 'Number'
                },
                'JobId': {
                    'StringValue': job_id,
                    'DataType': 'String'
                }
            }
        )
        
        logger.info(f"✅ Job {job_id} enviado para retry exitosamente")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error reintenando job {job_id}: {str(e)}")
        
        # Marcar como error permanente si falla el retry
        try:
            jobs_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression="""
                    SET #status = :status,
                        retry_error = :retry_error,
                        updated_at = :updated_at
                """,
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'failed_permanently',
                    ':retry_error': str(e),
                    ':updated_at': datetime.utcnow().isoformat()
                }
            )
        except:
            pass
        
        return False

def cleanup_old_jobs():
    """
    Limpia jobs antiguos (opcional, ejecutar mensualmente)
    """
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    jobs_table = dynamodb.Table(JOBS_TABLE_NAME)
    
    # Buscar jobs antiguos completados
    response = jobs_table.scan(
        FilterExpression='#status IN (:completed, :failed) AND created_at < :cutoff',
        ExpressionAttributeNames={'#status': 'status'},
        ExpressionAttributeValues={
            ':completed': 'completed',
            ':failed': 'failed_permanently',
            ':cutoff': cutoff_date.isoformat()
        }
    )
    
    old_jobs = response.get('Items', [])
    
    for job in old_jobs:
        try:
            jobs_table.delete_item(Key={'job_id': job['job_id']})
            logger.info(f"🗑️ Eliminado job antiguo: {job['job_id']}")
        except Exception as e:
            logger.error(f"Error eliminando job {job['job_id']}: {str(e)}")
    
    logger.info(f"🧹 Limpieza completada. Jobs eliminados: {len(old_jobs)}")
 