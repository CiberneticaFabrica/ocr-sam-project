# src/services/storage_service.py
import boto3
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from shared.config import Config
from shared.exceptions import OCRBaseException

logger = logging.getLogger(__name__)
config = Config()

class StorageService:
    """Service for handling S3 storage operations"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.bucket = config.S3_BUCKET
    
    def download_oficio_pdf(self, oficio_data: Dict[str, Any]) -> bytes:
        """Download oficio PDF from S3"""
        try:
            s3_key = oficio_data.get('s3_key')
            if not s3_key:
                raise OCRBaseException("No S3 key found in oficio data")
            
            logger.info(f"📥 Downloading oficio PDF: {s3_key}")
            
            response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
            content = response['Body'].read()
            
            logger.info(f"✅ Downloaded {len(content)} bytes")
            return content
            
        except Exception as e:
            raise OCRBaseException(f"Failed to download oficio PDF: {str(e)}")
    
    def download_job_pdf(self, job_id: str) -> bytes:
        """Download job PDF for individual processing"""
        try:
            # Try common patterns for job PDFs
            possible_keys = [
                f"jobs/{job_id}/input.pdf",
                f"jobs/{job_id}.pdf",
                f"oficios/{job_id}.pdf"
            ]
            
            for key in possible_keys:
                try:
                    logger.info(f"📥 Trying to download: {key}")
                    response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                    content = response['Body'].read()
                    logger.info(f"✅ Downloaded {len(content)} bytes from {key}")
                    return content
                except self.s3_client.exceptions.NoSuchKey:
                    continue
            
            raise OCRBaseException(f"No PDF found for job {job_id}")
            
        except Exception as e:
            raise OCRBaseException(f"Failed to download job PDF: {str(e)}")
    
    def save_ocr_result(self, job_id: str, result_data: Dict[str, Any]) -> str:
        """Save OCR result to S3"""
        try:
            # Generate S3 key
            s3_key = f"jobs/{job_id}/result.json"
            
            # Add metadata
            result_with_metadata = {
                **result_data,
                'job_id': job_id,
                'saved_at': datetime.utcnow().isoformat(),
                'version': '2.0'
            }
            
            # Save to S3
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=json.dumps(result_with_metadata, ensure_ascii=False, indent=2),
                ContentType='application/json',
                Metadata={
                    'job_id': job_id,
                    'result_type': 'ocr_analysis',
                    'saved_at': datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"💾 Saved OCR result: s3://{self.bucket}/{s3_key}")
            return s3_key
            
        except Exception as e:
            raise OCRBaseException(f"Failed to save OCR result: {str(e)}")
    
    def load_ocr_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load OCR result from S3"""
        try:
            s3_key = f"jobs/{job_id}/result.json"
            
            response = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
            content = response['Body'].read()
            
            result = json.loads(content)
            logger.info(f"📄 Loaded OCR result for job {job_id}")
            return result
            
        except self.s3_client.exceptions.NoSuchKey:
            logger.warning(f"⚠️ No OCR result found for job {job_id}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to load OCR result: {str(e)}")
            return None