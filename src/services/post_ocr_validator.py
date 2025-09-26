# src/services/post_ocr_validator.py

import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class PostOCRValidator:
    """
    Validador post-OCR que verifica si se extrajeron personas
    cuando el texto sugiere que debería haberlas
    """
    
    def validate_persons_extraction(self, ocr_result) -> Dict[str, Any]:
        """
        Valida si se extrajeron personas correctamente
        """
        try:
            # Manejar tanto OCRResult como dict
            if hasattr(ocr_result, 'text'):
                # Es un objeto OCRResult
                texto_completo = getattr(ocr_result, 'text', '') or ''
                structured_data = getattr(ocr_result, 'structured_data', {}) or {}
            else:
                # Es un diccionario
                texto_completo = ocr_result.get('texto_completo', '')
                structured_data = ocr_result.get('structured_data_raw', {})
            
            # Verificar si hay personas extraídas
            personas_extraidas = []
            if isinstance(structured_data, dict):
                lista_clientes = structured_data.get('lista_clientes', [])
                if isinstance(lista_clientes, list):
                    personas_extraidas = lista_clientes
            
            # Detectar si DEBERÍA haber personas basado en el texto
            deberia_haber_personas = self._should_have_persons(texto_completo)
            
            validation_result = {
                'personas_count': len(personas_extraidas),
                'should_have_persons': deberia_haber_personas,
                'validation_passed': True,
                'warnings': [],
                'extracted_from_text': []
            }
            
            # Si debería haber personas pero no se extrajeron
            if deberia_haber_personas and len(personas_extraidas) == 0:
                logger.warning(f"⚠️ Document appears to have persons but none extracted!")
                validation_result['validation_passed'] = False
                validation_result['warnings'].append("Documento contiene tabla de personas pero no se extrajeron")
                
                # Intentar extracción básica desde texto
                extracted = self._extract_persons_from_text(texto_completo)
                validation_result['extracted_from_text'] = extracted
                
                if extracted:
                    validation_result['warnings'].append(f"Se detectaron {len(extracted)} personas en el texto que no fueron extraídas")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error in post-OCR validation: {str(e)}")
            return {
                'personas_count': 0,
                'should_have_persons': False,
                'validation_passed': False,
                'error': str(e)
            }
    
    def _should_have_persons(self, text: str) -> bool:
        """
        Detecta si el texto sugiere que debe haber una lista de personas
        """
        # Patrones que indican presencia de tabla de personas
        table_indicators = [
            r'agente\s+económico',
            r'empleador',
            r'n[°º]\s*exp',
            r'r\.?u\.?c\.?',
            r'c\.?i\.?p\.?',
            r'monto\s+b/',
            r'\|\s*nombre',
            r'tabla.*persona',
            r'listado.*cliente',
            r'\d+-\d+-\d+.*\d+[,\.]\d+',  # Patrón de cédula + monto
        ]
        
        text_lower = text.lower()
        for pattern in table_indicators:
            if re.search(pattern, text_lower, re.IGNORECASE):
                logger.info(f"✅ Table indicator found: {pattern}")
                return True
        
        return False
    
    def _extract_persons_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Extracción básica de personas desde texto cuando Mistral falla
        """
        persons = []
        
        try:
            # Patrón para detectar filas de tabla con persona + identificación + monto
            # Ejemplo: "MINI SUPER AYACUCHO/RICARDO QIU ZHANG | 8-947-865, D.V. 86 | 467.50"
            
            table_pattern = r'([A-ZÁ-Ú][A-ZÁ-Ú\s\.,/]+)\s*\|?\s*(\d+-\d+-\d+[^\|]*)\s*\|?\s*([\d,]+\.?\d*)'
            matches = re.findall(table_pattern, text, re.MULTILINE)
            
            for idx, match in enumerate(matches):
                nombre = match[0].strip()
                identificacion = match[1].strip()
                monto_str = match[2].strip().replace(',', '')
                
                try:
                    monto_numerico = float(monto_str)
                except:
                    monto_numerico = 0.0
                
                person = {
                    'nombre_completo': nombre,
                    'numero_identificacion': identificacion,
                    'monto': monto_str,
                    'monto_numerico': monto_numerico,
                    'tipo_persona': 'Extraído del texto',
                    'observaciones': f'Extracción de respaldo - secuencia {idx + 1}'
                }
                persons.append(person)
            
            if persons:
                logger.info(f"📋 Extracted {len(persons)} persons from text as fallback")
            
            return persons
            
        except Exception as e:
            logger.error(f"Error extracting persons from text: {str(e)}")
            return []
    
    def enrich_ocr_result(self, ocr_result):
        """
        Enriquece el resultado OCR con personas extraídas del texto si es necesario
        """
        validation = self.validate_persons_extraction(ocr_result)
        
        # Manejar tanto OCRResult como dict
        if hasattr(ocr_result, 'structured_data'):
            # Es un objeto OCRResult
            if not validation['validation_passed'] and validation.get('extracted_from_text'):
                logger.info("🔧 Enriching OCR result with text-extracted persons")
                
                # Actualizar structured_data
                if not ocr_result.structured_data:
                    ocr_result.structured_data = {}
                
                if isinstance(ocr_result.structured_data, dict):
                    ocr_result.structured_data['lista_clientes'] = validation['extracted_from_text']
                    
                    # Agregar advertencia
                    if not hasattr(ocr_result, 'observaciones') or not getattr(ocr_result, 'observaciones', ''):
                        ocr_result.observaciones = ''
                    ocr_result.observaciones += f"\nADVERTENCIA: Personas extraídas mediante fallback desde texto. Validar manualmente."
            
            # SIEMPRE convertir lista_clientes a lista_personas para compatibilidad con CRM
            if hasattr(ocr_result, 'structured_data') and isinstance(ocr_result.structured_data, dict):
                lista_clientes = ocr_result.structured_data.get('lista_clientes', [])
                if lista_clientes:
                    ocr_result.lista_personas = {
                        'listado': lista_clientes,
                        'monto_total': sum(p.get('monto_numerico', 0) for p in lista_clientes if isinstance(p, dict))
                    }
                    logger.info(f"🔄 Converted {len(lista_clientes)} personas from lista_clientes to lista_personas")
            
            # Agregar validation_result como atributo
            if hasattr(ocr_result, 'validation_result'):
                ocr_result.validation_result = validation
            else:
                # Si no se puede asignar como atributo, agregar a metadata
                if not hasattr(ocr_result, 'metadata'):
                    ocr_result.metadata = {}
                ocr_result.metadata['validation_result'] = validation
            
        else:
            # Es un diccionario
            if not validation['validation_passed'] and validation.get('extracted_from_text'):
                logger.info("🔧 Enriching OCR result with text-extracted persons")
            
            # Agregar personas extraídas del texto
            if 'structured_data_raw' not in ocr_result:
                ocr_result['structured_data_raw'] = {}
            
            if isinstance(ocr_result['structured_data_raw'], dict):
                ocr_result['structured_data_raw']['lista_clientes'] = validation['extracted_from_text']
                ocr_result['lista_personas'] = {
                    'listado': validation['extracted_from_text'],
                    'monto_total': sum(p.get('monto_numerico', 0) for p in validation['extracted_from_text'])
                }
                
                # Agregar advertencia
                if 'observaciones' not in ocr_result:
                    ocr_result['observaciones'] = ''
                ocr_result['observaciones'] += f"\nADVERTENCIA: Personas extraídas mediante fallback desde texto. Validar manualmente."
            
            # SIEMPRE convertir lista_clientes a lista_personas para compatibilidad con CRM
            if 'structured_data_raw' in ocr_result and isinstance(ocr_result['structured_data_raw'], dict):
                lista_clientes = ocr_result['structured_data_raw'].get('lista_clientes', [])
                if lista_clientes:
                    ocr_result['lista_personas'] = {
                        'listado': lista_clientes,
                        'monto_total': sum(p.get('monto_numerico', 0) for p in lista_clientes if isinstance(p, dict))
                    }
                    logger.info(f"🔄 Converted {len(lista_clientes)} personas from lista_clientes to lista_personas")
        
            # Solo asignar si es un diccionario
            if isinstance(ocr_result, dict):
                ocr_result['validation_result'] = validation
        
        return ocr_result