# src/shared/config.py
import os
from typing import Optional

class Config:
    """Centralized configuration management"""
    
    def __init__(self):
        self.ENVIRONMENT = os.getenv('ENVIRONMENT', 'dev')
        self.S3_BUCKET = os.getenv('S3_BUCKET_NAME', 'ocr-legal-documents-dev')
        self.OCR_QUEUE_URL = os.getenv('OCR_QUEUE_URL')
        self.CRM_QUEUE_URL = os.getenv('CRM_QUEUE_URL')
        self.BATCH_TRACKING_TABLE = os.getenv('BATCH_TRACKING_TABLE', 'OCRBatchTracking')
        self.JOB_TRACKING_TABLE = os.getenv('JOB_TRACKING_TABLE', 'OCRJobTracking')
        self.MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')
        self.CREATIO_URL = os.getenv('CREATIO_URL')
        self.CREATIO_USERNAME = os.getenv('CREATIO_USERNAME')
        self.CREATIO_PASSWORD = os.getenv('CREATIO_PASSWORD')
        
        # Validation
        self._validate_required_config()
    
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get configuration value with default fallback"""
        return os.getenv(key, default)
    
    def _validate_required_config(self):
        """Validate that required configuration is present"""
        required_vars = ['S3_BUCKET_NAME']  # Only S3_BUCKET is truly required
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if missing:
            raise ValueError(f"Missing required environment variables: {missing}")
        
        # Log warnings for optional but important variables
        optional_vars = ['OCR_QUEUE_URL', 'MISTRAL_API_KEY', 'CRM_QUEUE_URL']
        missing_optional = [var for var in optional_vars if not os.getenv(var)]
        
        if missing_optional:
            print(f"⚠️  Warning: Optional environment variables not set: {missing_optional}")
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == 'prod'
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == 'dev'






