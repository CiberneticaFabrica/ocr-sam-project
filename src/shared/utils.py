# src/shared/utils.py
import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, Optional

class ResponseFormatter:
    """Utility class for formatting Lambda responses"""
    
    @staticmethod
    def success_response(data: Dict[str, Any], status_code: int = 200) -> Dict[str, Any]:
        """Format successful response"""
        return {
            'statusCode': status_code,
            'body': json.dumps(data, ensure_ascii=False, default=str)
        }
    
    @staticmethod
    def error_response(error_message: str, status_code: int = 400) -> Dict[str, Any]:
        """Format error response"""
        return {
            'statusCode': status_code,
            'body': json.dumps({
                'error': error_message,
                'timestamp': datetime.utcnow().isoformat()
            }, ensure_ascii=False)
        }

class Logger:
    """Utility class for logging operations"""
    
    @staticmethod
    def setup_logger(name: str) -> logging.Logger:
        """Setup logger with consistent configuration"""
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        return logger
    
    @staticmethod
    def log_success(logger: logging.Logger, message: str, data: Dict[str, Any] = None):
        """Log success message with optional data"""
        if data:
            logger.info(f"✅ {message} - {json.dumps(data, default=str)}")
        else:
            logger.info(f"✅ {message}")
    
    @staticmethod
    def log_error(logger: logging.Logger, message: str, error: Exception = None):
        """Log error message with optional exception"""
        if error:
            logger.error(f"❌ {message} - {str(error)}")
        else:
            logger.error(f"❌ {message}")
    
    @staticmethod
    def log_processing_step(logger: logging.Logger, message: str, data: Dict[str, Any] = None):
        """Log processing step with optional data"""
        if data:
            logger.info(f"🔄 {message} - {json.dumps(data, default=str)}")
        else:
            logger.info(f"🔄 {message}")

class TextCleaner:
    """Utility class for text cleaning operations"""
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep basic punctuation
        text = re.sub(r'[^\w\s.,;:!?()-]', '', text)
        
        return text.strip()
    
    @staticmethod
    def extract_numbers(text: str) -> list:
        """Extract numbers from text"""
        numbers = re.findall(r'\d+', text)
        return [int(num) for num in numbers]
    
    @staticmethod
    def normalize_company_name(name: str) -> str:
        """Normalize company name"""
        if not name:
            return "No especificado"
        
        # Remove common prefixes/suffixes
        name = re.sub(r'^(s\.?a\.?|s\.?r\.?l\.?|ltda\.?|inc\.?|corp\.?)\s*', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+(s\.?a\.?|s\.?r\.?l\.?|ltda\.?|inc\.?|corp\.?)$', '', name, flags=re.IGNORECASE)
        
        return name.strip().title()
    
    @staticmethod
    def clean_value(value: Any) -> str:
        """Clean and normalize any value"""
        if value is None:
            return ""
        
        if isinstance(value, (int, float)):
            return str(value)
        
        if isinstance(value, str):
            return TextCleaner.clean_text(value)
        
        return str(value).strip()
    
    @staticmethod
    def extract_currency(text: str) -> str:
        """Extract currency value from text"""
        if not text:
            return ""
        
        # Look for currency patterns
        currency_patterns = [
            r'\$[\d,]+\.?\d*',  # $1,234.56
            r'[\d,]+\.?\d*\s*pesos',  # 1,234.56 pesos
            r'[\d,]+\.?\d*\s*usd',  # 1,234.56 usd
        ]
        
        for pattern in currency_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                return matches[0]
        
        return text.strip()
    
    @staticmethod
    def extract_date(text: str) -> Optional[str]:
        """Extract date from text"""
        if not text:
            return None
        
        # Common date patterns
        date_patterns = [
            r'\d{1,2}/\d{1,2}/\d{4}',  # DD/MM/YYYY
            r'\d{4}-\d{1,2}-\d{1,2}',  # YYYY-MM-DD
            r'\d{1,2}-\d{1,2}-\d{4}',  # DD-MM-YYYY
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        
        return None