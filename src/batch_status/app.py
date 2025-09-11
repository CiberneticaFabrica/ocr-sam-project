# src/batch_status/app.py
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

from services.tracking_service import TrackingService
from services.batch_service import BatchService
from shared.config import Config
from shared.utils import ResponseFormatter, Logger
from shared.exceptions import BatchNotFoundError

# Setup logging
logger = Logger.setup_logger(__name__)
config = Config()

# Initialize services
tracking_service = TrackingService()
batch_service = BatchService()

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Consulta el estado de un lote completo de oficios
    Refactored to use new services architecture
    """
    try:
        Logger.log_processing_step(logger, "Batch status request", {'event': event})
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return ResponseFormatter.cors_response()
        
        # Extract batch_id
        batch_id = extract_batch_id_from_event(event)
        
        if not batch_id:
            return ResponseFormatter.error_response('batch_id es requerido', 400)
        
        Logger.log_processing_step(logger, f"Consultando estado del lote", {'batch_id': batch_id})
        
        # Get batch information using services
        batch_info = batch_service.get_batch_status(batch_id)
        
        if not batch_info:
            return ResponseFormatter.error_response(f'No se encontró el lote: {batch_id}', 404)
        
        Logger.log_success(logger, f"Batch status retrieved", {
            'batch_id': batch_id,
            'total_oficios': batch_info.get('summary', {}).get('total_oficios', 0)
        })
        
        return ResponseFormatter.success_response(batch_info)
        
    except BatchNotFoundError as e:
        Logger.log_error(logger, f"Batch not found", {'batch_id': batch_id, 'error': str(e)})
        return ResponseFormatter.error_response(f'No se encontró el lote: {batch_id}', 404)
        
    except Exception as e:
        Logger.log_error(logger, f"Error consultando estado del lote", {'error': str(e)})
        return ResponseFormatter.error_response(f"Error interno: {str(e)}", 500)

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

# All batch information logic is now handled by BatchService

# All statistics calculation logic is now handled by BatchService

# All formatting, calculation, and response logic is now handled by services