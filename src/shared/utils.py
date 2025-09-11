# src/shared/utils.py
import re
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

class TextCleaner:
    """Utility for cleaning and normalizing text"""
    
    @staticmethod
    def clean_value(value: Any) -> str:
        """Clean and normalize text value"""
        if value is None:
            return ""
        
        # Convert to string
        text = str(value).strip()
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters (keep basic punctuation)
        text = re.sub(r'[^\w\s\-.,;:()áéíóúÁÉÍÓÚñÑ]', '', text)
        
        # Capitalize properly
        if text and len(text) > 3:
            text = text.title()
        
        return text
    
    @staticmethod
    def extract_currency(text: str) -> Optional[float]:
        """Extract currency amount from text"""
        try:
            # Remove currency symbols and normalize
            cleaned = re.sub(r'[B/.\$,\s]', '', text)
            cleaned = re.sub(r'[^\d.]', '', cleaned)
            
            if cleaned:
                return float(cleaned)
            return None
            
        except:
            return None
    
    @staticmethod
    def extract_date(text: str) -> Optional[str]:
        """Extract and normalize date from text"""
        try:
            # Common date patterns
            patterns = [
                r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # DD/MM/YYYY or DD-MM-YYYY
                r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # YYYY/MM/DD or YYYY-MM-DD
                r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',  # DD de Month de YYYY
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    # Return normalized format YYYY-MM-DD
                    groups = match.groups()
                    if len(groups) == 3:
                        if pattern.startswith(r'(\d{4})'):  # YYYY-MM-DD
                            return f"{groups[0]}-{groups[1]:0>2}-{groups[2]:0>2}"
                        else:  # DD-MM-YYYY
                            return f"{groups[2]}-{groups[1]:0>2}-{groups[0]:0>2}"
            
            return None
            
        except:
            return None

class ResponseFormatter:
    """Utility for formatting API responses"""
    
    @staticmethod
    def success_response(data: Any, message: str = "Success") -> Dict[str, Any]:
        """Format successful response"""
        return {
            'statusCode': 200,
            'body': json.dumps({
                'status': 'success',
                'message': message,
                'data': data,
                'timestamp': datetime.utcnow().isoformat()
            }, ensure_ascii=False, default=str)
        }
    
    @staticmethod
    def error_response(error: str, status_code: int = 400, details: Dict = None) -> Dict[str, Any]:
        """Format error response"""
        response_body = {
            'status': 'error',
            'error': error,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if details:
            response_body['details'] = details
        
        return {
            'statusCode': status_code,
            'body': json.dumps(response_body, ensure_ascii=False, default=str)
        }
    
    @staticmethod
    def batch_status_response(batch_data: Dict, oficios_data: List[Dict]) -> Dict[str, Any]:
        """Format batch status response"""
        # Calculate statistics
        total_oficios = len(oficios_data)
        completed = len([o for o in oficios_data if o.get('status') == 'completed'])
        processing = len([o for o in oficios_data if o.get('status') == 'processing'])
        failed = len([o for o in oficios_data if o.get('status') == 'error'])
        
        progress_percentage = (completed / total_oficios * 100) if total_oficios > 0 else 0
        
        return ResponseFormatter.success_response({
            'batch_info': batch_data,
            'statistics': {
                'total_oficios': total_oficios,
                'completed': completed,
                'processing': processing,
                'failed': failed,
                'progress_percentage': round(progress_percentage, 2)
            },
            'oficios': oficios_data
        })

class IDGenerator:
    """Utility for generating unique IDs"""
    
    @staticmethod
    def generate_batch_id() -> str:
        """Generate unique batch ID"""
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        import uuid
        unique_part = str(uuid.uuid4())[:8]
        return f"batch_{timestamp}_{unique_part}"
    
    @staticmethod
    def generate_job_id(batch_id: str, oficio_number: int) -> str:
        """Generate job ID for oficio"""
        return f"{batch_id}_oficio_{oficio_number:03d}"
    
    @staticmethod
    def generate_s3_key(batch_id: str, oficio_id: str, file_type: str = 'pdf') -> str:
        """Generate S3 key for storing files"""
        return f"oficios/lotes/{batch_id}/{oficio_id}.{file_type}"

class Logger:
    """Enhanced logging utility"""
    
    @staticmethod
    def setup_logger(name: str, level: str = 'INFO') -> logging.Logger:
        """Setup structured logger"""
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper()))
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Create handler if not exists
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    @staticmethod
    def log_processing_step(logger: logging.Logger, step: str, details: Dict = None):
        """Log processing step with structured data"""
        message = f"🔄 {step}"
        if details:
            message += f" - {json.dumps(details, default=str)}"
        logger.info(message)
    
    @staticmethod
    def log_error(logger: logging.Logger, error: str, context: Dict = None):
        """Log error with context"""
        message = f"❌ {error}"
        if context:
            message += f" - Context: {json.dumps(context, default=str)}"
        logger.error(message)
    
    @staticmethod
    def log_success(logger: logging.Logger, message: str, metrics: Dict = None):
        """Log success with metrics"""
        log_message = f"✅ {message}"
        if metrics:
            log_message += f" - Metrics: {json.dumps(metrics, default=str)}"
        logger.info(log_message)