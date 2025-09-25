# src/services/ocr_service.py - VERSIÓN BASADA EN TU IMPLEMENTACIÓN EXITOSA
import json
import base64
import logging
import requests
import time
import random
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from shared.config import Config
from shared.exceptions import OCRExtractionError, MistralAPIError

logger = logging.getLogger(__name__)
config = Config()

@dataclass
class OCRResult:
    """Resultado de extracción OCR"""
    success: bool
    text: str = ""
    structured_data: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    error: str = ""
    confidence: str = "medium"
    processing_time: float = 0.0
    raw_response: Dict[str, Any] = None

class OCRService:
    """
    Servicio OCR basado en tu implementación exitosa
    """
    
    def __init__(self):
        self.api_key = config.MISTRAL_API_KEY
        self.api_url = "https://api.mistral.ai/v1/ocr"
        self.model = "mistral-ocr-latest"
        
        # Configuración optimizada basada en tu implementación
        self.max_retries = 5
        self.timeout = 600  # 10 minutos base
        self.base_delay = 5
        self.max_delay = 300  # 5 minutos máximo
        
        # Métricas
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._total_processing_time = 0.0

    def extract_text_from_pdf(self, pdf_content: bytes, job_id: str = None, document_type: str = 'legal_document') -> OCRResult:
        """
        Extrae texto de PDF usando Mistral OCR con base64
        Basado en tu implementación exitosa
        """
        try:
            start_time = time.time()
            self._total_requests += 1
            
            # Convertir PDF a base64
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            
            # Crear payload usando tu lógica
            payload = self._build_api_payload(pdf_base64, document_type)
            
            # Llamar a la API con reintentos robustos
            api_response = self._call_mistral_ocr_api_with_retry(payload)
            
            if not api_response:
                self._failed_requests += 1
                return OCRResult(
                    success=False,
                    error="Failed to get response from Mistral OCR API",
                    metadata={'job_id': job_id}
                )
            
            # Procesar respuesta usando tu lógica
            result = self._process_api_response(api_response, job_id, document_type)
            
            processing_time = time.time() - start_time
            self._total_processing_time += processing_time
            
            if result.success:
                self._successful_requests += 1
                result.processing_time = processing_time
                result.metadata = result.metadata or {}
                result.metadata.update({
                    'job_id': job_id,
                    'processing_time': processing_time,
                    'extraction_method': 'mistral_ocr_base64'
                })
            else:
                self._failed_requests += 1
            
            return result
            
        except Exception as e:
            self._failed_requests += 1
            logger.error(f"Error in OCRService.extract_text_from_pdf: {str(e)}")
            return OCRResult(
                success=False,
                error=str(e),
                metadata={'job_id': job_id}
            )

    def _build_api_payload(self, pdf_base64: str, document_type: str) -> Dict[str, Any]:
        """
        Construye el payload para la API usando tu lógica
        """
        payload = {
            "model": self.model,
            "include_image_base64": True
        }
        
        # Configurar el documento como data URL
        data_url = f"data:application/pdf;base64,{pdf_base64}"
        payload["document"] = {"document_url": data_url}
        
        # Configurar annotations para documentos legales
        if document_type == 'legal_document':
            payload["document_annotation_format"] = self._create_legal_document_annotation_schema()
        
        return payload

    def _create_legal_document_annotation_schema(self) -> Dict[str, Any]:
        """
        Crea el schema especializado para documentos legales
        Basado en tu implementación exitosa
        """
        return {
            "type": "json_schema",
            "json_schema": {
                "schema": {
                    "properties": {
                        "clasificacion": {
                            "title": "Clasificacion",
                            "description": "Clasificación del tipo de oficio legal",
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {
                                    "title": "Id", 
                                    "description": "ID numérico del tipo de oficio (1-16)",
                                    "type": "integer"
                                },
                                "tipo_oficio": {
                                    "title": "Tipo_Oficio",
                                    "description": "Nombre completo del tipo de oficio",
                                    "type": "string"
                                },
                                "tramite": {
                                    "title": "Tramite",
                                    "description": "Categoría del trámite (Secuestros, Embargos, etc.)",
                                    "type": "string"
                                },
                                "departamento": {
                                    "title": "Departamento",
                                    "description": "Departamento encargado (Civil o Penal)",
                                    "type": "string"
                                },
                                "confianza": {
                                    "title": "Confianza",
                                    "description": "Nivel de confianza en la clasificación",
                                    "type": "string",
                                    "enum": ["alta", "media", "baja"]
                                }
                            },
                            "required": ["id", "tipo_oficio", "tramite", "departamento", "confianza"]
                        },
                        "informacion_general": {
                            "title": "Informacion_General",
                            "description": "Información general del documento",
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "numero_oficio": {
                                    "title": "Numero_Oficio",
                                    "description": "Número o código del oficio",
                                    "type": "string"
                                },
                                "fecha": {
                                    "title": "Fecha",
                                    "description": "Fecha del documento",
                                    "type": "string"
                                },
                                "autoridad_emisora": {
                                    "title": "Autoridad_Emisora",
                                    "description": "Institución que emite el oficio",
                                    "type": "string"
                                },
                                "destinatario": {
                                    "title": "Destinatario",
                                    "description": "A quién va dirigido",
                                    "type": "string"
                                },
                                "asunto": {
                                    "title": "Asunto",
                                    "description": "Descripción del asunto",
                                    "type": "string"
                                }
                            },
                            "required": ["numero_oficio", "fecha", "autoridad_emisora", "destinatario"]
                        },
                        "lista_clientes": {
                            "title": "Lista_Clientes",
                            "description": "Lista de clientes/personas mencionados en el documento legal panameño",
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "nombre_completo": {
                                        "title": "Nombre_Completo",
                                        "description": "Nombre y apellidos completos de la persona",
                                        "type": "string"
                                    },
                                    "numero_identificacion": {
                                        "title": "Numero_Identificacion",
                                        "description": "Cédula panameña (formato: X-XXX-XXXX) o documento de identidad",
                                        "type": "string"
                                    },
                                    "numero_ruc": {
                                        "title": "Numero_RUC",
                                        "description": "Número RUC panameño (formato: XXX-XXXXXX-XX-DV)",
                                        "type": "string"
                                    },
                                    "numero_cuenta": {
                                        "title": "Numero_Cuenta",
                                        "description": "Número de cuenta bancaria si aplica",
                                        "type": "string"
                                    },
                                    "monto": {
                                        "title": "Monto",
                                        "description": "Monto asociado en balboas (ej: B/. 1,500.00)",
                                        "type": "string"
                                    },
                                    "monto_numerico": {
                                        "title": "Monto_Numerico",
                                        "description": "Monto como número decimal",
                                        "type": "number"
                                    },
                                    "expediente": {
                                        "title": "Expediente",
                                        "description": "Número de expediente judicial",
                                        "type": "string"
                                    },
                                    "tipo_persona": {
                                        "title": "Tipo_Persona",
                                        "description": "Tipo de persona (Cliente, Agente Económico, Demandado, etc.)",
                                        "type": "string"
                                    },
                                    "observaciones": {
                                        "title": "Observaciones",
                                        "description": "Notas o observaciones adicionales sobre la persona",
                                        "type": "string"
                                    }
                                },
                                "required": ["nombre_completo"]
                            }
                        },
                        "palabras_clave_encontradas": {
                            "title": "Palabras_Clave_Encontradas",
                            "description": "Palabras clave legales identificadas en el documento",
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "texto_completo": {
                            "title": "Texto_Completo",
                            "description": "Transcripción completa del texto del documento",
                            "type": "string"
                        },
                        "observaciones": {
                            "title": "Observaciones",
                            "description": "Observaciones adicionales sobre el procesamiento",
                            "type": "string"
                        }
                    },
                    "required": ["clasificacion", "informacion_general", "lista_clientes", "texto_completo"],
                    "title": "LegalDocumentAnnotation",
                    "type": "object",
                    "additionalProperties": False
                },
                "name": "legal_document_annotation",
                "strict": True
            }
        }

    def _call_mistral_ocr_api_with_retry(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Realiza la llamada a la API con reintentos robustos
        Basado en tu implementación exitosa
        """
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"🌐 Mistral OCR API call attempt {attempt + 1}/{self.max_retries + 1}")
                
                # Timeout progresivo como en tu lambda
                timeout = 600 + (attempt * 120)  # 10min + 2min por intento
                
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    logger.info(f"✅ API call successful on attempt {attempt + 1}")
                    return response.json()
                
                # Manejar diferentes tipos de errores usando tu lógica
                error_type, should_retry, wait_time = self._analyze_api_error(response, attempt)
                
                logger.warning(f"❌ Error {response.status_code} en intento {attempt + 1}: {response.text}")
                
                # Si no debemos reintentar, salir
                if not should_retry or attempt == self.max_retries:
                    logger.error(f"❌ Final error after {attempt + 1} attempts: {response.status_code}")
                    return None
                
                # Esperar antes del siguiente intento
                logger.info(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                
            except requests.exceptions.Timeout:
                logger.warning(f"⏰ Timeout on attempt {attempt + 1}")
                if attempt == self.max_retries:
                    logger.error("❌ Final timeout after all attempts")
                    return None
                
                # Esperar progresivamente más tiempo por timeout
                wait_time = 30 + (attempt * 30)  # 30s, 60s, 90s, etc.
                logger.info(f"⏳ Waiting {wait_time} seconds for timeout...")
                time.sleep(wait_time)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"🌐 Request error on attempt {attempt + 1}: {str(e)}")
                if attempt == self.max_retries:
                    logger.error("❌ Final request error after all attempts")
                    return None
                
                # Esperar antes de reintentar por error de conexión
                wait_time = 10 + (attempt * 10)
                time.sleep(wait_time)
        
        return None

    def _analyze_api_error(self, response: requests.Response, attempt: int) -> Tuple[str, bool, int]:
        """
        Analiza el error de la API y determina si debe reintentar
        Basado en tu implementación exitosa
        """
        status_code = response.status_code
        
        try:
            error_data = response.json()
            error_message = error_data.get('message', '').lower()
            error_type = error_data.get('type', '')
        except:
            error_message = response.text.lower()
            error_type = 'unknown'
        
        # Error 429: Rate limiting / Capacity exceeded
        if status_code == 429:
            if 'capacity exceeded' in error_message:
                # Capacidad excedida - esperar más tiempo
                wait_time = min(60 + (attempt * 30), 300)  # Max 5 minutos
                return 'capacity_exceeded', True, wait_time
            else:
                # Rate limiting normal
                wait_time = min(30 + (attempt * 15), 120)  # Max 2 minutos
                return 'rate_limit', True, wait_time
        
        # Error 500-599: Errores del servidor (reintentar)
        elif 500 <= status_code <= 599:
            wait_time = min(20 + (attempt * 20), 180)  # Max 3 minutos
            return 'server_error', True, wait_time
        
        # Error 401: Authentication (no reintentar)
        elif status_code == 401:
            return 'auth_error', False, 0
        
        # Error 400: Bad request (no reintentar en la mayoría de casos)
        elif status_code == 400:
            # Algunos errores 400 pueden ser temporales
            if 'temporary' in error_message or 'try again' in error_message:
                wait_time = 15 + (attempt * 10)
                return 'temporary_bad_request', True, wait_time
            return 'bad_request', False, 0
        
        # Error 413: Payload too large (no reintentar)
        elif status_code == 413:
            return 'payload_too_large', False, 0
        
        # Otros errores 4xx (no reintentar)
        elif 400 <= status_code <= 499:
            return 'client_error', False, 0
        
        # Error desconocido (reintentar conservadoramente)
        else:
            wait_time = 30 + (attempt * 15)
            return 'unknown_error', True, wait_time

    def _process_api_response(self, api_response: Dict[str, Any], job_id: str, document_type: str) -> OCRResult:
        """
        Procesa la respuesta de la API usando tu lógica mejorada
        """
        try:
            logger.info(f"🔍 Processing Mistral response for {job_id}")
            logger.info(f"📋 Response keys: {list(api_response.keys())}")
            
            extracted_text = ""
            structured_data = None
            
            # Estrategia 1: Buscar en choices (formato estándar)
            if 'choices' in api_response and len(api_response['choices']) > 0:
                choice = api_response['choices'][0]
                if 'message' in choice and 'content' in choice['message']:
                    content = choice['message']['content']
                    logger.info(f"📄 Found content in choices[0].message.content")
                    
                    try:
                        # Intentar parsear como JSON estructurado
                        parsed_content = json.loads(content)
                        
                        if isinstance(parsed_content, dict):
                            structured_data = parsed_content
                            
                            # Extraer texto de la estructura
                            extracted_text = parsed_content.get('texto_completo', '')
                            
                            # Si no hay texto en estructura, usar el contenido crudo
                            if not extracted_text:
                                extracted_text = content
                        else:
                            # Si no es dict, usar como texto plano
                            extracted_text = content
                            
                    except json.JSONDecodeError:
                        # Si no es JSON válido, usar como texto plano
                        extracted_text = content
                        logger.warning(f"Content is not valid JSON, using as plain text")
            
            # Estrategia 2: Buscar directamente en la respuesta (formato OCR)
            elif 'pages' in api_response:
                logger.info(f"📄 Found pages in response")
                pages = api_response['pages']
                if len(pages) > 0 and 'markdown' in pages[0]:
                    extracted_text = pages[0]['markdown']
                    logger.info(f"📄 Extracted text from pages[0].markdown: {len(extracted_text)} chars")
                    
                    # Buscar datos estructurados en la respuesta
                    if 'document_annotation' in api_response:
                        structured_data = api_response['document_annotation']
                        logger.info(f"📊 Found structured data in document_annotation")
            
            # Estrategia 3: Buscar en document_annotation directamente
            elif 'document_annotation' in api_response:
                logger.info(f"📊 Found document_annotation in response")
                structured_data = api_response['document_annotation']
                
                # Intentar extraer texto del documento estructurado
                if isinstance(structured_data, dict):
                    extracted_text = structured_data.get('texto_completo', '')
                    if not extracted_text:
                        extracted_text = structured_data.get('text', '')
            
            # Estrategia 4: Buscar en bbox_annotations
            elif 'bbox_annotations' in api_response:
                logger.info(f"📄 Found bbox_annotations in response")
                bbox_annotations = api_response['bbox_annotations']
                if len(bbox_annotations) > 0:
                    # Extraer texto de todas las anotaciones
                    text_parts = []
                    for bbox in bbox_annotations:
                        if 'text' in bbox:
                            text_parts.append(bbox['text'])
                    extracted_text = ' '.join(text_parts)
                    logger.info(f"📄 Extracted text from bbox_annotations: {len(extracted_text)} chars")
            
            # Estrategia 5: Buscar en cualquier campo que contenga texto
            else:
                logger.info(f"🔍 Searching for text in other fields")
                for key, value in api_response.items():
                    if isinstance(value, str) and len(value) > 100:  # Texto significativo
                        extracted_text = value
                        logger.info(f"📄 Found text in field '{key}': {len(value)} chars")
                        break
            
            # Validar que tenemos algo útil
            if not extracted_text and not structured_data:
                logger.warning("⚠️ No useful content found in API response")
                logger.warning(f"🔍 Full API response: {json.dumps(api_response, default=str)[:500]}...")
                return OCRResult(
                    success=False,
                    error="No text or structured data found in API response",
                    metadata={'job_id': job_id, 'document_type': document_type},
                    raw_response=api_response
                )
            
            # Validar patrones panameños si es un documento legal
            validation_results = None
            if document_type == 'legal_document' and structured_data:
                logger.info("🔍 Validating Panamanian patterns...")
                validation_results = self._validate_panamanian_patterns(structured_data)
                
                # Agregar resultados de validación a los datos estructurados
                if structured_data and isinstance(structured_data, dict):
                    structured_data['validaciones'] = validation_results
            
            # Determinar confianza basada en validación y contenido
            confidence = "high" if structured_data and extracted_text else "medium" if extracted_text else "low"
            
            # Ajustar confianza basada en validación panameña
            if validation_results and validation_results.get('validation_passed', False):
                confidence = "high"
                logger.info("✅ Panamanian validation passed - High confidence")
            elif validation_results and validation_results.get('confidence_score', 0) < 0.5:
                confidence = "low"
                logger.warning("⚠️ Panamanian validation failed - Low confidence")
            
            return OCRResult(
                success=True,
                text=extracted_text,
                structured_data=structured_data,
                confidence=confidence,
                metadata={
                    'job_id': job_id, 
                    'document_type': document_type,
                    'validation_results': validation_results,
                    'panamanian_validation': validation_results is not None
                },
                raw_response=api_response
            )
            
        except Exception as e:
            logger.error(f"❌ Error processing API response: {str(e)}")
            return OCRResult(
                success=False,
                error=f"Error processing API response: {str(e)}",
                metadata={'job_id': job_id, 'document_type': document_type},
                raw_response=api_response
            )

    def get_service_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del servicio"""
        return {
            'service_name': 'OCRService',
            'api_endpoint': self.api_url,
            'max_retries': self.max_retries,
            'timeout': self.timeout,
            'metrics': {
                'total_requests': self._total_requests,
                'successful_requests': self._successful_requests,
                'failed_requests': self._failed_requests,
                'success_rate': (self._successful_requests / self._total_requests * 100) if self._total_requests > 0 else 0,
                'average_processing_time': (self._total_processing_time / self._total_requests) if self._total_requests > 0 else 0
            }
        }

    def _get_legal_classification_prompt(self) -> str:
        """
        Retorna el prompt especializado para clasificación de oficios legales panameños
        Basado en tu implementación exitosa
        """
        return """Analiza este documento legal panameño y clasifícalo según estos tipos de oficios:

TIPOS DE OFICIOS PANAMEÑOS:
1. Oficios de Secuestros Civiles (Secuestros - Civil)
2. Oficios de Aprehensiones (Secuestros - Civil)  
3. Oficios de Solicitud de Traslado de Fondos Aprehendidos (Secuestros - Civil)
4. Oficios de Levantamiento Civiles y Penales (Levantamientos - Civil)
5. Oficios de Embargos (Embargos - Civil)
6. Oficios de Adjudicación en Procesos de Sucesión (Juicios de Sucesión - Civil)
7. Oficios de Investigaciones de Procesos de Sucesión (Juicios de Sucesión - Civil)
8. Oficios de Solo Notificación (Citaciones - Civil)
9. Oficios de Citaciones (Citaciones - Civil)
10. Oficios de Investigaciones Civiles (Investigaciones - Penal)
11. Oficios de Investigación de Familia (Investigaciones - Penal)
12. Oficios de Investigaciones de Procesos Penales (Investigaciones - Penal)
13. Oficios Solicitando Información de Clientes (Investigaciones - Penal)
14. Oficios de Inspección Ocular (Investigaciones - Penal)
15. Oficios de Allanamiento (Investigaciones - Penal)
16. Diligencia Exhibitoria (Investigaciones - Penal)

INSTRUCCIONES ESPECÍFICAS PARA DOCUMENTOS PANAMEÑOS:
- Identifica el tipo de oficio basándote en el contenido y palabras clave
- Extrae toda la información general del documento (número, fecha, autoridad, destinatario)
- Si hay una lista de clientes/personas, extrae todos los datos disponibles incluyendo:
  * Nombre completo
  * Número de identificación (cédula panameña formato: X-XXX-XXXX)
  * Número RUC (formato: XXX-XXXXXX-XX-DV)
  * Número de cuenta bancaria si aplica
  * Monto asociado si se especifica
  * Expediente si se menciona
- Transcribe el texto completo del documento
- Identifica palabras clave legales específicas
- Indica tu nivel de confianza en la clasificación (alta, media, baja)

PATRONES ESPECÍFICOS PANAMEÑOS:
- Cédulas: formato X-XXX-XXXX
- RUC: formato XXX-XXXXXX-XX-DV
- Números de oficio: JE-XXXX-XXXX, DJ-XXXX-XXXX, etc.
- Fechas en español: "23 de mayo de 2025"
- Montos en balboas: B/. XXX.XX
- Autoridades: Juzgado Ejecutor, Juzgado Segundo, etc."""

    def _validate_panamanian_patterns(self, structured_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida patrones específicos de documentos legales panameños
        Basado en tu implementación exitosa
        """
        validation_results = {
            'valid_patterns': {},
            'invalid_patterns': {},
            'confidence_score': 0.0,
            'validation_passed': False
        }
        
        try:
            # Verificar que structured_data es un diccionario
            if not isinstance(structured_data, dict):
                logger.warning(f"⚠️ structured_data is not a dict, type: {type(structured_data)}")
                validation_results['error'] = f"structured_data is not a dict, got {type(structured_data)}"
                return validation_results
            
            # Patrones panameños específicos
            panama_patterns = {
                'cedula': r'\b\d{1,2}-\d{1,4}-\d{1,4}\b',
                'ruc': r'\b\d{1,3}-\d{1,6}-\d{1,2}-?\d{0,2}\b',
                'oficio_number': r'\b(?:JE-|DJ-|No\.?)\s*\d{1,6}(?:-\d{4})?\b',
                'phone': r'\b\d{3}-\d{4}\b',
                'money': r'\bB/\.?\s*[\d,]+\.?\d{0,2}\b',
                'date_es': r'\b\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\b'
            }
            
            # Validar información general
            if 'informacion_general' in structured_data:
                info_general = structured_data['informacion_general']
                
                # Verificar que info_general es un diccionario
                if isinstance(info_general, dict):
                    # Validar número de oficio
                    if 'numero_oficio' in info_general:
                        oficio_num = info_general['numero_oficio']
                        if self._validate_pattern(oficio_num, panama_patterns['oficio_number']):
                            validation_results['valid_patterns']['numero_oficio'] = oficio_num
                        else:
                            validation_results['invalid_patterns']['numero_oficio'] = oficio_num
                    
                    # Validar fecha
                    if 'fecha' in info_general:
                        fecha = info_general['fecha']
                        if self._validate_pattern(fecha, panama_patterns['date_es']):
                            validation_results['valid_patterns']['fecha'] = fecha
                        else:
                            validation_results['invalid_patterns']['fecha'] = fecha
                else:
                    logger.warning(f"⚠️ informacion_general is not a dict, type: {type(info_general)}")
            
            # Validar lista de clientes
            if 'lista_clientes' in structured_data:
                clientes = structured_data['lista_clientes']
                
                # Verificar que clientes es una lista
                if isinstance(clientes, list):
                    valid_clientes = 0
                    
                    for cliente in clientes:
                        if isinstance(cliente, dict):
                            cliente_valid = True
                            
                            # Validar cédula
                            if 'numero_identificacion' in cliente:
                                cedula = cliente['numero_identificacion']
                                if not self._validate_pattern(cedula, panama_patterns['cedula']):
                                    cliente_valid = False
                                    validation_results['invalid_patterns'][f'cedula_{cliente.get("nombre_completo", "unknown")}'] = cedula
                            
                            # Validar RUC
                            if 'numero_ruc' in cliente:
                                ruc = cliente['numero_ruc']
                                if not self._validate_pattern(ruc, panama_patterns['ruc']):
                                    cliente_valid = False
                                    validation_results['invalid_patterns'][f'ruc_{cliente.get("nombre_completo", "unknown")}'] = ruc
                            
                            if cliente_valid:
                                valid_clientes += 1
                    
                    validation_results['valid_patterns']['clientes_validos'] = valid_clientes
                    validation_results['valid_patterns']['total_clientes'] = len(clientes)
                else:
                    logger.warning(f"⚠️ lista_clientes is not a list, type: {type(clientes)}")
            
            # Calcular score de confianza
            total_validations = len(validation_results['valid_patterns']) + len(validation_results['invalid_patterns'])
            if total_validations > 0:
                validation_results['confidence_score'] = len(validation_results['valid_patterns']) / total_validations
            
            # Determinar si pasa la validación
            validation_results['validation_passed'] = validation_results['confidence_score'] >= 0.7
            
            logger.info(f"✅ Validación panameña completada - Score: {validation_results['confidence_score']:.2f}")
            
        except Exception as e:
            logger.error(f"❌ Error en validación panameña: {str(e)}")
            validation_results['error'] = str(e)
        
        return validation_results

    def _validate_pattern(self, text: str, pattern: str) -> bool:
        """
        Valida si un texto coincide con un patrón regex
        """
        import re
        try:
            return bool(re.search(pattern, text, re.IGNORECASE))
        except:
            return False