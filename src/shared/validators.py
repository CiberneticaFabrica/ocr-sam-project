# src/shared/validators.py
import logging
from typing import List, Dict, Any, NamedTuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of validation operation"""
    success: bool
    error: str = ""
    warning: str = ""
    details: Dict[str, Any] = None

class PDFValidator:
    """Validator for PDF operations"""
    
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MIN_FILE_SIZE = 1024  # 1KB
    
    @staticmethod
    def validate_pdf_content(pdf_content: bytes) -> ValidationResult:
        """Validate PDF content"""
        try:
            # Check file size
            if len(pdf_content) > PDFValidator.MAX_FILE_SIZE:
                return ValidationResult(False, f"PDF too large: {len(pdf_content)} bytes (max: {PDFValidator.MAX_FILE_SIZE})")
            
            if len(pdf_content) < PDFValidator.MIN_FILE_SIZE:
                return ValidationResult(False, f"PDF too small: {len(pdf_content)} bytes (min: {PDFValidator.MIN_FILE_SIZE})")
            
            # Check PDF header
            if not pdf_content.startswith(b'%PDF-'):
                return ValidationResult(False, "Invalid PDF file: missing PDF header")
            
            # Basic PDF structure check
            if b'%%EOF' not in pdf_content:
                return ValidationResult(False, "Invalid PDF file: missing EOF marker")
            
            return ValidationResult(True)
            
        except Exception as e:
            return ValidationResult(False, f"PDF validation error: {str(e)}")

class OficiosValidator:
    """Validator for oficios operations"""
    
    @staticmethod
    def validate_count(oficios: List[Dict], metadata: Dict[str, Any]) -> ValidationResult:
        """Validate oficios count against declared count"""
        try:
            cantidad_extraida = len(oficios)
            cantidad_declarada = metadata.get('cantidad_oficios_declarada', 0)
            
            logger.info(f"📊 Validating count - Declared: {cantidad_declarada}, Extracted: {cantidad_extraida}")
            
            # No oficios extracted
            if cantidad_extraida == 0:
                return ValidationResult(False, "No se pudieron extraer oficios del PDF")
            
            # No declared count (auto-process)
            if cantidad_declarada == 0:
                return ValidationResult(
                    True, 
                    warning=f"No se declaró cantidad, procesando {cantidad_extraida} oficios encontrados"
                )
            
            # Exact match
            if cantidad_extraida == cantidad_declarada:
                return ValidationResult(True)
            
            # Calculate tolerance (10% or minimum 1)
            tolerance = max(1, int(cantidad_declarada * 0.1))
            difference = abs(cantidad_extraida - cantidad_declarada)
            
            # Within tolerance
            if difference <= tolerance:
                return ValidationResult(
                    True,
                    warning=f"Diferencia menor dentro de tolerancia: {difference} (tolerancia: {tolerance})"
                )
            
            # Outside tolerance
            return ValidationResult(
                False, 
                f"Diferencia excede tolerancia: declarados {cantidad_declarada}, extraídos {cantidad_extraida} (diferencia: {difference}, tolerancia: {tolerance})"
            )
            
        except Exception as e:
            return ValidationResult(False, f"Error validating count: {str(e)}")

class MetadataValidator:
    """Validator for metadata operations"""
    
    REQUIRED_FIELDS = ['empresa', 'cantidad_oficios_declarada']
    OPTIONAL_FIELDS = ['origen', 'observaciones', 'fecha', 'operador']
    
    @staticmethod
    def validate_metadata(metadata: Dict[str, Any]) -> ValidationResult:
        """Validate extracted metadata"""
        try:
            missing_fields = []
            warnings = []
            
            # Check required fields
            for field in MetadataValidator.REQUIRED_FIELDS:
                if field not in metadata or not metadata[field]:
                    missing_fields.append(field)
            
            # Check for reasonable values
            if 'cantidad_oficios_declarada' in metadata:
                count = metadata['cantidad_oficios_declarada']
                if count < 0 or count > 1000:
                    warnings.append(f"Cantidad de oficios inusual: {count}")
            
            if 'empresa' in metadata and len(metadata['empresa']) < 3:
                warnings.append("Nombre de empresa muy corto")
            
            # Determine result
            if missing_fields:
                return ValidationResult(
                    False, 
                    f"Campos requeridos faltantes: {missing_fields}",
                    "; ".join(warnings) if warnings else ""
                )
            
            return ValidationResult(
                True,
                warning="; ".join(warnings) if warnings else ""
            )
            
        except Exception as e:
            return ValidationResult(False, f"Error validating metadata: {str(e)}")