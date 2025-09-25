# src/services/mistral_service.py - VERSIÓN SIMPLIFICADA
import json
import requests
import logging
import random
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from shared.config import Config
from shared.exceptions import MistralAPIError

logger = logging.getLogger(__name__)
config = Config()

@dataclass
class MistralResult:
    """Result of Mistral AI analysis (for text-only analysis)"""
    success: bool
    data: Dict[str, Any] = None
    error: str = ""
    raw_response: str = ""
    processing_time: float = 0.0

class MistralService:
    """
    Service for Mistral AI text analysis (complementary to OCR Service)
    
    Note: OCR functionality has been moved to OCRService.
    This service now handles text-only analysis and chat completions.
    """
    
    def __init__(self):
        self.api_key = config.MISTRAL_API_KEY
        self.chat_api_url = "https://api.mistral.ai/v1/chat/completions"
        self.model = "mistral-large-latest"
        self.max_retries = 3
        self.timeout = 120  # 2 minutes for text analysis
        self.base_delay = 2
        self.max_delay = 60
    
    def analyze_text_content(self, text: str, analysis_type: str = "legal_analysis", 
                           custom_prompt: str = None) -> MistralResult:
        """
        Analyze text content using Mistral AI chat completions
        (For when you already have extracted text and need additional analysis)
        """
        try:
            start_time = datetime.now()
            logger.info(f"Starting Mistral text analysis - Type: {analysis_type}")
            
            # Prepare prompt based on analysis type
            if custom_prompt:
                prompt = custom_prompt
            elif analysis_type == "legal_analysis":
                prompt = self._create_legal_analysis_prompt(text)
            elif analysis_type == "document_summary":
                prompt = self._create_summary_prompt(text)
            elif analysis_type == "entity_extraction":
                prompt = self._create_entity_extraction_prompt(text)
            else:
                prompt = f"Analyze the following text and provide structured insights:\n\n{text}"
            
            # Make API request
            response = self._make_chat_api_request(prompt)
            
            if not response:
                return MistralResult(False, error="No response from Mistral Chat API")
            
            # Parse response
            parsed_data = self._parse_chat_response(response)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Mistral text analysis completed in {processing_time:.2f}s")
            
            return MistralResult(
                success=True,
                data=parsed_data,
                raw_response=response,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Mistral text analysis failed: {str(e)}")
            return MistralResult(False, error=str(e))
    
    def analyze_oficio_text(self, text: str, job_id: str) -> MistralResult:
        """
        Legacy method for backward compatibility
        
        Note: For new implementations, use OCRService.extract_text_from_pdf() 
        which includes integrated OCR + AI analysis
        """
        logger.warning("analyze_oficio_text is deprecated. Use OCRService for integrated OCR+AI processing.")
        
        return self.analyze_text_content(
            text, 
            analysis_type="legal_analysis",
            custom_prompt=self._create_legal_analysis_prompt(text)
        )
    
    def _create_legal_analysis_prompt(self, text: str) -> str:
        """Create prompt for legal document analysis"""
        return f"""
        Analiza el siguiente texto de un documento legal y extrae información estructurada.

        TEXTO:
        {text}

        INSTRUCCIONES:
        1. Identifica el tipo de documento legal
        2. Extrae información clave como números de oficio, fechas, autoridades
        3. Identifica personas mencionadas
        4. Clasifica el documento según los tipos de oficios legales conocidos
        5. Proporciona un nivel de confianza en tu análisis

        RESPONDE EN FORMATO JSON con esta estructura:
        {{
            "tipo_documento": "tipo identificado",
            "nivel_confianza": "alto|medio|bajo",
            "informacion_clave": {{
                "numero_oficio": "string o null",
                "autoridad": "string o null",
                "fecha": "string o null",
                "destinatario": "string o null"
            }},
            "personas_identificadas": [
                {{
                    "nombre": "string",
                    "rol": "string",
                    "identificacion": "string o null"
                }}
            ],
            "clasificacion": "tipo de oficio",
            "resumen": "resumen del contenido"
        }}
        """
    
    def _create_summary_prompt(self, text: str) -> str:
        """Create prompt for document summarization"""
        return f"""
        Resume el siguiente texto de manera concisa y estructurada:

        TEXTO:
        {text}

        Proporciona un resumen que incluya:
        1. Tema principal
        2. Puntos clave
        3. Personas o entidades mencionadas
        4. Fechas importantes
        5. Acciones requeridas (si las hay)

        Responde en formato JSON estructurado.
        """
    
    def _create_entity_extraction_prompt(self, text: str) -> str:
        """Create prompt for entity extraction"""
        return f"""
        Extrae todas las entidades importantes del siguiente texto:

        TEXTO:
        {text}

        Identifica y estructura:
        - Nombres de personas
        - Organizaciones
        - Fechas
        - Números de documentos
        - Direcciones
        - Montos monetarios
        - Términos legales importantes

        Responde en formato JSON estructurado.
        """
    
    def _make_chat_api_request(self, prompt: str) -> Optional[str]:
        """Make request to Mistral Chat API with retries"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "top_p": 0.9
        }
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Mistral Chat API request attempt {attempt + 1}")
                
                response = requests.post(
                    self.chat_api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        content = result['choices'][0]['message']['content']
                        logger.info(f"Mistral Chat API success on attempt {attempt + 1}")
                        return content.strip()
                
                elif response.status_code == 429:
                    # Rate limit - exponential backoff
                    wait_time = self.base_delay * (2 ** attempt)
                    jitter = random.uniform(0, wait_time * 0.1)
                    total_wait = min(wait_time + jitter, self.max_delay)
                    
                    logger.warning(f"Rate limit hit, waiting {total_wait:.1f}s (attempt {attempt + 1})")
                    time.sleep(total_wait)
                    continue
                
                else:
                    logger.warning(f"API returned status {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                continue
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error on attempt {attempt + 1}: {str(e)}")
                continue
        
        logger.error("All Mistral Chat API attempts failed")
        return None
    
    def _parse_chat_response(self, response: str) -> Dict[str, Any]:
        """Parse and validate Mistral Chat response"""
        try:
            # Try to find JSON in response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                parsed = json.loads(json_str)
                
                # Basic validation
                if isinstance(parsed, dict):
                    return parsed
            
            # If no valid JSON found, create basic structure
            logger.warning("Could not parse Mistral response as JSON, creating basic structure")
            return {
                "tipo_documento": "No identificado",
                "nivel_confianza": "bajo",
                "informacion_clave": {},
                "raw_response": response
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return {
                "tipo_documento": "Error de parsing",
                "nivel_confianza": "bajo",
                "informacion_clave": {},
                "parsing_error": str(e),
                "raw_response": response
            }
    
    def get_service_info(self) -> Dict[str, Any]:
        """Get service information"""
        return {
            'service_name': 'MistralService_TextAnalysis',
            'version': '2.0',
            'api_endpoint': self.chat_api_url,
            'model': self.model,
            'capabilities': [
                'text_analysis',
                'legal_document_analysis', 
                'document_summarization',
                'entity_extraction'
            ],
            'note': 'OCR functionality moved to OCRService',
            'configuration': {
                'max_retries': self.max_retries,
                'timeout': self.timeout,
                'base_delay': self.base_delay,
                'max_delay': self.max_delay
            }
        }