# src/services/queue_service.py
import boto3
import json
import logging
from datetime import datetime
from typing import List, Dict, Any

from shared.config import Config

logger = logging.getLogger(__name__)
config = Config()

class QueueService:
    """Service for managing SQS operations"""
    
    def __init__(self):
        self.sqs_client = boto3.client('sqs')
    
    def send_oficios_to_processing(self, oficios: List[Dict[str, Any]], 
                                 batch_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Send oficios to OCR processing queue"""
        try:
            logger.info(f"📤 Sending {len(oficios)} oficios to processing queue")
            
            sent_count = 0
            failed_count = 0
            
            for oficio in oficios:
                try:
                    # Create message for SQS
                    message_data = {
                        'job_id': oficio['oficio_id'],
                        'batch_id': batch_id,
                        'oficio_data': oficio,
                        'batch_metadata': metadata,
                        'created_at': datetime.utcnow().isoformat(),
                        'source': 's3_direct'
                    }
                    
                    # Send to SQS
                    response = self.sqs_client.send_message(
                        QueueUrl=config.OCR_QUEUE_URL,
                        MessageBody=json.dumps(message_data, ensure_ascii=False),
                        MessageAttributes={
                            'BatchId': {
                                'StringValue': batch_id,
                                'DataType': 'String'
                            },
                            'OficioId': {
                                'StringValue': oficio['oficio_id'],
                                'DataType': 'String'
                            },
                            'Source': {
                                'StringValue': 's3_direct',
                                'DataType': 'String'
                            }
                        }
                    )
                    
                    sent_count += 1
                    logger.debug(f"📤 Sent: {oficio['oficio_id']}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to send {oficio['oficio_id']}: {str(e)}")
                    failed_count += 1
            
            result = {
                'sent_count': sent_count,
                'failed_count': failed_count,
                'total_count': len(oficios),
                'success_rate': sent_count / len(oficios) if oficios else 0
            }
            
            logger.info(f"📊 Queue result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error sending to queue: {str(e)}")
            raise