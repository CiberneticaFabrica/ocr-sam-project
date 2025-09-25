# src/shared/__init__.py
"""
Shared modules for OCR SAM Project v2.0

This package contains shared utilities, configuration, and common functionality:
- Config: Centralized configuration management
- Exceptions: Custom exception classes
- Utils: Utility classes for logging, formatting, and text processing
- Validators: Validation classes for PDFs, metadata, and oficios
"""

from .config import Config
from .exceptions import (
    OCRBaseException,
    PDFProcessingError,
    ValidationError,
    MetadataExtractionError,
    QueueError,
    CRMIntegrationError,
    OCRExtractionError,
    MistralAPIError,
    StorageError,
    TrackingError
)
from .utils import ResponseFormatter, Logger, TextCleaner
from .validators import PDFValidator, OficiosValidator, MetadataValidator, ValidationResult

__all__ = [
    'Config',
    'OCRBaseException',
    'PDFProcessingError',
    'ValidationError',
    'MetadataExtractionError',
    'QueueError',
    'CRMIntegrationError',
    'OCRExtractionError',
    'MistralAPIError',
    'StorageError',
    'TrackingError',
    'ResponseFormatter',
    'Logger',
    'TextCleaner',
    'PDFValidator',
    'OficiosValidator',
    'MetadataValidator',
    'ValidationResult'
]

__version__ = '2.0.0'

