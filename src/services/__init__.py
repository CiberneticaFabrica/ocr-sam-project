# src/services/__init__.py
"""
Services package for OCR SAM Project v2.0

This package contains all business logic services:
- PDFService: Handle PDF operations
- MetadataService: Extract metadata from documents  
- BatchService: Manage batch operations
- QueueService: Handle SQS operations
- OCRService: Text extraction from PDFs
- MistralService: AI text analysis
- StorageService: S3 storage operations
- TrackingService: DynamoDB tracking operations
"""

from .pdf_service import PDFService
from .metadata_service import MetadataService
from .batch_service import BatchService
from .queue_service import QueueService
from .ocr_service import OCRService, OCRResult
from .mistral_service import MistralService, MistralResult
from .storage_service import StorageService
from .tracking_service import TrackingService

__all__ = [
    'PDFService',
    'MetadataService', 
    'BatchService',
    'QueueService',
    'OCRService',
    'OCRResult',
    'MistralService',
    'MistralResult',
    'StorageService',
    'TrackingService'
]

__version__ = '2.0.0'
