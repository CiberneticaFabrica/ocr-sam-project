# src/crm_integrator/app.py - SCHEMA COMPATIBLE VERSION

import json
import boto3
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

# Configuración existente
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Variables de entorno existentes
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']
BATCH_TRACKING_TABLE = os.environ.get('BATCH_TRACKING_TABLE', 'OCRBatchTracking')
JOB_TRACKING_TABLE = os.environ.get('JOB_TRACKING_TABLE', 'OCRJobTracking')
CREATIO_URL = os.environ.get('CREATIO_URL', 'https://11006608-demo.creatio.com')
CREATIO_USERNAME = os.environ.get('CREATIO_USERNAME', 'Supervisor')
CREATIO_PASSWORD = os.environ.get('CREATIO_PASSWORD')

# CloudWatch para métricas
cloudwatch = boto3.client('cloudwatch')

def put_crm_metric(metric_name: str, value: float, unit: str = 'Count', dimensions: Dict[str, str] = None):
    """Enviar métrica personalizada a CloudWatch para CRM"""
    try:
        metric_data = {
            'MetricName': metric_name,
            'Value': value,
            'Unit': unit,
            'Timestamp': datetime.utcnow()
        }
        
        if dimensions:
            metric_data['Dimensions'] = [{'Name': k, 'Value': v} for k, v in dimensions.items()]
        
        cloudwatch.put_metric_data(
            Namespace='CRM/Integration',
            MetricData=[metric_data]
        )
    except Exception as e:
        logger.warning(f"Failed to send CRM metric {metric_name}: {str(e)}")

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Procesa resultados OCR mejorados y los inserta en Creatio CRM
    VERSIÓN COMPATIBLE CON SCHEMA EXISTENTE
    """
    try:
        logger.info(f"🏢 Schema-compatible CRM Integrator event received: {json.dumps(event, default=str)}")
        
        results = []
        for record in event.get('Records', []):
            try:
                result = process_enhanced_sqs_message(record)
                results.append(result)
            except Exception as e:
                logger.error(f"❌ Error procesando mensaje SQS: {str(e)}")
                results.append({'success': False, 'error': str(e)})
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'processed_messages': len(results),
                'results': results,
                'enhanced_processing': True,
                'schema_compatible': True
            })
        }
        
    except Exception as e:
        logger.error(f"❌ Error en Schema-compatible CRM integrator: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def process_enhanced_sqs_message(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procesa un mensaje individual de SQS con resultado OCR mejorado
    USANDO SOLO CAMPOS CONOCIDOS
    """
    try:
        message_body = json.loads(record['body'])
        job_id = message_body.get('job_id')
        batch_id = message_body.get('batch_id')
        is_enhanced = message_body.get('enhanced_processing', False)
        
        logger.info(f"📄 Procesando inserción CRM compatible para job {job_id} (Enhanced: {is_enhanced})")
        
        # Obtener resultado OCR desde S3
        ocr_result = get_enhanced_ocr_result_from_s3(job_id)
        
        if not ocr_result:
            logger.error(f"❌ No se encontró resultado OCR válido para job {job_id}")
            update_tracking_status(batch_id, job_id, 'crm_error', 'No OCR result found')
            return {'success': False, 'job_id': job_id, 'error': 'No OCR result found'}
        
        # Verificar si tiene datos estructurados
        has_structured_data = bool(ocr_result.get('structured_data_raw'))
        has_classification = bool(ocr_result.get('clasificacion'))
        
        logger.info(f"📊 OCR Result Analysis for {job_id}:")
        logger.info(f"  - Has structured data: {has_structured_data}")
        logger.info(f"  - Has classification: {has_classification}")
        logger.info(f"  - Persons count: {len(ocr_result.get('lista_personas', {}).get('listado', []))}")
        
        # Mapear datos para Creatio usando SOLO campos conocidos
        crm_payload = map_ocr_data_to_known_schema(ocr_result, job_id, batch_id, has_structured_data)
        
        # Crear solicitud en Creatio con campos compatibles
        creatio_response = create_schema_compatible_creatio_request(crm_payload, has_structured_data)
        
        if creatio_response.get('success'):
            logger.info(f"✅ Solicitud compatible creada en Creatio para job {job_id}")
            
            # Enviar métricas de éxito
            put_crm_metric('IntegrationSuccess', 1, dimensions={'ProcessingType': 'schema_compatible'})
            put_crm_metric('PersonsCreated', creatio_response.get('persons_created', 0))
            
            update_tracking_status(batch_id, job_id, 'completed', 
                                 f"CRM ID: {creatio_response.get('crm_id')} (Schema Compatible)")
            return {
                'success': True,
                'job_id': job_id,
                'crm_id': creatio_response.get('crm_id'),
                'enhanced_processing': has_structured_data,
                'schema_compatible': True,
                'persons_created': creatio_response.get('persons_created', 0)
            }
        else:
            logger.error(f"❌ Error creando solicitud compatible en Creatio: {creatio_response.get('error')}")
            
            # Enviar métricas de error
            put_crm_metric('IntegrationError', 1, dimensions={'ErrorType': 'creatio_error'})
            
            update_tracking_status(batch_id, job_id, 'crm_error', 
                                 creatio_response.get('error', 'Unknown error'))
            return {
                'success': False,
                'job_id': job_id,
                'error': creatio_response.get('error')
            }
        
    except Exception as e:
        logger.error(f"❌ Error procesando mensaje compatible: {str(e)}")
        return {'success': False, 'error': str(e)}

