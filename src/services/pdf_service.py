# src/services/pdf_service.py
import fitz  # PyMuPDF
import boto3
import json
import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime
import uuid

from shared.exceptions import PDFProcessingError
from shared.config import Config

logger = logging.getLogger(__name__)
config = Config()

class PDFService:
    """Service for handling PDF operations"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
    
    def download_from_s3(self, bucket: str, key: str) -> bytes:
        """Download PDF content from S3"""
        try:
            logger.info(f"📥 Downloading PDF from s3://{bucket}/{key}")
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read()
            
            logger.info(f"📄 PDF downloaded: {len(content)} bytes")
            return content
            
        except Exception as e:
            raise PDFProcessingError(f"Failed to download PDF: {str(e)}")
    
    def split_into_oficios(self, pdf_content: bytes, batch_id: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split PDF into individual oficios"""
        try:
            logger.info("✂️ Starting PDF split into oficios")
            
            # Open PDF document
            pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            # Skip first page if it contains metadata/config
            start_page = 1 if self._has_config_page(pdf_doc) else 0
            
            oficios = []
            oficios_per_page = metadata.get('oficios_per_page', 1)
            
            # Split by pages (configurable oficios per page)
            current_page = start_page
            oficio_number = 1
            
            while current_page < pdf_doc.page_count:
                end_page = min(current_page + oficios_per_page, pdf_doc.page_count)
                
                # Create individual oficio
                oficio_doc = fitz.open()
                for page_num in range(current_page, end_page):
                    oficio_doc.insert_pdf(pdf_doc, from_page=page_num, to_page=page_num)
                
                # Generate oficio data
                oficio_data = {
                    'oficio_id': f"{batch_id}_oficio_{oficio_number:03d}",
                    'batch_id': batch_id,
                    'oficio_number': oficio_number,
                    'page_range': [current_page, end_page - 1],
                    'total_pages': end_page - current_page,
                    'pdf_content': oficio_doc.write(),
                    'created_at': datetime.utcnow().isoformat()
                }
                
                oficios.append(oficio_data)
                oficio_doc.close()
                
                current_page = end_page
                oficio_number += 1
            
            pdf_doc.close()
            
            logger.info(f"✅ PDF split completed: {len(oficios)} oficios created")
            return oficios
            
        except Exception as e:
            raise PDFProcessingError(f"Failed to split PDF: {str(e)}")
    
    def _has_config_page(self, pdf_doc) -> bool:
        """Check if first page contains configuration data"""
        try:
            if pdf_doc.page_count < 2:
                return False
                
            first_page = pdf_doc[0]
            text = first_page.get_text().lower()
            
            # Look for configuration keywords
            config_keywords = ['cantidad_oficios', 'empresa', 'configuración', 'lote']
            return any(keyword in text for keyword in config_keywords)
            
        except:
            return False
    
    def store_oficios_in_s3(self, oficios: List[Dict[str, Any]], batch_id: str) -> List[Dict[str, Any]]:
        """Store individual oficios in S3"""
        try:
            stored_oficios = []
            
            for oficio in oficios:
                # Generate S3 key
                s3_key = f"oficios/lotes/{batch_id}/{oficio['oficio_id']}.pdf"
                
                # Upload to S3
                self.s3_client.put_object(
                    Bucket=config.S3_BUCKET,
                    Key=s3_key,
                    Body=oficio['pdf_content'],
                    ContentType='application/pdf',
                    Metadata={
                        'batch_id': batch_id,
                        'oficio_id': oficio['oficio_id'],
                        'oficio_number': str(oficio['oficio_number']),
                        'total_pages': str(oficio['total_pages'])
                    }
                )
                
                # Remove PDF content from memory and add S3 reference
                stored_oficio = {
                    **oficio,
                    's3_bucket': config.S3_BUCKET,
                    's3_key': s3_key,
                    's3_uri': f"s3://{config.S3_BUCKET}/{s3_key}"
                }
                del stored_oficio['pdf_content']  # Remove binary content
                
                stored_oficios.append(stored_oficio)
                
                logger.info(f"📤 Stored oficio: {oficio['oficio_id']}")
            
            logger.info(f"✅ All oficios stored in S3: {len(stored_oficios)} files")
            return stored_oficios
            
        except Exception as e:
            raise PDFProcessingError(f"Failed to store oficios: {str(e)}")








