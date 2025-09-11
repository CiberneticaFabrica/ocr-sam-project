# src/document_processor/app.py
import json
import boto3
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from services.pdf_service import PDFService
from services.metadata_service import MetadataService
from services.batch_service import BatchService
from services.queue_service import QueueService
from shared.config import Config
from shared.exceptions import PDFProcessingError, ValidationError
from shared.validators import PDFValidator

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize services
pdf_service = PDFService()
metadata_service = MetadataService()
batch_service = BatchService()
queue_service = QueueService()
config = Config()

@dataclass
class ProcessingResult:
    """Result of PDF processing"""
    success: bool
    batch_id: str
    oficios_count: int
    metadata: Dict[str, Any]
    error: Optional[str] = None

def lambda_handler(event, context) -> Dict[str, Any]:
    """
    Main Lambda handler for S3 document processing
    Simplified and focused on single responsibility
    """
    try:
        logger.info(f"🚀 Starting document processing - Event: {json.dumps(event, default=str)}")
        
        # Extract S3 event information
        s3_events = extract_s3_events(event)
        if not s3_events:
            return create_error_response("No valid S3 events found")
        
        # Process each S3 event
        results = []
        for s3_event in s3_events:
            result = process_single_document(s3_event, context)
            results.append(result)
        
        # Return combined results
        return create_success_response(results)
        
    except Exception as e:
        logger.error(f"❌ Fatal error in lambda_handler: {str(e)}")
        return create_error_response(f"Processing failed: {str(e)}")

def extract_s3_events(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract and validate S3 events from Lambda event"""
    try:
        records = event.get('Records', [])
        s3_events = []
        
        for record in records:
            if record.get('eventSource') == 'aws:s3':
                s3_info = {
                    'bucket': record['s3']['bucket']['name'],
                    'key': record['s3']['object']['key'],
                    'size': record['s3']['object']['size'],
                    'event_name': record['eventName']
                }
                s3_events.append(s3_info)
        
        logger.info(f"📄 Extracted {len(s3_events)} S3 events")
        return s3_events
        
    except Exception as e:
        logger.error(f"❌ Error extracting S3 events: {str(e)}")
        return []

def process_single_document(s3_event: Dict[str, Any], context) -> ProcessingResult:
    """
    Process a single PDF document from S3
    Refactored to be smaller and more focused
    """
    bucket = s3_event['bucket']
    key = s3_event['key']
    
    try:
        logger.info(f"📄 Processing document: s3://{bucket}/{key}")
        
        # Step 1: Download and validate PDF
        pdf_content = pdf_service.download_from_s3(bucket, key)
        PDFValidator.validate_pdf_content(pdf_content)
        
        # Step 2: Extract metadata from first page
        metadata = metadata_service.extract_from_pdf_first_page(pdf_content)
        
        # Step 3: Create batch tracking
        batch_id = batch_service.create_batch(metadata, source='s3_direct')
        
        # Step 4: Split PDF into individual oficios
        oficios = pdf_service.split_into_oficios(pdf_content, batch_id, metadata)
        
        # Step 5: Validate oficios count
        validation_result = validate_oficios_count(oficios, metadata)
        if not validation_result.success:
            batch_service.mark_as_failed(batch_id, validation_result.error)
            return ProcessingResult(False, batch_id, 0, metadata, validation_result.error)
        
        # Step 6: Store oficios in S3
        stored_oficios = pdf_service.store_oficios_in_s3(oficios, batch_id)
        
        # Step 7: Send to processing queue
        queue_result = queue_service.send_oficios_to_processing(stored_oficios, batch_id, metadata)
        
        # Step 8: Update batch status
        batch_service.update_status(batch_id, 'queued_for_processing', 
                                  f"{len(oficios)} oficios enviados a procesamiento")
        
        logger.info(f"✅ Document processed successfully: {len(oficios)} oficios created")
        
        return ProcessingResult(
            success=True,
            batch_id=batch_id,
            oficios_count=len(oficios),
            metadata=metadata
        )
        
    except PDFProcessingError as e:
        logger.error(f"📄 PDF processing error: {str(e)}")
        return ProcessingResult(False, "", 0, {}, f"PDF error: {str(e)}")
        
    except ValidationError as e:
        logger.error(f"✅ Validation error: {str(e)}")
        return ProcessingResult(False, "", 0, {}, f"Validation error: {str(e)}")
        
    except Exception as e:
        logger.error(f"❌ Unexpected error processing document: {str(e)}")
        return ProcessingResult(False, "", 0, {}, f"Processing error: {str(e)}")

def validate_oficios_count(oficios: List[Dict], metadata: Dict[str, Any]) -> 'ValidationResult':
    """Validate extracted oficios count against declared count"""
    from shared.validators import OficiosValidator
    return OficiosValidator.validate_count(oficios, metadata)

def create_success_response(results: List[ProcessingResult]) -> Dict[str, Any]:
    """Create standardized success response"""
    total_oficios = sum(r.oficios_count for r in results if r.success)
    successful_batches = [r.batch_id for r in results if r.success]
    failed_batches = [r for r in results if not r.success]
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'status': 'success',
            'processed_documents': len(results),
            'successful_batches': len(successful_batches),
            'failed_batches': len(failed_batches),
            'total_oficios_created': total_oficios,
            'batch_ids': successful_batches,
            'errors': [{'batch': r.batch_id, 'error': r.error} for r in failed_batches],
            'timestamp': datetime.utcnow().isoformat()
        }, ensure_ascii=False)
    }

def create_error_response(error_message: str) -> Dict[str, Any]:
    """Create standardized error response"""
    return {
        'statusCode': 400,
        'body': json.dumps({
            'status': 'error',
            'error': error_message,
            'timestamp': datetime.utcnow().isoformat()
        }, ensure_ascii=False)
    }