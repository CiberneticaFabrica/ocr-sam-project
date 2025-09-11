# src/services/batch_service.py
import boto3
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from shared.config import Config

logger = logging.getLogger(__name__)
config = Config()

class BatchService:
    """Service for managing batch operations"""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(config.BATCH_TRACKING_TABLE)
    
    def create_batch(self, metadata: Dict[str, Any], source: str = 's3_direct') -> str:
        """Create a new batch for tracking"""
        try:
            batch_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
            
            # Create batch record
            batch_record = {
                'batch_id': batch_id,
                'status': 'processing',
                'source': source,
                'created_at': datetime.utcnow().isoformat(),
                'metadata': metadata,
                'oficios_count': 0,
                'completed_count': 0,
                'error_count': 0,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            # Store in DynamoDB
            self.table.put_item(Item=batch_record)
            
            logger.info(f"📦 Batch created: {batch_id}")
            return batch_id
            
        except Exception as e:
            logger.error(f"❌ Error creating batch: {str(e)}")
            raise
    
    def update_status(self, batch_id: str, status: str, message: Optional[str] = None) -> None:
        """Update batch status"""
        try:
            update_data = {
                'status': status,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            if message:
                update_data['status_message'] = message
            
            # Update in DynamoDB
            self.table.update_item(
                Key={'batch_id': batch_id},
                UpdateExpression='SET #status = :status, last_updated = :updated' + 
                               (', status_message = :message' if message else ''),
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': status,
                    ':updated': update_data['last_updated'],
                    **((':message', message) if message else {})
                }
            )
            
            logger.info(f"📦 Batch {batch_id} status updated: {status}")
            
        except Exception as e:
            logger.error(f"❌ Error updating batch status: {str(e)}")
            raise
    
    def mark_as_failed(self, batch_id: str, error: str) -> None:
        """Mark batch as failed with error"""
        self.update_status(batch_id, 'failed', f'Processing failed: {error}')