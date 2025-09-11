# src/batch_status/app.py
import json
import boto3
import logging
import os
from datetime import datetime
from typing import Dict, Any, List
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# Configuración de logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Cliente DynamoDB
dynamodb = boto3.resource('dynamodb')

# Variables de entorno
TRACKING_TABLE = os.environ['TRACKING_TABLE']

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Consulta el estado de un lote completo de oficios
    """
    try:
        logger.info(f"📊 Batch status request: {json.dumps(event, default=str)}")
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return create_cors_response()
        
        # Extract batch_id
        batch_id = extract_batch_id_from_event(event)
        
        if not batch_id:
            return create_error_response(400, 'batch_id es requerido')
        
        logger.info(f"🔍 Consultando estado del lote: {batch_id}")
        
        # Obtener información del lote
        batch_info = get_batch_information(batch_id)
        
        if not batch_info:
            return create_error_response(404, f'No se encontró el lote: {batch_id}')
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': json.dumps(convert_decimals(batch_info), ensure_ascii=False)
        }
        
    except Exception as e:
        logger.error(f"❌ Error consultando estado del lote: {str(e)}")
        return create_error_response(500, f"Error interno: {str(e)}")

def extract_batch_id_from_event(event: Dict[str, Any]) -> str:
    """
    Extrae batch_id del evento
    """
    # Try path parameters first
    if 'pathParameters' in event and event['pathParameters']:
        batch_id = event['pathParameters'].get('batch_id')
        if batch_id:
            return batch_id
    
    # Try query string parameters
    if 'queryStringParameters' in event and event['queryStringParameters']:
        batch_id = event['queryStringParameters'].get('batch_id')
        if batch_id:
            return batch_id
    
    # Try extracting from path directly
    path = event.get('path', '')
    if '/batch/status/' in path:
        parts = path.split('/batch/status/')
        if len(parts) > 1:
            return parts[1].strip('/')
    
    return None

def get_batch_information(batch_id: str) -> Dict[str, Any]:
    """
    Obtiene información completa del lote
    """
    try:
        table = dynamodb.Table(TRACKING_TABLE)
        
        # Obtener todos los registros del batch
        response = table.query(
            KeyConditionExpression=Key('batch_id').eq(batch_id)
        )
        
        items = response.get('Items', [])
        
        if not items:
            logger.warning(f"⚠️ No se encontraron registros para batch {batch_id}")
            return None
        
        # Separar resumen del batch y oficios individuales
        batch_summary = None
        oficios = []
        
        for item in items:
            if item['oficio_id'] == 'BATCH_SUMMARY':
                batch_summary = item
            else:
                oficios.append(item)
        
        if not batch_summary:
            logger.warning(f"⚠️ No se encontró resumen para batch {batch_id}")
            return None
        
        # Calcular estadísticas actualizadas
        stats = calculate_batch_statistics(oficios)
        
        # Construir respuesta completa
        batch_info = {
            'success': True,
            'batch_id': batch_id,
            'summary': {
                'status': batch_summary.get('status', 'unknown'),
                'total_oficios': batch_summary.get('total_oficios', 0),
                'completed_oficios': batch_summary.get('completed_oficios', 0),
                'failed_oficios': batch_summary.get('failed_oficios', 0),
                'created_at': batch_summary.get('created_at'),
                'completed_at': batch_summary.get('completed_at'),
                'completion_rate': batch_summary.get('completion_rate', 0),
                'processing_started_at': batch_summary.get('processing_started_at'),
                'email_metadata': batch_summary.get('email_metadata', {})
            },
            'statistics': stats,
            'oficios': format_oficios_for_response(oficios),
            'progress': calculate_progress_info(batch_summary, stats),
            'timeline': generate_timeline(batch_summary, oficios),
            'errors': get_error_summary(oficios)
        }
        
        logger.info(f"📊 Información del lote obtenida: {len(oficios)} oficios")
        return batch_info
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo información del lote: {str(e)}")
        return None

def calculate_batch_statistics(oficios: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcula estadísticas del lote basadas en oficios
    """
    total = len(oficios)
    
    if total == 0:
        return {
            'total_oficios': 0,
            'by_status': {},
            'by_ocr_status': {},
            'by_crm_status': {},
            'processing_times': {}
        }
    
    # Contadores por estado
    status_counts = {}
    ocr_status_counts = {}
    crm_status_counts = {}
    
    # Tiempos de procesamiento
    processing_times = []
    
    for oficio in oficios:
        # Estado general
        status = oficio.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
        
        # Estado OCR
        ocr_status = oficio.get('ocr_status', 'unknown')
        ocr_status_counts[ocr_status] = ocr_status_counts.get(ocr_status, 0) + 1
        
        # Estado CRM
        crm_status = oficio.get('crm_status', 'unknown')
        crm_status_counts[crm_status] = crm_status_counts.get(crm_status, 0) + 1
        
        # Calcular tiempo de procesamiento si está completo
        if status == 'completed' and 'created_at' in oficio and 'completed_at' in oficio:
            try:
                created = datetime.fromisoformat(oficio['created_at'].replace('Z', '+00:00'))
                completed = datetime.fromisoformat(oficio['completed_at'].replace('Z', '+00:00'))
                duration = (completed - created).total_seconds()
                processing_times.append(duration)
            except:
                pass
    
    # Calcular estadísticas de tiempo
    time_stats = {}
    if processing_times:
        time_stats = {
            'average_seconds': sum(processing_times) / len(processing_times),
            'min_seconds': min(processing_times),
            'max_seconds': max(processing_times),
            'completed_count': len(processing_times)
        }
    
    return {
        'total_oficios': total,
        'by_status': status_counts,
        'by_ocr_status': ocr_status_counts,
        'by_crm_status': crm_status_counts,
        'processing_times': time_stats,
        'completion_percentage': {
            'completed': (status_counts.get('completed', 0) / total) * 100,
            'failed': (status_counts.get('error', 0) + status_counts.get('crm_error', 0)) / total * 100,
            'pending': (status_counts.get('pending', 0) + status_counts.get('processing', 0)) / total * 100
        }
    }

