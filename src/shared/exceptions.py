# src/shared/exceptions.py
"""
Custom exceptions for OCR SAM Project v2.0
"""

class OCRBaseException(Exception):
    """Base exception for OCR processing"""
    pass

class PDFProcessingError(OCRBaseException):
    """Raised when PDF processing fails"""
    pass

class ValidationError(OCRBaseException):
    """Raised when validation fails"""
    pass

class MetadataExtractionError(OCRBaseException):
    """Raised when metadata extraction fails"""
    pass

class QueueError(OCRBaseException):
    """Raised when queue operations fail"""
    pass

class CRMIntegrationError(OCRBaseException):
    """Raised when CRM integration fails"""
    pass

class OCRExtractionError(OCRBaseException):
    """Raised when OCR text extraction fails"""
    pass

class MistralAPIError(OCRBaseException):
    """Raised when Mistral AI API fails"""
    pass

class StorageError(OCRBaseException):
    """Raised when storage operations fail"""
    pass

class TrackingError(OCRBaseException):
    """Raised when tracking operations fail"""
    pass