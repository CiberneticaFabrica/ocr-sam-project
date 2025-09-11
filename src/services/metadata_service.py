# src/services/metadata_service.py
import fitz
import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from shared.exceptions import ValidationError

logger = logging.getLogger(__name__)

class MetadataService:
    """Service for extracting metadata from PDFs"""
    
    def extract_from_pdf_first_page(self, pdf_content: bytes) -> Dict[str, Any]:
        """Extract metadata from first page of PDF"""
        try:
            logger.info("📋 Extracting metadata from PDF first page")
            
            # Open PDF and get first page
            pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            if pdf_doc.page_count == 0:
                raise ValidationError("PDF is empty")
            
            first_page = pdf_doc[0]
            text = first_page.get_text()
            
            # Extract metadata using patterns
            metadata = self._parse_metadata_text(text)
            
            # Add PDF information
            metadata.update({
                'total_pages': pdf_doc.page_count,
                'pdf_size_bytes': len(pdf_content),
                'extraction_timestamp': datetime.utcnow().isoformat(),
                'source': 's3_direct'
            })
            
            pdf_doc.close()
            
            logger.info(f"📊 Metadata extracted: {metadata}")
            return metadata
            
        except Exception as e:
            logger.error(f"❌ Error extracting metadata: {str(e)}")
            raise ValidationError(f"Metadata extraction failed: {str(e)}")
    
    def _parse_metadata_text(self, text: str) -> Dict[str, Any]:
        """Parse metadata from text using regex patterns"""
        
        # Normalize text
        normalized_text = text.lower().replace('\n', ' ').replace('\r', ' ')
        
        # Define extraction patterns
        patterns = {
            'empresa': [
                r'empresa:\s*([^\n\r]+)',
                r'cliente:\s*([^\n\r]+)',
                r'organizacion:\s*([^\n\r]+)'
            ],
            'cantidad_oficios': [
                r'cantidad_oficios:\s*(\d+)',
                r'cantidad:\s*(\d+)',
                r'total_oficios:\s*(\d+)',
                r'oficios:\s*(\d+)'
            ],
            'origen': [
                r'origen:\s*([^\n\r]+)',
                r'provincia:\s*([^\n\r]+)',
                r'ubicacion:\s*([^\n\r]+)'
            ],
            'observaciones': [
                r'observaciones:\s*([^\n\r]+)',
                r'comentarios:\s*([^\n\r]+)',
                r'notas:\s*([^\n\r]+)'
            ],
            'fecha': [
                r'fecha:\s*([^\n\r]+)',
                r'date:\s*([^\n\r]+)'
            ],
            'operador': [
                r'operador:\s*([^\n\r]+)',
                r'usuario:\s*([^\n\r]+)',
                r'procesado_por:\s*([^\n\r]+)'
            ]
        }
        
        # Initialize with defaults
        metadata = {
            'empresa': 'No especificado',
            'cantidad_oficios_declarada': 0,
            'origen': 'No especificado',
            'observaciones': 'Procesado automáticamente desde S3',
            'fecha_envio': datetime.utcnow().strftime('%Y-%m-%d'),
            'operador': 'Sistema automático',
            'extraction_success': False
        }
        
        # Extract each field
        extracted_fields = 0
        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, normalized_text, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    
                    if field == 'cantidad_oficios':
                        try:
                            metadata['cantidad_oficios_declarada'] = int(value)
                            extracted_fields += 1
                        except ValueError:
                            continue
                    else:
                        metadata[field] = value
                        extracted_fields += 1
                    break
        
        # Mark as successful if we extracted at least some fields
        metadata['extraction_success'] = extracted_fields > 0
        metadata['extracted_fields_count'] = extracted_fields
        
        return metadata