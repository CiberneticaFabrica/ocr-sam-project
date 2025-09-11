
# src/services/ocr_service.py
import logging
import fitz  # PyMuPDF
from typing import NamedTuple, Dict, Any
from dataclasses import dataclass

from shared.exceptions import OCRBaseException

logger = logging.getLogger(__name__)

@dataclass
class OCRResult:
    """Result of OCR text extraction"""
    success: bool
    text: str = ""
    metadata: Dict[str, Any] = None
    error: str = ""
    confidence: float = 0.0

class OCRService:
    """Service for OCR text extraction from PDFs"""
    
    def __init__(self):
        self.min_text_length = 50  # Minimum text length to consider valid
    
    def extract_text_from_pdf(self, pdf_content: bytes) -> OCRResult:
        """Extract text from PDF content using PyMuPDF"""
        try:
            logger.info("🔍 Starting OCR text extraction")
            
            # Open PDF document
            pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            if pdf_doc.page_count == 0:
                return OCRResult(False, error="PDF has no pages")
            
            # Extract text from all pages
            full_text = ""
            page_texts = []
            
            for page_num in range(pdf_doc.page_count):
                page = pdf_doc[page_num]
                page_text = page.get_text()
                
                if page_text.strip():
                    full_text += page_text + "\n\n"
                    page_texts.append({
                        'page_number': page_num + 1,
                        'text': page_text.strip(),
                        'char_count': len(page_text.strip())
                    })
            
            pdf_doc.close()
            
            # Validate extracted text
            if len(full_text.strip()) < self.min_text_length:
                return OCRResult(
                    False, 
                    text=full_text.strip(),
                    error=f"Extracted text too short: {len(full_text.strip())} chars"
                )
            
            # Calculate confidence based on text quality
            confidence = self._calculate_text_confidence(full_text)
            
            # Prepare metadata
            metadata = {
                'total_pages': pdf_doc.page_count if 'pdf_doc' in locals() else len(page_texts),
                'total_chars': len(full_text),
                'pages_with_text': len(page_texts),
                'average_chars_per_page': len(full_text) / len(page_texts) if page_texts else 0,
                'confidence': confidence,
                'extraction_method': 'pymupdf',
                'page_details': page_texts
            }
            
            logger.info(f"✅ OCR extraction successful: {len(full_text)} chars, {confidence:.2f} confidence")
            
            return OCRResult(
                success=True,
                text=full_text.strip(),
                metadata=metadata,
                confidence=confidence
            )
            
        except Exception as e:
            logger.error(f"❌ OCR extraction failed: {str(e)}")
            return OCRResult(False, error=f"OCR extraction failed: {str(e)}")
    
    def _calculate_text_confidence(self, text: str) -> float:
        """Calculate confidence score based on text characteristics"""
        try:
            if not text:
                return 0.0
            
            # Factors for confidence calculation
            factors = []
            
            # Length factor (longer text usually better)
            length_score = min(len(text) / 1000, 1.0)  # Normalize to 1000 chars
            factors.append(length_score * 0.3)
            
            # Character diversity (more diverse = better)
            unique_chars = len(set(text.lower()))
            diversity_score = min(unique_chars / 50, 1.0)  # Normalize to 50 unique chars
            factors.append(diversity_score * 0.2)
            
            # Word count factor
            words = text.split()
            word_score = min(len(words) / 200, 1.0)  # Normalize to 200 words
            factors.append(word_score * 0.2)
            
            # Special characters ratio (too many = lower confidence)
            alpha_count = sum(1 for c in text if c.isalpha())
            alpha_ratio = alpha_count / len(text) if text else 0
            factors.append(alpha_ratio * 0.3)
            
            # Calculate final confidence
            confidence = sum(factors)
            return min(max(confidence, 0.0), 1.0)  # Clamp between 0 and 1
            
        except:
            return 0.5  # Default confidence