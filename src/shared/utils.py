import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
logger = logging.getLogger()
# =====================================
# FUNCIONES DE LIMPIEZA Y FORMATO
# =====================================
def clean_value_lambda(value: Any) -> str:
    """
    Versión para Lambda que preserva "No especificado" para cálculos de extracción
    """
    if value is None:
        return "No especificado"
    str_value = str(value).strip()
    if str_value in ["", "null", "None"]:
        return "No especificado"
    return str_value

def format_persons_for_lambda(personas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Formatea lista de personas para Lambda preservando "No especificado"
    """
    personas_limpia = []
    total_monto = 0.0
    for i, persona in enumerate(personas, 1):
        monto_str = clean_value_lambda(persona.get('monto', 'No especificado'))
        monto_float = parse_currency_lambda(monto_str) if monto_str != "No especificado" else 0.0
        total_monto += monto_float
        persona_limpia = {
            "secuencia": i,
            "nombre_completo": clean_value_lambda(persona.get('nombre', 'No especificado')),
            "identificacion": clean_value_lambda(persona.get('identificacion', 'No especificado')),
            "tipo_identificacion": detect_id_type_lambda(clean_value_lambda(persona.get('identificacion', 'No especificado'))),
            "monto_texto": monto_str,
            "monto_numerico": monto_float,
            "expediente": clean_value_lambda(persona.get('no_exp', 'No especificado'))
        }
        personas_limpia.append(persona_limpia)
    return {
        "total_personas": len(personas_limpia),
        "monto_total": total_monto,
        "monto_total_formateado": f"B/.{total_monto:,.2f}",
        "listado": personas_limpia
    }

def format_autos_for_lambda(autos: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Formatea la lista de autos para lambda
    """
    formatted_autos = []
    for auto in autos:
        formatted_auto = {
            "fecha_auto": clean_value_lambda(auto.get('fecha_auto')),
            "numero_auto_placa": clean_value_lambda(auto.get('numero_auto_placa')),
            "monto_auto": clean_value_lambda(auto.get('monto_auto'))
        }
        formatted_autos.append(formatted_auto)
    return formatted_autos

def parse_currency_lambda(currency_str: str) -> float:
    """
    Convierte string de moneda a float - versión simplificada
    """
    if not currency_str:
        return 0.0
    try:
        cleaned = currency_str.replace('B/.', '').replace('$', '').replace(',', '').strip()
        return float(cleaned) if cleaned else 0.0
    except:
        return 0.0

def detect_id_type_lambda(identification: str) -> str:
    """
    Detecta el tipo de identificación panameña
    """
    if not identification:
        return "No especificado"
    identification = identification.strip()
    if '-' in identification:
        parts = identification.split('-')
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            return "Cédula panameña"
        elif len(parts) >= 3:
            return "RUC"
    if identification.startswith(('3NT', '4NT', '5NT')):
        return "Identificación temporal"
    if len(identification) > 10:
        return "RUC"
    return "Otro tipo"

def generate_stats_for_lambda(personas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Genera estadísticas para Lambda
    """
    if not personas:
        return {"total_personas": 0, "monto_total": 0}
    montos = [parse_currency_lambda(clean_value_lambda(p.get('monto', '0'))) for p in personas]
    total_monto = sum(montos)
    personas_con_montos = [(p.get('nombre', ''), parse_currency_lambda(clean_value_lambda(p.get('monto', '0')))) for p in personas]
    personas_con_montos.sort(key=lambda x: x[1], reverse=True)
    return {
        "total_personas": len(personas),
        "monto_total": total_monto,
        "monto_promedio": total_monto / len(personas) if personas else 0,
        "monto_mayor": {"nombre": personas_con_montos[0][0], "monto": personas_con_montos[0][1]} if personas_con_montos else {},
        "monto_menor": {"nombre": personas_con_montos[-1][0], "monto": personas_con_montos[-1][1]} if personas_con_montos else {}
    }

def calculate_extraction_percentage(info_extraida: Dict[str, Any], personas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calcula el porcentaje de extracción de campos y análisis de calidad
    """
    campos_principales = [
        'numero_oficio', 'autoridad', 'fecha_emision', 'fecha_recibido',
        'oficiado_cliente', 'expediente', 'numero_auto', 'fecha_auto',
        'sucursal_recibido', 'numero_resolucion', 'fecha_resolucion'
    ]
    campos_opcionales = [
        'numero_identificacion', 'monto', 'carpeta', 'vencimiento', 
        'sello_recibido', 'delito', 'sello_autoridad', 'dirigido_global_bank',
        'tipo_producto', 'denuciante'
    ]
    principales_extraidos = 0
    principales_detalle = {}
    for campo in campos_principales:
        valor = clean_value_lambda(info_extraida.get(campo))
        is_extracted = valor not in ["No especificado", ""]
        principales_detalle[campo] = {
            "extraido": is_extracted,
            "valor": valor
        }
        if is_extracted:
            principales_extraidos += 1
    opcionales_extraidos = 0
    opcionales_detalle = {}
    for campo in campos_opcionales:
        valor = clean_value_lambda(info_extraida.get(campo))
        is_extracted = valor not in ["No especificado", ""]
        opcionales_detalle[campo] = {
            "extraido": is_extracted,
            "valor": valor
        }
        if is_extracted:
            opcionales_extraidos += 1
    personas_completas = 0
    personas_detalle = []
    for persona in personas:
        nombre_ok = clean_value_lambda(persona.get('nombre', '')) not in ["No especificado", ""]
        id_ok = clean_value_lambda(persona.get('identificacion', '')) not in ["No especificado", ""]
        monto_ok = clean_value_lambda(persona.get('monto', '')) not in ["No especificado", ""]
        campos_persona_extraidos = sum([nombre_ok, id_ok, monto_ok])
        es_completa = campos_persona_extraidos >= 2
        personas_detalle.append({
            "nombre_extraido": nombre_ok,
            "identificacion_extraida": id_ok,
            "monto_extraido": monto_ok,
            "completitud": f"{campos_persona_extraidos}/3",
            "es_completa": es_completa
        })
        if es_completa:
            personas_completas += 1
    porcentaje_campos = (principales_extraidos / len(campos_principales)) * 100 if campos_principales else 0
    porcentaje_personas = (personas_completas / len(personas)) * 100 if personas else 0
    return {
        "resumen": {
            "calidad_extraccion": "ALTA" if porcentaje_campos > 80 else "MEDIA" if porcentaje_campos > 50 else "BAJA",
            "porcentaje_total_campos": porcentaje_campos,
            "porcentaje_personas_completas": porcentaje_personas
        },
        "detalle_campos_principales": principales_detalle,
        "detalle_campos_opcionales": opcionales_detalle,
        "detalle_personas": personas_detalle
    }

def log_extraction_summary(formatted_response: Dict[str, Any]):
    """
    Loguea un resumen de la extracción para monitoreo
    """
    resumen = formatted_response.get('analisis_extraccion', {}).get('resumen', {})
    print(f"Resumen extracción: {json.dumps(resumen, ensure_ascii=False)}")

def detect_document_type(event: Dict[str, Any]) -> str:
    """
    Detecta automáticamente el tipo de documento basado en parámetros del evento
    """
    # Verificar si se especifica explícitamente el tipo
    if 'document_type' in event:
        return event['document_type']
    
    # Verificar por annotation_type específico
    annotation_type = event.get('annotation_type', 'document')
    
    # Verificar por custom_prompt o parámetros
    custom_prompt = event.get('custom_prompt', '').lower()
    
    # Palabras clave para oficios legales
    legal_keywords = [
        'oficio', 'secuestro', 'embargo', 'levantamiento', 'citación',
        'investigación', 'sucesión', 'aprehensión', 'juzgado', 'tribunal',
        'allanamiento', 'diligencia', 'exhibitoria', 'inspección', 'ocular',
        'traslado', 'fondos', 'legal', 'panama', 'autoridad', 'expediente'
    ]
    
    # Convertir event a string para buscar palabras clave
    event_str = json.dumps(event, default=str).lower()
    
    # Buscar palabras clave en el evento completo
    if any(keyword in event_str for keyword in legal_keywords):
        return 'legal_document'
    
    # Si viene con 'legal' en annotation_type
    if 'legal' in annotation_type:
        return 'legal_document'
    
    # Por defecto, para documentos panameños asumir legal
    return 'legal_document'

def prepare_document(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepara el documento para el procesamiento OCR
    """
    if 'pdf_content' in event:
        return {"document_base64": event['pdf_content'], "document_type": "pdf"}
    elif 'image_content' in event:
        return {"document_base64": event['image_content'], "document_type": "image"}
    elif 'document_url' in event:
        return {"document_url": event['document_url']}
    else:
        raise ValueError("Debe proporcionar 'pdf_content', 'image_content' o 'document_url'")

def build_api_payload(document_data: Dict[str, Any], annotation_type: str, custom_prompt: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construye el payload para la API de Mistral OCR - VERSIÓN CORREGIDA
    Solo incluye campos que la API acepta
    """
    payload = {
        "model": "mistral-ocr-latest",
        "include_image_base64": True
    }
    
    # Configurar el documento
    if "document_url" in document_data:
        payload["document"] = {"document_url": document_data["document_url"]}
    else:
        # Para base64, usar el formato data URL
        base64_data = document_data["document_base64"]
        if document_data["document_type"] == "pdf":
            data_url = f"data:application/pdf;base64,{base64_data}"
        else:  # imagen
            data_url = f"data:image/jpeg;base64,{base64_data}"
        
        payload["document"] = {"document_url": data_url}
    
    # Agregar páginas específicas si se proporcionan
    if 'pages' in event:
        payload["pages"] = event['pages']
    
    # REMOVER ESTOS CAMPOS - NO SON SOPORTADOS POR LA API
    # NO agregar annotation_type ni custom_prompt al payload principal
    
    # Detectar tipo de documento para configurar schemas internamente
    document_type = detect_document_type(event)
    
    # Si necesitas configurar annotations específicas, usar los campos correctos de la API
    if document_type == 'legal_document':
        logger.info("Configurando schema especializado para oficio legal panameño")
        
        # Para documentos legales, usar prompt especializado si no se proporciona uno custom
        if custom_prompt == 'Extract and structure key information from this document':
            custom_prompt = get_legal_classification_prompt()
        
        # Usar los campos correctos para annotations según la documentación de Mistral
        if annotation_type in ['bbox', 'both']:
            payload["bbox_annotation_format"] = create_bbox_annotation_schema(custom_prompt)
        
        if annotation_type in ['document', 'both']:
            payload["document_annotation_format"] = create_legal_document_annotation_schema(custom_prompt)
    else:
        # Para documentos generales, usar el schema original
        logger.info("Usando schema estándar para documento general")
        
        if annotation_type in ['bbox', 'both']:
            payload["bbox_annotation_format"] = create_bbox_annotation_schema(custom_prompt)
        
        if annotation_type in ['document', 'both']:
            payload["document_annotation_format"] = create_document_annotation_schema(custom_prompt)
    
    # Log del payload final (sin mostrar el contenido base64 completo)
    payload_info = {k: v if k != 'document' else 'DOCUMENT_DATA_PRESENT' for k, v in payload.items()}
    logger.info(f"📤 Payload final construido: {list(payload_info.keys())}")
    
    return payload

def create_bbox_annotation_schema(custom_prompt: str) -> Dict[str, Any]:
    """
    Schema para bbox annotations
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "schema": {
                "properties": {
                    "element_type": {"title": "Element_Type", "type": "string"},
                    "content_description": {"title": "Content_Description", "type": "string"},
                    "extracted_data": {"title": "Extracted_Data", "type": "string"}
                },
                "required": ["element_type", "content_description", "extracted_data"],
                "title": "BBoxAnnotation",
                "type": "object",
                "additionalProperties": False
            },
            "name": "bbox_annotation",
            "strict": True
        }
    }

def create_document_annotation_schema(custom_prompt: str) -> Dict[str, Any]:
    """
    Schema para document annotations generales
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "schema": {
                "properties": {
                    "document_type": {"title": "Document_Type", "type": "string"},
                    "main_content": {"title": "Main_Content", "type": "string"},
                    "key_information": {"title": "Key_Information", "type": "string"},
                    "language": {"title": "Language", "type": "string"}
                },
                "required": ["document_type", "main_content", "key_information", "language"],
                "title": "DocumentAnnotation",
                "type": "object",
                "additionalProperties": False
            },
            "name": "document_annotation",
            "strict": True
        }
    }

def create_legal_document_annotation_schema(custom_prompt: str) -> Dict[str, Any]:
    """
    Schema mejorado y más específico para oficios legales panameños
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "schema": {
                "properties": {
                    "palabras_clave_encontradas": {
                        "title": "Palabras_Clave_Encontradas",
                        "description": "Lista de palabras clave legales identificadas en el documento",
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "tipo_oficio_detectado": {
                        "title": "Tipo_Oficio_Detectado", 
                        "description": "Tipo de oficio identificado basado en palabras clave",
                        "type": "string"
                    },
                    "nivel_confianza": {
                        "title": "Nivel_Confianza",
                        "description": "Nivel de confianza en la extracción",
                        "type": "string",
                        "enum": ["ALTA", "MEDIA", "BAJA"]
                    },
                    "informacion_extraida": {
                        "title": "Informacion_Extraida",
                        "description": "Variables específicas extraídas del documento",
                        "type": "object",
                        "properties": {
                            "numero_oficio": {
                                "title": "Numero_Oficio",
                                "description": "N° de Oficio / Número de Oficio",
                                "type": "string"
                            },
                            "autoridad": {
                                "title": "Autoridad", 
                                "description": "Autoridad / Autoridad Competente",
                                "type": "string"
                            },
                            "fecha_emision": {
                                "title": "Fecha_Emision",
                                "description": "Fecha de Emisión del documento",
                                "type": "string"
                            },
                            "fecha_recibido": {
                                "title": "Fecha_Recibido",
                                "description": "Fecha de Recibido",
                                "type": "string"
                            },
                            "oficiado_cliente": {
                                "title": "Oficiado_Cliente",
                                "description": "Oficiado / Cliente al que se dirige el oficio (Global Bank, otra entidad, o persona específica)",
                                "type": "string"
                            },
                            "numero_identificacion": {
                                "title": "Numero_Identificacion",
                                "description": "N° de Identificación / Cédula/ID del Cliente",
                                "type": "string"
                            },
                            "expediente": {
                                "title": "Expediente",
                                "description": "Expediente / Número de Expediente",
                                "type": "string"
                            },
                            "fecha_auto": {
                                "title": "Fecha_Auto",
                                "description": "Fecha de Auto",
                                "type": "string"
                            },
                            "numero_auto": {
                                "title": "Numero_Auto",
                                "description": "N° de Auto / Auto o placa",
                                "type": "string"
                            },
                            "monto": {
                                "title": "Monto",
                                "description": "Monto / Monto B/.",
                                "type": "string"
                            },
                            "sucursal_recibido": {
                                "title": "Sucursal_Recibido",
                                "description": "Sucursal de Recibido / Provincia donde se recibe oficio",
                                "type": "string"
                            },
                            "carpeta": {
                                "title": "Carpeta",
                                "description": "Carpeta del expediente",
                                "type": "string"
                            },
                            "vencimiento": {
                                "title": "Vencimiento",
                                "description": "Vencimiento / Fecha de Cumplimiento",
                                "type": "string"
                            },
                            "sello_recibido": {
                                "title": "Sello_Recibido",
                                "description": "Sello de Recibido / Dirigido a Global Bank",
                                "type": "string"
                            },
                            "sello_autoridad": {
                                "title": "Sello_Autoridad",
                                "description": "Sello de Autoridad / Sello de autoridad",
                                "type": "string"
                            },
                            "dirigido_global_bank": {
                                "title": "Dirigido_Global_Bank",
                                "description": "Indicación si está dirigido a Global Bank",
                                "type": "string"
                            },
                            "numero_resolucion": {
                                "title": "Numero_Resolucion",
                                "description": "N° de Resolución / Resolución",
                                "type": "string"
                            },
                            "fecha_resolucion": {
                                "title": "Fecha_Resolucion",
                                "description": "Fecha de Resolución",
                                "type": "string"
                            },
                            "delito": {
                                "title": "Delito",
                                "description": "Delito mencionado en el documento",
                                "type": "string"
                            },
                            "tipo_producto": {
                                "title": "Tipo_Producto",
                                "description": "Tipo de producto bancario o financiero mencionado",
                                "type": "string"
                            },
                            "denuciante": {
                                "title": "Denuciante",
                                "description": "Persona o entidad que presenta la denuncia",
                                "type": "string"
                            }
                        },
                        "additionalProperties": False
                    },
                    "lista_personas": {
                        "title": "Lista_Personas",
                        "description": "Lista de personas mencionadas en el documento",
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "no_exp": {
                                    "title": "No_Exp",
                                    "description": "Número de expediente de la persona",
                                    "type": "string"
                                },
                                "nombre": {
                                    "title": "Nombre",
                                    "description": "Nombre completo de la persona",
                                    "type": "string"
                                },
                                "identificacion": {
                                    "title": "Identificacion",
                                    "description": "Cédula o documento de identificación",
                                    "type": "string"
                                },
                                "monto": {
                                    "title": "Monto",
                                    "description": "Monto asociado a la persona si aplica",
                                    "type": "string"
                                }
                            },
                            "required": ["nombre"],
                            "additionalProperties": False
                        }
                    },
                    "lista_autos": {
                        "title": "Lista_Autos",
                        "description": "Lista de autos mencionados en el documento",
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "fecha_auto": {
                                    "title": "Fecha_Auto",
                                    "description": "Fecha del auto",
                                    "type": "string"
                                },
                                "numero_auto_placa": {
                                    "title": "Numero_Auto_Placa",
                                    "description": "Número de auto o placa",
                                    "type": "string"
                                },
                                "monto_auto": {
                                    "title": "Monto_Auto",
                                    "description": "Monto del auto si aplica",
                                    "type": "string"
                                }
                            },
                            "required": ["numero_auto_placa"],
                            "additionalProperties": False
                        }
                    },
                    "texto_completo": {
                        "title": "Texto_Completo",
                        "description": f"Transcripción completa del texto del documento. {custom_prompt}",
                        "type": "string"
                    },
                    "observaciones": {
                        "title": "Observaciones",
                        "description": "Observaciones adicionales sobre calidad del documento o dificultades en la extracción",
                        "type": "string"
                    }
                },
                "required": ["palabras_clave_encontradas", "tipo_oficio_detectado", "nivel_confianza", "informacion_extraida", "lista_personas", "lista_autos", "texto_completo"],
                "title": "OficioLegalPanama",
                "type": "object",
                "additionalProperties": False
            },
            "name": "oficio_legal_panama",
            "strict": True
        }
    }

def get_legal_classification_prompt() -> str:
    """
    Devuelve un prompt especializado para documentos legales panameños
    """
    return """Analiza este documento legal panameño y extrae ÚNICAMENTE la información que encuentres claramente visible.

PALABRAS CLAVE A BUSCAR (incluye en respuesta solo las que encuentres):

ALLANAMIENTOS: "Allanamiento", "Solicitud de Allanamiento", "Allanamiento y Registro", "Incautar"
APREHENSIONES: "Se Aprehendan", "Aprehensión", "Dispone", "Resuelve"  
CITACIÓN: "Presentarse", "diligencia de entrevista", "Rendir Entrevista", "Comparecer a Audiencia", "Citación en calidad de testigo", "Entrevista judicial", "Notificar el deber de comparecer", "se presente", "entrevista", "se cita a"
DILIGENCIA EXHIBITORIA: "diligencia exhibitoria"
EMBARGO: "Certificado de Depósito Judicial", "Cheque de Gerencia", "embargo", "embargo de cuentas", "embárguese", "retener y remitir fondos", "cheque de gerencia a favor de", "certificado de depósito judicial", "remitir", "confección de cheque de gerencia", "elevar a embargo", "Ordena formal embargo", "Decreta formal embargo", "retener y poner a disposición de este Juzgado", "formal embargo"
INSPECCIÓN OCULAR: "inspección ocular"
INVESTIGACIÓN: "investigación", "solicitud de información", "remitir datos", "detalle de cuentas", "facilitar información", "proporcione información", "blanqueo de capitales", "cámara de videovigilancia", "patrimonio económico", "estafa", "hurto", "robo", "fe pública"
JUICIO DE SUCESIÓN: "sucesión", "adjudicación de fondos", "heredero", "declaratoria de herederos", "testamento", "partición de bienes", "adjudicación", "juicio de sucesión"
LEVANTAMIENTO: "levantamiento", "levantamiento de la medida", "levantamiento parcial", "liberar la cuenta", "declara extinguida la obligación", "dejar sin efecto", "desistimiento del secuestro", "orden de poner a disposición la suma de dinero retenida", "Ponga a disposición de", "desistimiento del proceso", "levantamiento y cierre", "ordenar el levantamiento parcial del secuestro", "levántese la medida", "liberación de fondos", "ordenar el levantamiento", "desbloquear cuenta", "deje sin efecto el", "cancelación"
SECUESTRO: "secuestro", "retención de fondos", "bloqueo de cuenta", "medida cautelar de secuestro", "retener fondos", "retener", "secuestrar", "poner a disposición de juzgado", "poner a disposición de institución", "sírvase poner a orden y disposición de este juzgado", "Ordenamos el secuestro", "Sírvase retener", "decretado formal secuestro", "se ha decretado secuestro", "Sírvase poner a orden y disposición de este despacho", "cautelación"
TRASLADO DE FONDOS: "El comiso", "Trasladar los fondos", "Puestas a Disposición del Ministerio de Economía y Finanzas", "Transferir dichas sumas", "Sean aprehendidos"

VARIABLES A EXTRAER (solo si están claramente visibles):
- N° de Oficio / Número de Oficio
- Autoridad / Autoridad Competente  
- Fecha de Emisión
- Fecha de Recibido
- Oficiado / Cliente al que se dirige
- N° de Identificación / Cédula/ID del Cliente
- Expediente / Número de Expediente
- Fecha de Auto
- N° de Auto / Auto
- Monto / Monto B/.
- Sucursal de Recibido / Provincia donde se recibe oficio
- Carpeta
- Vencimiento / Fecha de Cumplimiento
- Sello de Recibido / Dirigido a Global Bank
- Sello de Autoridad / Sello de autoridad
- Dirigido a Global Bank (indicación específica)
- N° de Resolución / Resolución
- Fecha de Resolución
- Delito
- Tipo de producto bancario o financiero
- Denuciante

INSTRUCCIONES IMPORTANTES:
1. NO inventes información que no esté claramente visible
2. Si hay una lista de personas, extrae: Expediente, Nombre, Identificación, Monto (si aplica)
3. Si hay una lista de autos, extraer: Fecha de Auto, Numero de Auto o placa, Monto del auto (si aplica)
4. Transcribe el texto completo del documento
5. Indica el nivel de confianza: ALTA (información muy clara), MEDIA (legible pero con dudas), BAJA (difícil de leer)
6. Solo incluye las palabras clave que efectivamente encuentres en el documento"""