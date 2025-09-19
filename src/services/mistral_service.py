# src/services/mistral_service.py
import json
import requests
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from shared.config import Config
from shared.exceptions import OCRBaseException

logger = logging.getLogger(__name__)
config = Config()

@dataclass
class MistralResult:
    """Result of Mistral AI analysis"""
    success: bool
    data: Dict[str, Any] = None
    error: str = ""
    raw_response: str = ""
    processing_time: float = 0.0

class MistralService:
    """Service for Mistral AI text analysis"""
    
    def __init__(self):
        self.api_key = config.MISTRAL_API_KEY
        self.api_url = "https://api.mistral.ai/v1/chat/completions"
        self.model = "mistral-large-latest"
        self.max_retries = 3
        self.timeout = 300  # 5 minutes
    
    def analyze_oficio_text(self, text: str, job_id: str) -> MistralResult:
        """Analyze oficio text with Mistral AI"""
        try:
            start_time = datetime.now()
            logger.info(f"🤖 Starting Mistral AI analysis for job {job_id}")
            
            # Log input text for debugging
            logger.info(f"📝 Input text for analysis: {len(text)} chars")
            logger.info(f"📄 Text preview: {text[:300]}...")
            
            # Prepare prompt
            prompt = self._create_analysis_prompt(text)
            logger.info(f"📋 Prompt created: {len(prompt)} chars")
            
            # Make API request
            response = self._make_api_request(prompt)
            
            if not response:
                return MistralResult(False, error="No response from Mistral API")
            
            # Log raw response for debugging
            logger.info(f"🤖 Raw Mistral response: {len(response)} chars")
            logger.info(f"📄 Response preview: {response[:500]}...")
            
            # Parse response
            parsed_data = self._parse_mistral_response(response)
            
            # Log parsed data for debugging
            logger.info(f"📊 Parsed data: tipo={parsed_data.get('tipo_oficio_detectado')}, palabras={len(parsed_data.get('palabras_clave_encontradas', []))}, personas={len(parsed_data.get('informacion_extraida', {}).get('personas', []))}")
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"✅ Mistral analysis completed in {processing_time:.2f}s")
            
            return MistralResult(
                success=True,
                data=parsed_data,
                raw_response=response,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"❌ Mistral analysis failed: {str(e)}")
            return MistralResult(False, error=str(e))
    
    def _create_analysis_prompt(self, text: str) -> str:
        """Create structured prompt for Mistral AI"""
        return f"""
        Eres un experto en análisis de documentos legales panameños. Analiza el siguiente texto de un oficio legal y extrae la información estructurada.

        TEXTO DEL OFICIO:
        {text}

        INSTRUCCIONES:
        1. Extrae toda la información disponible en formato JSON
        2. Si no encuentras un campo, usa null
        3. Para fechas, usa formato YYYY-MM-DD
        4. Para montos, extrae solo el número sin símbolos
        5. Para personas, incluye nombre, tipo y rol si está disponible

        RESPONDE ÚNICAMENTE CON UN JSON VÁLIDO CON ESTA ESTRUCTURA:
        {{
            "palabras_clave_encontradas": ["palabra1", "palabra2"],
            "tipo_oficio_detectado": "tipo",
            "nivel_confianza": "alto|medio|bajo",
            "informacion_extraida": {{
                "numero_oficio": "string o null",
                "autoridad": "string o null", 
                "fecha_emision": "YYYY-MM-DD o null",
                "fecha_recibido": "YYYY-MM-DD o null",
                "oficiado_cliente": "string o null",
                "numero_identificacion": "string o null",
                "expediente": "string o null",
                "fecha_auto": "YYYY-MM-DD o null",
                "numero_auto": "string o null",
                "monto": "number o null",
                "sucursal_recibido": "string o null",
                "carpeta": "string o null",
                "vencimiento": "YYYY-MM-DD o null",
                "personas": [
                    {{
                        "nombre": "string",
                        "tipo": "Deudor|Fiador|Testigo|Abogado|Otro",
                        "identificacion": "string o null",
                        "rol": "string o null"
                    }}
                ]
            }}
        }}
        """
    
    def _make_api_request(self, prompt: str) -> Optional[str]:
        """Make request to Mistral API with retries"""
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
                logger.info(f"🌐 Mistral API request attempt {attempt + 1}")
                
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if 'choices' in result and len(result['choices']) > 0:
                        content = result['choices'][0]['message']['content']
                        logger.info(f"✅ Mistral API success on attempt {attempt + 1}")
                        return content.strip()
                
                elif response.status_code == 429:
                    # Rate limit - wait and retry
                    wait_time = (attempt + 1) * 10
                    logger.warning(f"⏳ Rate limit hit, waiting {wait_time}s")
                    import time
                    time.sleep(wait_time)
                    continue
                
                else:
                    logger.warning(f"⚠️ API returned status {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"⏰ Timeout on attempt {attempt + 1}")
                continue
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"🌐 Request error on attempt {attempt + 1}: {str(e)}")
                continue
        
        logger.error("❌ All Mistral API attempts failed")
        return None
    
    def _parse_mistral_response(self, response: str) -> Dict[str, Any]:
        """Parse and validate Mistral AI response"""
        try:
            # Try to find JSON in response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                parsed = json.loads(json_str)
                
                # Validate structure
                if 'informacion_extraida' in parsed:
                    return parsed
            
            # If no valid JSON found, create basic structure
            logger.warning("⚠️ Could not parse Mistral response as JSON, creating basic structure")
            return {
                "palabras_clave_encontradas": [],
                "tipo_oficio_detectado": "No identificado",
                "nivel_confianza": "bajo",
                "informacion_extraida": {},
                "raw_response": response
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing error: {str(e)}")
            return {
                "palabras_clave_encontradas": [],
                "tipo_oficio_detectado": "Error de parsing",
                "nivel_confianza": "bajo",
                "informacion_extraida": {},
                "parsing_error": str(e),
                "raw_response": response
            }