def format_oficios_for_response(oficios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Formatea lista de oficios para la respuesta
    """
    formatted_oficios = []
    
    for oficio in oficios:
        formatted_oficio = {
            'oficio_id': oficio.get('oficio_id'),
            'sequence_number': oficio.get('sequence_number'),
            'status': oficio.get('status'),
            'ocr_status': oficio.get('ocr_status'),
            'crm_status': oficio.get('crm_status'),
            'created_at': oficio.get('created_at'),
            'updated_at': oficio.get('updated_at'),
            'completed_at': oficio.get('completed_at'),
            'crm_details': oficio.get('crm_details'),
            'error_message': oficio.get('error_message')
        }
        
        # Agregar información adicional si está disponible
        if 'ocr_completed_at' in oficio:
            formatted_oficio['ocr_completed_at'] = oficio['ocr_completed_at']
        
        if 'crm_id' in oficio:
            formatted_oficio['crm_id'] = oficio['crm_id']
        
        formatted_oficios.append(formatted_oficio)
    
    # Ordenar por número de secuencia
    formatted_oficios.sort(key=lambda x: x.get('sequence_number', 0))
    
    return formatted_oficios

def calculate_progress_info(batch_summary: Dict[str, Any], stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcula información de progreso del lote
    """
    total = batch_summary.get('total_oficios', 0)
    
    if total == 0:
        return {'percentage': 0, 'phase': 'unknown', 'estimated_completion': None}
    
    completed = stats['by_status'].get('completed', 0)
    processing = stats['by_status'].get('processing', 0)
    pending = stats['by_status'].get('pending', 0)
    failed = stats['by_status'].get('error', 0) + stats['by_status'].get('crm_error', 0)
    
    percentage = ((completed + failed) / total) * 100
    
    # Determinar fase actual
    if percentage >= 100:
        phase = 'completed'
    elif processing > 0:
        phase = 'processing'
    elif pending > 0:
        phase = 'queued'
    else:
        phase = 'unknown'
    
    # Estimar tiempo de finalización
    estimated_completion = None
    if processing > 0 and 'processing_times' in stats and stats['processing_times']:
        avg_time = stats['processing_times'].get('average_seconds', 300)  # Default 5 min
        remaining_jobs = pending + processing
        estimated_seconds = remaining_jobs * avg_time
        estimated_completion = datetime.utcnow().timestamp() + estimated_seconds
    
    return {
        'percentage': round(percentage, 1),
        'phase': phase,
        'completed': completed,
        'processing': processing,
        'pending': pending,
        'failed': failed,
        'estimated_completion': estimated_completion
    }

def generate_timeline(batch_summary: Dict[str, Any], oficios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Genera timeline de eventos del lote
    """
    events = []
    
    # Evento de creación del lote
    if 'created_at' in batch_summary:
        events.append({
            'timestamp': batch_summary['created_at'],
            'event': 'batch_created',
            'description': f"Lote creado con {batch_summary.get('total_oficios', 0)} oficios",
            'details': batch_summary.get('email_metadata', {})
        })
    
    # Eventos de inicio de procesamiento
    if 'processing_started_at' in batch_summary:
        events.append({
            'timestamp': batch_summary['processing_started_at'],
            'event': 'processing_started',
            'description': "Iniciado procesamiento OCR"
        })
    
    # Eventos de completitud de oficios (solo primeros y últimos)
    completed_oficios = [o for o in oficios if o.get('status') == 'completed' and 'completed_at' in o]
    completed_oficios.sort(key=lambda x: x['completed_at'])
    
    if completed_oficios:
        # Primer oficio completado
        first_completed = completed_oficios[0]
        events.append({
            'timestamp': first_completed['completed_at'],
            'event': 'first_oficio_completed',
            'description': f"Primer oficio completado: {first_completed['oficio_id']}"
        })
        
        # Último oficio completado (si es diferente)
        if len(completed_oficios) > 1:
            last_completed = completed_oficios[-1]
            events.append({
                'timestamp': last_completed['completed_at'],
                'event': 'last_oficio_completed',
                'description': f"Último oficio completado: {last_completed['oficio_id']}"
            })
    
    # Evento de completitud del lote
    if 'completed_at' in batch_summary:
        events.append({
            'timestamp': batch_summary['completed_at'],
            'event': 'batch_completed',
            'description': f"Lote completado con {batch_summary.get('completion_rate', 0)}% de éxito"
        })
    
    # Ordenar eventos por timestamp
    events.sort(key=lambda x: x['timestamp'])
    
    return events

def get_error_summary(oficios: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Obtiene resumen de errores del lote
    """
    errors = []
    error_counts = {}
    
    for oficio in oficios:
        if oficio.get('status') in ['error', 'crm_error']:
            error_msg = oficio.get('error_message', 'Unknown error')
            
            error_entry = {
                'oficio_id': oficio['oficio_id'],
                'error_type': oficio.get('status'),
                'error_message': error_msg,
                'timestamp': oficio.get('updated_at')
            }
            errors.append(error_entry)
            
            # Contar tipos de error
            error_type = error_msg.split(':')[0] if ':' in error_msg else error_msg
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
    
    return {
        'total_errors': len(errors),
        'error_details': errors[:10],  # Primeros 10 errores
        'error_types': error_counts,
        'has_more_errors': len(errors) > 10
    }

def create_cors_response():
    """
    Create CORS preflight response
    """
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Access-Control-Max-Age': '86400'
        },
        'body': json.dumps({'message': 'CORS preflight OK'})
    }

def convert_decimals(obj):
    """
    Convierte objetos Decimal a tipos nativos de Python para serialización JSON
    """
    if isinstance(obj, Decimal):
        # Si es un número entero, convertir a int, sino a float
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    else:
        return obj

def create_error_response(status_code: int, error_message: str) -> Dict[str, Any]:
    """
    Crea respuesta de error estandarizada
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