# src/services/__init__.py - VERSIÓN ACTUALIZADA
"""
Services package for OCR SAM Project v2.1

This package contains all business logic services:
- PDFService: Handle PDF operations and splitting
- MetadataService: Extract metadata from documents  
- BatchService: Manage batch operations
- QueueService: Handle SQS operations
- OCRService: Enhanced OCR with integrated Mistral AI (PRIMARY OCR SERVICE)
- MistralService: Text-only analysis and chat completions (COMPLEMENTARY)
- StorageService: S3 storage operations
- TrackingService: DynamoDB tracking operations
"""

from .pdf_service import PDFService
from .metadata_service import MetadataService
from .batch_service import BatchService
from .queue_service import QueueService
from .ocr_service import OCRService, OCRResult  # Enhanced version
from .mistral_service import MistralService, MistralResult  # Text-only version
from .storage_service import StorageService
from .tracking_service import TrackingService

# Clean services - no hybrid OCR

__all__ = [
    'PDFService',
    'MetadataService', 
    'BatchService',
    'QueueService',
    'OCRService',        # Enhanced OCR with integrated AI
    'OCRResult',         # Enhanced result class
    'MistralService',    # Text-only analysis service
    'MistralResult',     # Text analysis result class
    'StorageService',
    'TrackingService'
]

__version__ = '2.1.0'

# Service compatibility notes:
# - OCRService: Primary service for PDF OCR + AI analysis
# - MistralService: Complementary service for text-only analysis
# - All other services remain unchanged