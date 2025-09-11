import json
import logging
from datetime import datetime
from typing import Dict, Any

from services.tracking_service import TrackingService
from services.storage_service import StorageService
from shared.config import Config
from shared.utils import ResponseFormatter, Logger
from shared.exceptions import JobNotFoundError

# Setup logging
logger = Logger.setup_logger(__name__)
config = Config()

# Initialize services
tracking_service = TrackingService()
storage_service = StorageService()

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function para consultar el estado de trabajos OCR
    Refactored to use new services architecture
    """
    try:
        Logger.log_processing_step(logger, "Status request received", {'event': event})
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return ResponseFormatter.cors_response()
        
        # Extract job_id
        job_id = extract_job_id_from_event(event)
        
        if not job_id:
            return ResponseFormatter.error_response('job_id es requerido', 400)
        
        Logger.log_processing_step(logger, f"Consultando estado del trabajo", {'job_id': job_id})
        
        # Get job status using services
        job_status = tracking_service.get_job_status(job_id)
        
        if not job_status:
            return ResponseFormatter.error_response(f'No se encontró el trabajo: {job_id}', 404)
        
        Logger.log_success(logger, f"Job status retrieved", {
            'job_id': job_id,
            'status': job_status.get('status', 'unknown')
        })
        
        return ResponseFormatter.success_response(job_status)
        
    except JobNotFoundError as e:
        Logger.log_error(logger, f"Job not found", {'job_id': job_id, 'error': str(e)})
        return ResponseFormatter.error_response(f'No se encontró el trabajo: {job_id}', 404)
        
    except Exception as e:
        Logger.log_error(logger, f"Error consultando estado", {'error': str(e)})
        return ResponseFormatter.error_response(f"Error interno: {str(e)}", 500)

def extract_job_id_from_event(event: Dict[str, Any]) -> str:
    """
    Extract job_id from various possible locations in the event
    """
    # Try path parameters first
    if 'pathParameters' in event and event['pathParameters']:
        job_id = event['pathParameters'].get('job_id')
        if job_id:
            return job_id
    
    # Try query string parameters
    if 'queryStringParameters' in event and event['queryStringParameters']:
        job_id = event['queryStringParameters'].get('job_id')
        if job_id:
            return job_id
    
    # Try extracting from path directly
    path = event.get('path', '')
    if '/status/' in path:
        parts = path.split('/status/')
        if len(parts) > 1:
            return parts[1].strip('/')
    
    return None

# All status checking and response logic is now handled by services