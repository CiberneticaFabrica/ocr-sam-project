# src/services/pdf_service.py
import PyPDF2
import io
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
            logger.info("✂️ Starting PDF split into oficios using separator detection")
            
            # Open PDF document
            pdf_stream = io.BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_stream)
            
            # Find separator pages
            separator_pages = self._find_separator_pages(pdf_reader)
            logger.info(f"🔍 Found {len(separator_pages)} separator pages")
            
            oficios = []
            
            if separator_pages:
                # Split using separator pages
                oficios = self._split_by_separators(pdf_reader, separator_pages, batch_id)
            else:
                # Fallback to page-based splitting
                logger.warning("⚠️ No separators found, falling back to page-based splitting")
                oficios = self._split_by_pages(pdf_reader, batch_id, metadata)
            
            # Validate count
            declared_count = metadata.get('cantidad_oficios_declarada', 0)
            logger.info(f"📊 Validating count - Declared: {declared_count}, Extracted: {len(oficios)}")
            
            logger.info(f"✅ PDF split completed: {len(oficios)} oficios created")
            return oficios
            
        except Exception as e:
            raise PDFProcessingError(f"Failed to split PDF: {str(e)}")
    
    def _find_separator_pages(self, pdf_reader: PyPDF2.PdfReader) -> List[int]:
        """Find pages that act as separators between oficios"""
        try:
            separator_pages = []
            
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text = page.extract_text().lower()
                
                # Look for specific separator patterns
                separator_patterns = [
                    'separador de oficios',
                    '=====================',
                    'separador',
                    'divisor',
                    '---',
                    '==='
                ]
                
                # Check if this page is a separator (not content)
                is_separator = False
                for pattern in separator_patterns:
                    if pattern in text:
                        # Additional check: separator pages are usually short
                        if len(text.strip()) < 200:  # Separator pages are typically short
                            is_separator = True
                            break
                
                if is_separator:
                    separator_pages.append(page_num)
            
            return separator_pages
            
        except Exception as e:
            logger.warning(f"Error finding separators: {str(e)}")
            return []
    
    def _split_by_separators(self, pdf_reader: PyPDF2.PdfReader, separator_pages: List[int], batch_id: str) -> List[Dict[str, Any]]:
        """Split PDF using separator pages"""
        try:
            oficios = []
            oficio_number = 1
            
            # Simple approach: create one oficio per separator
            # Each separator marks the end of one oficio and start of the next
            for i, sep_page in enumerate(separator_pages):
                # Determine start page
                if i == 0:
                    start_page = 0
                else:
                    start_page = separator_pages[i-1] + 1
                
                # Determine end page
                end_page = sep_page
                
                # Only create oficio if there are pages
                if end_page > start_page:
                    oficio_data = self._create_oficio_from_pages(
                        pdf_reader, start_page, end_page, batch_id, oficio_number
                    )
                    oficios.append(oficio_data)
                    oficio_number += 1
            
            # Add final oficio if there are pages after last separator
            if separator_pages and separator_pages[-1] + 1 < len(pdf_reader.pages):
                start_page = separator_pages[-1] + 1
                end_page = len(pdf_reader.pages)
                
                if end_page > start_page:
                    oficio_data = self._create_oficio_from_pages(
                        pdf_reader, start_page, end_page, batch_id, oficio_number
                    )
                    oficios.append(oficio_data)
            
            return oficios
            
        except Exception as e:
            logger.error(f"Error splitting by separators: {str(e)}")
            return []
    
    def _split_by_pages(self, pdf_reader: PyPDF2.PdfReader, batch_id: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Split PDF by pages (fallback method)"""
        try:
            oficios = []
            oficio_number = 1
            oficios_per_page = metadata.get('oficios_per_page', 1)
            
            # Skip first page if it contains metadata/config
            start_page = 1 if self._has_config_page(pdf_reader) else 0
            
            current_page = start_page
            total_pages = len(pdf_reader.pages)
            
            while current_page < total_pages:
                end_page = min(current_page + oficios_per_page, total_pages)
                
                oficio_data = self._create_oficio_from_pages(
                    pdf_reader, current_page, end_page, batch_id, oficio_number
                )
                oficios.append(oficio_data)
                
                current_page = end_page
                oficio_number += 1
            
            return oficios
            
        except Exception as e:
            logger.error(f"Error splitting by pages: {str(e)}")
            return []
    
    def _create_oficio_from_pages(self, pdf_reader: PyPDF2.PdfReader, start_page: int, end_page: int, batch_id: str, oficio_number: int) -> Dict[str, Any]:
        """Create an oficio from a range of pages"""
        try:
            # Create new PDF writer
            pdf_writer = PyPDF2.PdfWriter()
            
            # Add pages to the writer
            for page_num in range(start_page, end_page):
                pdf_writer.add_page(pdf_reader.pages[page_num])
            
            # Write to bytes
            output_stream = io.BytesIO()
            pdf_writer.write(output_stream)
            pdf_content = output_stream.getvalue()
            output_stream.close()
            
            return {
                'oficio_id': f"{batch_id}_oficio_{oficio_number:03d}",
                'batch_id': batch_id,
                'oficio_number': oficio_number,
                'page_range': [start_page, end_page - 1],
                'total_pages': end_page - start_page,
                'pdf_content': pdf_content,
                'created_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating oficio: {str(e)}")
            raise PDFProcessingError(f"Failed to create oficio: {str(e)}")
    
    def _has_config_page(self, pdf_reader: PyPDF2.PdfReader) -> bool:
        """Check if first page contains configuration data"""
        try:
            if len(pdf_reader.pages) < 2:
                return False
                
            first_page = pdf_reader.pages[0]
            text = first_page.extract_text().lower()
            
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