def get_enhanced_ocr_result_from_s3(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene el resultado OCR mejorado desde S3 - VERSIÓN CORREGIDA
    """
    try:
        response = s3_client.get_object(
            Bucket=S3_BUCKET_NAME,
            Key=f'jobs/{job_id}/result.json'
        )
        result = json.loads(response['Body'].read())
        
        logger.info(f"✅ OCR result obtained for {job_id}")
        logger.info(f"📋 Result keys: {list(result.keys())}")
        
        # Log detalles para debugging
        logger.info(f"🔍 Result details:")
        logger.info(f"  - Success: {result.get('success')}")
        logger.info(f"  - Text length: {len(result.get('texto_completo', ''))}")
        logger.info(f"  - Has structured_data_raw: {bool(result.get('structured_data_raw'))}")
        logger.info(f"  - Has clasificacion: {bool(result.get('clasificacion'))}")
        logger.info(f"  - Has informacion_extraida: {bool(result.get('informacion_extraida'))}")
        logger.info(f"  - Enhanced processing: {result.get('enhanced_processing')}")
        logger.info(f"  - Confidence: {result.get('confidence')}")
        
        # Validar que tiene estructura utilizando la función corregida
        if validate_ocr_result_structure(result):
            return result
        else:
            logger.warning(f"⚠️ Invalid OCR structure for {job_id}")
            return None
            
    except s3_client.exceptions.NoSuchKey:
        logger.warning(f"⚠️ No OCR result found for job {job_id}")
        return None
    except Exception as e:
        logger.error(f"❌ Error obteniendo resultado OCR: {str(e)}")
        return None

def validate_ocr_result_structure(result: Dict[str, Any]) -> bool:
    """
    Valida estructura de resultado OCR - VERSIÓN CORREGIDA
    """
    try:
        if not isinstance(result, dict):
            logger.warning(f"Result is not a dict: {type(result)}")
            return False
        
        # Verificar que es un resultado exitoso
        if not result.get('success', False):
            logger.warning(f"Result success is False: {result.get('success')}")
            return False
        
        # Verificar que tiene texto O datos estructurados
        has_text = bool(result.get('texto_completo', '').strip())
        has_structured_data = bool(result.get('structured_data_raw'))
        has_classification = bool(result.get('clasificacion'))
        has_info_extraida = bool(result.get('informacion_extraida'))
        
        logger.info(f"Validation check - Text: {has_text}, Structured: {has_structured_data}, Classification: {has_classification}, Info: {has_info_extraida}")
        
        # Aceptar si tiene cualquiera de estos elementos
        if has_text or has_structured_data or has_classification or has_info_extraida:
            logger.info("✅ OCR result structure validation passed")
            return True
        
        logger.warning("❌ OCR result has no usable content")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error validating OCR structure: {str(e)}")
        return False

def map_ocr_data_to_known_schema(ocr_data: Dict[str, Any], job_id: str, batch_id: str, has_structured_data: bool) -> Dict[str, Any]:
    """
    Mapea datos OCR al formato de Creatio usando SOLO campos conocidos que existen
    """
    try:
        logger.info(f"📄 Mapping OCR data to known Creatio schema")
        
        # Función auxiliar para valores seguros
        def safe_string(value, default="No especificado", max_length: int = None):
            if not value or str(value).strip() in ['', 'null', 'None', 'No especificado']:
                return default
            
            cleaned_value = str(value).strip()
            
            if max_length and len(cleaned_value) > max_length:
                cleaned_value = cleaned_value[:max_length-3] + "..."
            
            return cleaned_value
        
        def safe_number(value, default=0.0):
            try:
                if not value or str(value).strip() in ['', 'null', 'None']:
                    return default
                
                clean_value = str(value).replace('B/.', '').replace(',', '').strip()
                return float(clean_value) if clean_value else default
            except:
                return default
        
        # Extraer información disponible
        info_extraida = ocr_data.get('informacion_extraida', {})
        clasificacion = ocr_data.get('clasificacion', {})
        structured_data = ocr_data.get('structured_data_raw', {})
        
        # Si hay datos estructurados, usarlos como fuente primaria
        if structured_data and 'informacion_general' in structured_data:
            info_general = structured_data['informacion_general']
            enhanced_info = {**info_extraida, **info_general}
        else:
            enhanced_info = info_extraida
        
        # 🔧 USAR SOLO CAMPOS CONOCIDOS DE CREATIO
        crm_payload = {
            # Campos básicos que sabemos que existen
            "DocumentId": job_id,
            "BatchId": batch_id,
            "DocumentType": "Oficio Legal",
            
            # Información básica del oficio
            "OficioNumber": safe_string(enhanced_info.get('numero_oficio', ''), max_length=50),
            "Authority": safe_string(enhanced_info.get('autoridad', enhanced_info.get('autoridad_emisora', '')), max_length=200),
            "ClientTarget": safe_string(enhanced_info.get('oficiado_cliente', enhanced_info.get('destinatario', '')), max_length=300),
            "ExpedientNumber": safe_string(enhanced_info.get('expediente', ''), max_length=50),
            
            # Fechas en formato ISO
            "IssueDate": parse_date_for_creatio(enhanced_info.get('fecha_emision', enhanced_info.get('fecha', '')), nullable=False),
            "ReceivedDate": parse_date_for_creatio(enhanced_info.get('fecha_recibido', ''), nullable=False),
            "DueDate": parse_date_for_creatio(enhanced_info.get('vencimiento', ''), nullable=False),
            
            # Clasificación y metadatos
            "DocumentClassification": safe_string(clasificacion.get('tipo_oficio', ocr_data.get('tipo_oficio_detectado', ''))),
            "ClassificationConfidence": safe_string(clasificacion.get('confianza', ocr_data.get('nivel_confianza', 'medio'))),
            "KeywordsFound": ', '.join(ocr_data.get('palabras_clave_encontradas', [])) or "Ninguna",
            
            # Monto y datos numéricos
            "Amount": safe_number(enhanced_info.get('monto', '')),
            
            # Texto y observaciones
            "Subject": safe_string(enhanced_info.get('asunto', 'Oficio procesado automáticamente')),
            "FullText": ocr_data.get('texto_completo', '')[:4000] or "Sin texto",
            
            # Metadatos de procesamiento
            "ProcessedAt": datetime.utcnow().isoformat(),
            "ProcessingSource": "Enhanced Automated OCR" if has_structured_data else "Basic Automated OCR",
            
            # Estado y prioridad
            "Status": "Pending Review",
            "Priority": determine_priority_from_data(enhanced_info, ocr_data, clasificacion),
            "RequiresUrgentAction": requires_urgent_action_from_data(enhanced_info, ocr_data, clasificacion),
            
            # Estadísticas
            "PersonsCount": len(ocr_data.get('lista_personas', {}).get('listado', [])),
            "TotalAmount": ocr_data.get('lista_personas', {}).get('monto_total', 0)
        }
        
        # Agregar personas si existen
        lista_personas = ocr_data.get('lista_personas', {})
        if isinstance(lista_personas, dict) and 'listado' in lista_personas:
            personas = lista_personas['listado']
            if personas:
                crm_payload["InvolvedPersons"] = format_persons_for_creatio(personas)
        
        logger.info(f"📊 Compatible CRM payload created: {len(crm_payload)} fields")
        logger.info(f"  - Persons: {crm_payload.get('PersonsCount', 0)}")
        logger.info(f"  - Classification: {crm_payload.get('DocumentClassification', 'N/A')}")
        logger.info(f"  - Structured data: {has_structured_data}")
        
        # 📊 LOG DETALLADO DE DATOS EXTRAÍDOS DEL OCR
        logger.info(f"🔍 DATOS EXTRAÍDOS DEL OCR:")
        logger.info(f"   📄 Número de oficio: {enhanced_info.get('numero_oficio', 'No encontrado')}")
        logger.info(f"   🏛️  Autoridad: {enhanced_info.get('autoridad', enhanced_info.get('autoridad_emisora', 'No encontrada'))}")
        logger.info(f"   🏦 Cliente/oficiado: {enhanced_info.get('oficiado_cliente', enhanced_info.get('destinatario', 'No encontrado'))}")
        logger.info(f"   📁 Expediente: {enhanced_info.get('expediente', 'No encontrado')}")
        logger.info(f"   📅 Fecha emisión: {enhanced_info.get('fecha_emision', enhanced_info.get('fecha', 'No encontrada'))}")
        logger.info(f"   📅 Fecha recibido: {enhanced_info.get('fecha_recibido', 'No encontrada')}")
        logger.info(f"   📅 Vencimiento: {enhanced_info.get('vencimiento', 'No encontrado')}")
        logger.info(f"   💰 Monto: {enhanced_info.get('monto', 'No encontrado')}")
        logger.info(f"   📝 Asunto: {enhanced_info.get('asunto', 'No encontrado')}")
        
        # Mostrar clasificación
        logger.info(f"   🏷️  Clasificación OCR:")
        logger.info(f"      - Tipo: {clasificacion.get('tipo_oficio', 'No clasificado')}")
        logger.info(f"      - Trámite: {clasificacion.get('tramite', 'No especificado')}")
        logger.info(f"      - Departamento: {clasificacion.get('departamento', 'No especificado')}")
        logger.info(f"      - Confianza: {clasificacion.get('confianza', 'No especificada')}")
        
        # Mostrar palabras clave
        palabras_clave = ocr_data.get('palabras_clave_encontradas', [])
        if palabras_clave:
            logger.info(f"   🔑 Palabras clave encontradas: {', '.join(palabras_clave)}")
        else:
            logger.info(f"   🔑 Palabras clave: Ninguna encontrada")
        
        # Mostrar personas extraídas
        lista_personas = ocr_data.get('lista_personas', {})
        if isinstance(lista_personas, dict) and 'listado' in lista_personas:
            personas_lista = lista_personas['listado']
            logger.info(f"   👥 Personas extraídas: {len(personas_lista)}")
            for i, persona in enumerate(personas_lista, 1):
                logger.info(f"      Persona {i}: {persona.get('nombre_completo', 'Sin nombre')}")
                logger.info(f"        - ID: {persona.get('identificacion', 'N/A')}")
                logger.info(f"        - Monto: {persona.get('monto_numerico', 0.0)}")
        else:
            logger.info(f"   👥 Personas extraídas: 0 (lista_personas no válida o vacía)")
        
        return crm_payload
        
    except Exception as e:
        logger.error(f"❌ Error mapeando datos compatibles: {str(e)}")
        raise

def format_persons_for_creatio(personas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Formatea lista de personas para Creatio usando el schema real de NdosPersonasOCR
    """
    formatted_persons = []
    
    try:
        for persona in personas:
            if not persona or not isinstance(persona, dict):
                continue
            
            # Extraer nombre completo y dividirlo según el schema real
            nombre_completo = persona.get('nombre_completo', '')
            nombres = nombre_completo.split() if nombre_completo else []
            
            # Usar los campos que ya pueden existir o extraer del nombre completo
            formatted_person = {
                "nombre_completo": nombre_completo,
                "identificacion": persona.get('identificacion', ''),
                "monto_numerico": persona.get('monto_numerico', 0.0),
                "expediente": persona.get('expediente', ''),
                "observaciones": persona.get('observaciones', f"Persona extraída por OCR - Secuencia: {persona.get('secuencia', 0)}"),
                
                # Campos de nombre divididos según schema real de NdosPersonasOCR
                "nombre": persona.get('nombre', nombres[0] if nombres else ''),
                "nombre_segundo": persona.get('nombre_segundo', ' '.join(nombres[1:-2]) if len(nombres) > 3 else ''),
                "apellido_paterno": persona.get('apellido_paterno', nombres[-2] if len(nombres) >= 2 else ''),
                "apellido_materno": persona.get('apellido_materno', nombres[-1] if len(nombres) >= 3 else '')
            }
            formatted_persons.append(formatted_person)
        
        logger.info(f"Schema-compatible persons formatted: {len(formatted_persons)} persons")
        return formatted_persons
        
    except Exception as e:
        logger.error(f"Error formatting schema-compatible persons: {str(e)}")
        return []

def determine_priority_from_data(info_extraida: Dict[str, Any], ocr_data: Dict[str, Any], 
                                clasificacion: Dict[str, Any]) -> str:
    """Determina prioridad usando clasificación"""
    try:
        tipo_oficio = clasificacion.get('tipo_oficio', '').lower()
        
        # Tipos de oficio de alta prioridad
        high_priority_tipos = [
            'secuestro', 'embargo', 'aprehensión', 'allanamiento', 
            'citación', 'levantamiento'
        ]
        
        if any(keyword in tipo_oficio for keyword in high_priority_tipos):
            return "High"
        
        # Verificar montos altos
        monto_total = ocr_data.get('lista_personas', {}).get('monto_total', 0)
        if monto_total > 50000:
            return "High"
        elif monto_total > 10000:
            return "Medium"
        
        return "Medium"
        
    except Exception as e:
        logger.error(f"Error determining priority: {str(e)}")
        return "Medium"

def requires_urgent_action_from_data(info_extraida: Dict[str, Any], ocr_data: Dict[str, Any], 
                                    clasificacion: Dict[str, Any]) -> bool:
    """Determina si requiere acción urgente"""
    try:
        tipo_oficio = clasificacion.get('tipo_oficio', '').lower()
        
        urgent_tipos = [
            'secuestro', 'embargo', 'aprehensión', 'allanamiento', 
            'citación', 'levantamiento'
        ]
        
        return any(keyword in tipo_oficio for keyword in urgent_tipos)
        
    except Exception as e:
        logger.error(f"Error checking urgent action: {str(e)}")
        return False

def prepare_known_case_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    🔧 PREPARAR DATOS USANDO SOLO CAMPOS CONOCIDOS QUE EXISTEN EN CREATIO
    """
    try:
        def safe_string(value: Any, max_length: int = None, default: str = "") -> str:
            if value is None or str(value).strip() in ['', 'null', 'None', 'No especificado']:
                return default
            
            clean_value = str(value).strip()
            clean_value = clean_value.replace('\x00', '').replace('\r', '').replace('\n', ' ')
            
            if max_length and len(clean_value) > max_length:
                clean_value = clean_value[:max_length-3] + "..."
            
            return clean_value
        
        def safe_date(date_str: str) -> str:
            if not date_str or date_str in ['No especificado', 'No especificada', '', 'null', None]:
                return "1900-01-01"
            
            import re
            if re.match(r'^\d{4}-\d{2}-\d{2}$', str(date_str)):
                return str(date_str)
            else:
                return "1900-01-01"
        
        def safe_number(value: Any, default: float = 0.0) -> float:
            try:
                if value is None or str(value).strip() in ['', 'null', 'None']:
                    return default
                
                clean_value = str(value).replace('B/.', '').replace(',', '').strip()
                number = float(clean_value) if clean_value else default
                
                if number < 0:
                    return 0.0
                if number > 999999999:
                    return 999999999.0
                
                return number
            except:
                return default
        
        # 🔧 USAR SOLO CAMPOS QUE EXISTEN EN EL SCHEMA REAL DE CREATIO
        case_data_extra = {
            # Campos de fecha que existen
            "NdosFechadeEmision": safe_date(payload.get('IssueDate', '')),
            "NdosFechadeRecibido": safe_date(payload.get('ReceivedDate', '')),
            "NdosFechadeResolucion": safe_date(payload.get('ResolutionDate', '')),
            "NdosVencimiento": safe_date(payload.get('DueDate', '')),
            
            # Campos de texto que existen
            "NdosNoficio": safe_string(payload.get('OficioNumber', ''), 50, 'N/A'),
            "NdosAutoridad": safe_string(payload.get('Authority', ''), 200, 'No especificado'),
            "NdosClasificaciondeOficio": safe_string(payload.get('DocumentClassification', ''), 100, 'No especificado'),
            "NdosObservaciones": safe_string(payload.get('Subject', ''), 500, 'Oficio procesado automáticamente'),
            "NdosPalabrasClaves": safe_string(payload.get('KeywordsFound', ''), 300, 'Ninguna'),
            "NdosNotas": safe_string(payload.get('Notes', ''), 500, 'Procesado por OCR automático'),
            "NdosInstruccion": safe_string(payload.get('Instructions', ''), 300, ''),
            
            # Campos opcionales de texto
            "NdosDelito": safe_string(payload.get('Crime', ''), 100, ''),
            "NdosNdeResolucion": safe_string(payload.get('ResolutionNumber', ''), 50, ''),
            "NdosCarpeta": safe_string(payload.get('Folder', ''), 50, ''),
            "NdosSucursaldeRecibido": safe_string(payload.get('BranchReceived', ''), 100, ''),
            
            # Campo numérico
            "NdosMonto": safe_number(payload.get('Amount', 0)),
            
            # Campos booleanos que existen
            "NdosSensitivo": bool(payload.get('RequiresUrgentAction', False)),
            "NdosDirigidoaGlobalBank": bool(payload.get('DirectedToGlobalBank', False)),
            "NdosSellodeAutoridad": bool(payload.get('HasAuthoritySeal', False))
        }
        
        logger.info(f"📋 Real schema data prepared: {len(case_data_extra)} fields")
        logger.info(f"  - All fields confirmed to exist in Creatio schema")
        
        return case_data_extra
        
    except Exception as e:
        logger.error(f"❌ Error preparing real schema case data: {str(e)}")
        # Devolver datos mínimos usando solo campos que existen
        return {
            "NdosFechadeEmision": "1900-01-01",
            "NdosFechadeRecibido": "1900-01-01", 
            "NdosVencimiento": "1900-01-01",
            "NdosNoficio": "Error de validación",
            "NdosAutoridad": "Error de validación", 
            "NdosClasificaciondeOficio": "Error de validación",
            "NdosObservaciones": "Error en procesamiento de datos",
            "NdosPalabrasClaves": "Ninguna",
            "NdosMonto": 0.0,
            "NdosSensitivo": False
        }

def create_schema_compatible_creatio_request(payload: Dict[str, Any], has_structured_data: bool) -> Dict[str, Any]:
    """
    Crea caso en Creatio usando solo campos compatibles con el schema existente
    """
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🚀 Creating schema-compatible Creatio case - Attempt {attempt + 1}/{max_retries}")
            
            creatio = CreatioService(CREATIO_URL, CREATIO_USERNAME, CREATIO_PASSWORD)
            creatio.authenticate()
        
            # Preparar subject y notes seguros
            oficio_number = payload.get('OficioNumber', 'Sin número')
            authority = payload.get('Authority', 'Sin autoridad')
            classification = payload.get('DocumentClassification', '')
            
            subject = f"Oficio: {oficio_number} - {authority}"
            if classification and classification != "No especificado":
                subject += f" ({classification})"
            
            notes_parts = [
                f"Oficio procesado automáticamente",
                f"Cliente: {payload.get('ClientTarget', 'No especificado')}",
                f"Clasificación: {classification}",
                f"Confianza: {payload.get('ClassificationConfidence', 'N/A')}"
            ]
            
            if payload.get('PersonsCount', 0) > 0:
                notes_parts.append(f"Personas involucradas: {payload.get('PersonsCount')}")
            
            if payload.get('TotalAmount', 0) > 0:
                notes_parts.append(f"Monto total: B/.{payload.get('TotalAmount'):,.2f}")
            
            notes = "\n".join(notes_parts)
            
            # 🔧 PREPARAR DATOS CON SCHEMA COMPATIBLE
            case_data_extra = prepare_known_case_data(payload)
            
            # 📊 LOG DETALLADO DE DATOS QUE SE ENVÍAN A CREATIO
            logger.info(f"🔧 Creating case with {len(case_data_extra)} validated fields")
            logger.info(f"   - Using ONLY fields confirmed in Creatio schema")
            
            # Mostrar datos específicos que se envían
            logger.info(f"📋 DATOS ESPECÍFICOS ENVIADOS A CREATIO:")
            logger.info(f"   📄 Subject: {subject}")
            logger.info(f"   📝 Notes: {notes}")
            logger.info(f"   🏷️  Clasificación: {payload.get('DocumentClassification', 'N/A')}")
            logger.info(f"   📅 Fecha Emisión: {case_data_extra.get('NdosFechadeEmision', 'N/A')}")
            logger.info(f"   📅 Fecha Recibido: {case_data_extra.get('NdosFechadeRecibido', 'N/A')}")
            logger.info(f"   📅 Fecha Vencimiento: {case_data_extra.get('NdosVencimiento', 'N/A')}")
            logger.info(f"   📄 Número Oficio: {case_data_extra.get('NdosNoficio', 'N/A')}")
            logger.info(f"   🏛️  Autoridad: {case_data_extra.get('NdosAutoridad', 'N/A')}")
            logger.info(f"   💰 Monto: {case_data_extra.get('NdosMonto', 0.0)}")
            logger.info(f"   🔑 Palabras Clave: {case_data_extra.get('NdosPalabrasClaves', 'N/A')}")
            logger.info(f"   ⚠️  Sensitivo: {case_data_extra.get('NdosSensitivo', False)}")
            logger.info(f"   🏦 Dirigido a Global Bank: {case_data_extra.get('NdosDirigidoaGlobalBank', False)}")
            # Crear registros de personas si existen
            personas = payload.get('InvolvedPersons', [])
            
            logger.info(f"   👥 Personas a crear: {len(personas)}")
            
            # Mostrar detalles de personas si existen
            if personas:
                logger.info(f"   👥 DETALLES DE PERSONAS:")
                for i, persona in enumerate(personas, 1):
                    logger.info(f"      Persona {i}: {persona.get('nombre_completo', 'Sin nombre')}")
                    logger.info(f"        - ID: {persona.get('identificacion', 'N/A')}")
                    logger.info(f"        - Monto: {persona.get('monto_numerico', 0.0)}")
                    logger.info(f"        - Expediente: {persona.get('expediente', 'N/A')}")
            else:
                logger.info(f"   👥 No hay personas para crear (persons_count = 0)")
            
            # Crear caso
            case_id = creatio.create_case(subject, notes, case_data_extra=case_data_extra)
            created_persons = []
            
            for persona in personas:
                try:
                    person_id = creatio.create_person_record(case_id, persona)
                    created_persons.append({
                        'person_id': person_id,
                        'name': persona.get('nombre_completo', 'Sin nombre')
                    })
                except Exception as e:
                    logger.error(f"Error creando persona: {str(e)}")
                    created_persons.append({
                        'error': str(e),
                        'name': persona.get('nombre_completo', 'Sin nombre')
                    })
            
            logger.info(f"🎉 Schema-compatible integration SUCCESS: Case {case_id}")
            
            # 📊 LOG FINAL DE RESULTADO
            logger.info(f"✅ CASO CREADO EXITOSAMENTE EN CREATIO:")
            logger.info(f"   🆔 Case ID: {case_id}")
            logger.info(f"   📄 Subject: {subject}")
            logger.info(f"   🏷️  Clasificación: {payload.get('DocumentClassification', 'N/A')}")
            logger.info(f"   👥 Personas creadas: {len([p for p in created_persons if 'person_id' in p])}")
            logger.info(f"   ❌ Errores en personas: {len([p for p in created_persons if 'error' in p])}")
            
            if created_persons:
                logger.info(f"   👥 DETALLES DE PERSONAS CREADAS:")
                for i, persona in enumerate(created_persons, 1):
                    if 'person_id' in persona:
                        logger.info(f"      Persona {i}: {persona['name']} (ID: {persona['person_id']})")
                    else:
                        logger.info(f"      Persona {i}: {persona['name']} (ERROR: {persona.get('error', 'Desconocido')})")
            
            return {
                'success': True,
                'crm_id': case_id,
                'case_id': case_id,
                'persons_created': len([p for p in created_persons if 'person_id' in p]),
                'persons_errors': len([p for p in created_persons if 'error' in p]),
                'persons_details': created_persons,
                'schema_compatible': True,
                'attempt': attempt + 1
            }
            
        except Exception as e:
            error_msg = f"Error en integración compatible (Attempt {attempt + 1}): {str(e)}"
            logger.warning(f"⚠️ {error_msg}")
            
            logger.error(f"🔍 Error details:")
            logger.error(f"  - Error type: {type(e).__name__}")
            logger.error(f"  - Error message: {str(e)}")
            
            if hasattr(e, 'read'):
                try:
                    error_response = e.read().decode('utf-8')
                    logger.error(f"  - HTTP Response: {error_response}")
                except:
                    pass
            
            if attempt < max_retries - 1:
                logger.info(f"🔄 Retrying in {retry_delay} seconds...")
                import time
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error(f"❌ All attempts failed: {error_msg}")
                return {'success': False, 'error': error_msg, 'attempts': max_retries}

def parse_date_for_creatio(date_str: str, nullable: bool = True) -> str:
    """Convierte fecha a formato ISO para Creatio"""
    if not date_str or date_str in ['No especificado', 'No especificada', '', 'null', None]:
        return "1900-01-01" if not nullable else None
    
    try:
        import re
        from datetime import datetime
        
        date_clean = date_str.strip()
        
        # Intentar parsear fechas en español
        if " de " in date_clean.lower():
            try:
                meses = {
                    'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
                    'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
                    'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'
                }
                
                parts = date_clean.lower().split()
                if len(parts) >= 4 and parts[1] == 'de' and parts[3] == 'de':
                    dia = parts[0].zfill(2)
                    mes = meses.get(parts[2], None)
                    año = parts[4]
                    
                    if mes and año.isdigit():
                        return f"{año}-{mes}-{dia}"
            except:
                pass
        
        # Formatos numéricos
        date_clean = re.sub(r'[^\d\/\-\.]', '', date_str)
        
        if not date_clean:
            return "1900-01-01" if not nullable else None
        
        formats = ['%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%y']
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_clean, fmt)
                return dt.strftime('%Y-%m-%d')
            except:
                continue
        
        return "1900-01-01" if not nullable else None
        
    except Exception as e:
        logger.warning(f"Error parseando fecha {date_str}: {str(e)}")
        return "1900-01-01" if not nullable else None

def update_tracking_status(batch_id: str, job_id: str, status: str, details: str = ''):
    """Actualiza el estado en DynamoDB"""
    try:
        table = dynamodb.Table(JOB_TRACKING_TABLE)
        
        update_expression = "SET #status = :status, updated_at = :updated_at"
        expression_values = {
            ':status': status,
            ':updated_at': datetime.utcnow().isoformat()
        }
        expression_names = {'#status': 'status'}
        
        if details:
            update_expression += ", details = :details"
            expression_values[':details'] = details
        
        if status == 'completed':
            update_expression += ", completed_at = :completed_at"
            expression_values[':completed_at'] = datetime.utcnow().isoformat()
        elif status in ['crm_error', 'error']:
            update_expression += ", error_at = :error_at"
            expression_values[':error_at'] = datetime.utcnow().isoformat()
        
        table.update_item(
            Key={'job_id': job_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"✅ Schema-compatible status updated: {job_id} -> {status}")
        
        # Actualizar progreso del batch
        try:
            update_batch_completion_counter(batch_id, status == 'completed')
        except Exception as batch_error:
            logger.warning(f"Error updating batch counter: {str(batch_error)}")
        
    except Exception as e:
        logger.error(f"Error updating schema-compatible status: {str(e)}")

def update_batch_completion_counter(batch_id: str, success: bool):
    """Actualiza contadores de completitud del batch"""
    try:
        batch_table = dynamodb.Table(BATCH_TRACKING_TABLE)
        
        if success:
            update_expression = "ADD completed_count :inc SET last_updated = :updated"
        else:
            update_expression = "ADD error_count :inc SET last_updated = :updated"
        
        batch_table.update_item(
            Key={'batch_id': batch_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues={
                ':inc': 1,
                ':updated': datetime.utcnow().isoformat()
            }
        )
        
        logger.info(f"✅ Schema-compatible batch counter updated: {batch_id}")
        
    except Exception as e:
        logger.warning(f"Error updating schema-compatible batch counter: {str(e)}")

# Servicio de Creatio (mantener implementación original)
class CreatioService:
    """Servicio de Creatio compatible con schema existente"""
    def __init__(self, url, username, password):
        self.url = url
        self.username = username
        self.password = password
        self.bpmcsrf = None
        self.cookie_jar = None
    
    def authenticate(self):
        """Autentica con Creatio"""
        import urllib.request
        import http.cookiejar
        
        auth_url = f"{self.url}/ServiceModel/AuthService.svc/Login"
        self.cookie_jar = http.cookiejar.CookieJar()
        cookie_handler = urllib.request.HTTPCookieProcessor(self.cookie_jar)
        opener = urllib.request.build_opener(cookie_handler)

        data = json.dumps({
            "UserName": self.username, 
            "UserPassword": self.password
        }).encode("utf-8")
        
        request = urllib.request.Request(auth_url, data=data, headers={"Content-Type": "application/json"})
        response = opener.open(request)

        if response.status == 200:
            self.bpmcsrf = next((cookie.value for cookie in self.cookie_jar if cookie.name == "BPMCSRF"), None)
            if self.bpmcsrf:
                logger.info(f"✅ Schema-compatible Creatio authentication successful")
                return True
            else:
                raise Exception("No se encontró la cookie BPMCSRF")
        else:
            raise Exception("Error de autenticación: " + response.read().decode("utf-8"))
    
    def _get_headers(self):
        """Prepara headers para peticiones"""
        cookie_header = "; ".join([f"{cookie.name}={cookie.value}" for cookie in self.cookie_jar])
        return {
            "Content-Type": "application/json",
            "BPMCSRF": self.bpmcsrf,
            "Cookie": cookie_header
        }
    
    def create_case(self, subject, notes, priority_id="d9bd322c-f46b-1410-ee8c-0050ba5d6c38", case_data_extra=None):
        """Crea caso en Creatio usando schema compatible"""
        import urllib.request
        
        url = f"{self.url}/0/odata/case"
        
        case_data = {
            "CreatedOn": datetime.utcnow().isoformat() + "Z",
            "CreatedById": "410006e1-ca4e-4502-a9ec-e54d922d2c00",
            "ModifiedOn": datetime.utcnow().isoformat() + "Z",
            "ModifiedById": "410006e1-ca4e-4502-a9ec-e54d922d2c00",
            "ProcessListeners": 2,
            "RegisteredOn": datetime.utcnow().isoformat() + "Z",
            "Subject": "Caso, tipo Oficio",
            "Symptoms": "Caso, tipo Oficio",
            "StatusId": "ae5f2f10-f46b-1410-fd9a-0050ba5d6c38",
            "Notes": notes,
            "PriorityId": priority_id,
            "OriginId": "5e5e202a-f46b-1410-3692-0050ba5d6c38",
            "AccountId": "e308b781-3c5b-4ecb-89ef-5c1ed4da488e",
            "ResponseOverdue": False,
            "SolutionOverdue": False,
            "SatisfactionLevelComment": "",
            "SolutionRemains": 0.0,
            "SupportLevelId": "ff7f2f92-f36b-1410-3d9c-0050ba5d6c38",
            "FirstSolutionProvidedOn": "0001-01-01T00:00:00Z"
        }
        
        if case_data_extra:
            case_data.update(case_data_extra)
        
        try:
            data = json.dumps(case_data).encode("utf-8")
            request = urllib.request.Request(url, data=data, headers=self._get_headers())
            request.get_method = lambda: 'POST'
            
            response = urllib.request.urlopen(request)
            
            if response.status == 201:
                created_case = json.loads(response.read().decode("utf-8"))
                case_id = created_case.get("Id")
                logger.info(f"🎉 Schema-compatible case created: {case_id}")
                return case_id
            else:
                raise Exception(f"Error creating schema-compatible case: {response.status}")
                
        except Exception as e:
            logger.error(f"Error creating schema-compatible case: {str(e)}")
            raise
    
    def create_person_record(self, case_id, person_data):
        """Crea registro de persona usando schema real de NdosPersonasOCR"""
        import urllib.request
        
        url = f"{self.url}/0/odata/NdosPersonasOCR"
        
        # Extraer datos de la persona
        nombre_completo = person_data.get('nombre_completo', '')
        nombres = nombre_completo.split() if nombre_completo else []
        
        # Mapear a los campos reales del schema de NdosPersonasOCR (basado en el objeto real)
        persona_record = {
            "CreatedOn": datetime.utcnow().isoformat() + "Z",
            "CreatedById": "410006e1-ca4e-4502-a9ec-e54d922d2c00",
            "ModifiedOn": datetime.utcnow().isoformat() + "Z",
            "ModifiedById": "410006e1-ca4e-4502-a9ec-e54d922d2c00",
            "ProcessListeners": 0,
            
            # Campos que existen en el schema real de NdosPersonasOCR
            "NdosObservaciones": person_data.get('observaciones', 'Persona extraída por OCR - Secuencia: 0'),
            "NdosImporte": person_data.get('monto_numerico', 0.0),
            "NdosIdentificacionNumero": person_data.get('identificacion', ''),
            "NdosExpediente": person_data.get('expediente', ''),
            "NdosOficioId": case_id,
            
            # Campos de nombre que existen en el schema real
            "NdosNombreCompleto": nombre_completo,
            "NdosNombre": person_data.get('nombre', nombres[0] if nombres else ''),
            "NdosNombreSegundo": person_data.get('nombre_segundo', ' '.join(nombres[1:-2]) if len(nombres) > 3 else ''),
            "NdosApellidoPaterno": person_data.get('apellido_paterno', nombres[-2] if len(nombres) >= 2 else ''),
            "NdosApellidoMaterno": person_data.get('apellido_materno', nombres[-1] if len(nombres) >= 3 else '')
        }
        
        try:
            data = json.dumps(persona_record).encode("utf-8")
            request = urllib.request.Request(url, data=data, headers=self._get_headers())
            request.get_method = lambda: 'POST'
            
            response = urllib.request.urlopen(request)
            
            if response.status == 201:
                created_person = json.loads(response.read().decode("utf-8"))
                person_id = created_person.get("Id")
                logger.info(f"✅ Schema-compatible person record created: {person_id}")
                return person_id
            else:
                raise Exception(f"Error creating schema-compatible person: {response.status}")
                
        except Exception as e:
            logger.error(f"Error creating schema-compatible person: {str(e)}")
            raise