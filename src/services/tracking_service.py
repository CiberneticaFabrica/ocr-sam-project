# src/services/tracking_service.py
import boto3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from boto3.dynamodb.conditions import Key

from shared.config import Config
from shared.exceptions import OCRBaseException

logger = logging.getLogger(__name__)
config = Config()

class TrackingService:
    """Service for tracking jobs and batches in DynamoDB"""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.batch_table = self.dynamodb.Table(config.BATCH_TRACKING_TABLE)
        self.job_table = self.dynamodb.Table(config.JOB_TRACKING_TABLE)
    
    def update_job_status(self, job_id: str, status: str, message: Optional[str] = None) -> None:
        """Update job status in DynamoDB"""
        try:
            update_data = {
                'status': status,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            if message:
                update_data['status_message'] = message
            
            if status == 'completed':
                update_data['completed_at'] = datetime.utcnow().isoformat()
            elif status == 'error':
                update_data['error_at'] = datetime.utcnow().isoformat()
            
            # Build update expression
            update_expr = 'SET #status = :status, updated_at = :updated'
            expr_names = {'#status': 'status'}
            expr_values = {
                ':status': status,
                ':updated': update_data['updated_at']
            }
            
            if message:
                update_expr += ', status_message = :message'
                expr_values[':message'] = message
            
            if 'completed_at' in update_data:
                update_expr += ', completed_at = :completed'
                expr_values[':completed'] = update_data['completed_at']
            
            if 'error_at' in update_data:
                update_expr += ', error_at = :error_time'
                expr_values[':error_time'] = update_data['error_at']
            
            self.job_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values
            )
            
            logger.info(f"📊 Job {job_id} status updated: {status}")
            
        except Exception as e:
            logger.error(f"❌ Failed to update job status: {str(e)}")
            # Don't raise exception to avoid breaking main flow
    
    def get_job_data(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job data from DynamoDB"""
        try:
            response = self.job_table.get_item(Key={'job_id': job_id})
            return response.get('Item')
        except Exception as e:
            logger.error(f"❌ Failed to get job data: {str(e)}")
            return None
    
    def update_batch_progress(self, batch_id: str) -> None:
        """Update batch progress based on job statuses"""
        try:
            # Get all jobs for this batch
            response = self.job_table.query(
                IndexName='BatchIndex',
                KeyConditionExpression=Key('batch_id').eq(batch_id)
            )
            
            jobs = response.get('Items', [])
            if not jobs:
                return
            
            # Calculate statistics
            total_jobs = len(jobs)
            completed_jobs = len([j for j in jobs if j.get('status') == 'completed'])
            error_jobs = len([j for j in jobs if j.get('status') == 'error'])
            processing_jobs = len([j for j in jobs if j.get('status') in ['processing', 'ocr_processing']])
            
            # Determine batch status
            if completed_jobs == total_jobs:
                batch_status = 'completed'
                status_message = f'All {total_jobs} oficios completed successfully'
            elif error_jobs > 0 and (completed_jobs + error_jobs) == total_jobs:
                batch_status = 'partial_completion'
                status_message = f'{completed_jobs} completed, {error_jobs} failed'
            elif processing_jobs > 0:
                batch_status = 'processing'
                status_message = f'{completed_jobs}/{total_jobs} completed, {processing_jobs} processing'
            else:
                batch_status = 'queued'
                status_message = f'{total_jobs} oficios queued for processing'
            
            # Update batch
            self.batch_table.update_item(
                Key={'batch_id': batch_id},
                UpdateExpression='''
                    SET batch_status = :status, 
                        status_message = :message,
                        oficios_count = :total,
                        completed_count = :completed,
                        error_count = :errors,
                        processing_count = :processing,
                        last_updated = :updated
                ''',
                ExpressionAttributeValues={
                    ':status': batch_status,
                    ':message': status_message,
                    ':total': total_jobs,
                    ':completed': completed_jobs,
                    ':errors': error_jobs,
                    ':processing': processing_jobs,
                    ':updated': datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"📊 Batch {batch_id} progress updated: {batch_status}")
            
        except Exception as e:
            logger.error(f"❌ Failed to update batch progress: {str(e)}")