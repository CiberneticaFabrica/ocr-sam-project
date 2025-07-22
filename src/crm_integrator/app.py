# src/crm_integrator/app.py
import json
import boto3
import logging
import os
import requests
from datetime import datetime
from typing import Dict, Any, Optional

# Configuración de logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Clientes AWS
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Variables de entorno
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']
TRACKING_TABLE = os.environ['TRACKING_TABLE']
CREATIO_API_ENDPOINT = os.environ['CREATIO_API_ENDPOINT']
CREATIO_API_KEY = os.environ['CREATIO_API_KEY']

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Procesa resultados OCR y los inserta en Creatio CRM
    """
    try:
        logger.info(f"🏢 CRM Integrator event received: {json.dumps(event, default=str)}")
        
        # Procesar mensajes de SQS
        results = []
        for record in event.get('Records', []):
            try:
                result = process_sqs_message(record)
                results.append(result)
            except Exception as e:
                logger.error(f"❌ Error procesando mensaje SQS: {str(e)}")
                results.append({'success': False, 'error': str(e)})
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'processed_messages': len(results),
                'results': results
            })
        }
        
    except Exception as e:
        logger.error(f"❌ Error en CRM integrator: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def process_sqs_message(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procesa un mensaje individual de SQS con resultado OCR
    """
    try:
        # Parsear mensaje
        message_body = json.loads(record['body'])
        job_id = message_body.get('job_id')
        batch_id = message_body.get('batch_id')
        
        logger.info(f"🔄 Procesando inserción CRM para job {job_id}")
        
        # Obtener resultado OCR desde S3
        ocr_result = get_ocr_result_from_s3(job_id)
        
        if not ocr_result or not ocr_result.get('success'):
            logger.error(f"❌ No se encontró resultado OCR válido para job {job_id}")
            update_tracking_status(batch_id, job_id, 'crm_error', 'No OCR result found')
            return {'success': False, 'job_id': job_id, 'error': 'No OCR result found'}
        
        # Extraer datos del resultado OCR
        extracted_data = ocr_result.get('data', {})
        
        # Mapear datos para Creatio
        crm_payload = map_ocr_data_to_creatio(extracted_data, job_id, batch_id)
        
        # Crear solicitud en Creatio
        creatio_response = create_creatio_request(crm_payload)
        
        if creatio_response.get('success'):
            logger.info(f"✅ Solicitud creada en Creatio para job {job_id}")
            update_tracking_status(batch_id, job_id, 'completed', 
                                 f"CRM ID: {creatio_response.get('crm_id')}")
            return {
                'success': True,
                'job_id': job_id,
                'crm_id': creatio_response.get('crm_id')
            }
        else:
            logger.error(f"❌ Error creando solicitud en Creatio: {creatio_response.get('error')}")
            update_tracking_status(batch_id, job_id, 'crm_error', 
                                 creatio_response.get('error', 'Unknown error'))
            return {
                'success': False,
                'job_id': job_id,
                'error': creatio_response.get('error')
            }
        
    except Exception as e:
        logger.error(f"❌ Error procesando mensaje: {str(e)}")
        return {'success': False, 'error': str(e)}

def get_ocr_result_from_s3(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Obtiene el resultado OCR desde S3
    """
    try:
        # Intentar obtener resultado desde nueva estructura
        try:
            response = s3_client.get_object(
                Bucket=S3_BUCKET_NAME,
                Key=f'jobs/{job_id}/result.json'
            )
            result = json.loads(response['Body'].read())
            logger.info(f"✅ Resultado OCR obtenido desde jobs/{job_id}/result.json")
            return result
        except s3_client.exceptions.NoSuchKey:
            pass
        
        # Intentar obtener desde estructura de oficios
        try:
            response = s3_client.get_object(
                Bucket=S3_BUCKET_NAME,
                Key=f'oficios/results/{job_id}_result.json'
            )
            result = json.loads(response['Body'].read())
            logger.info(f"✅ Resultado OCR obtenido desde oficios/results/{job_id}_result.json")
            return result
        except s3_client.exceptions.NoSuchKey:
            pass
        
        logger.warning(f"⚠️ No se encontró resultado OCR para job {job_id}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo resultado OCR: {str(e)}")
        return None

def map_ocr_data_to_creatio(ocr_data: Dict[str, Any], job_id: str, batch_id: str) -> Dict[str, Any]:
    """
    Mapea datos extraídos por OCR al formato de Creatio CRM
    """
    try:
        # Extraer información principal
        info_extraida = ocr_data.get('informacion_extraida', {})
        personas = ocr_data.get('lista_personas', {}).get('listado', [])
        
        # Datos principales del oficio
        crm_payload = {
            # Identificación del documento
            "DocumentId": job_id,
            "BatchId": batch_id,
            "DocumentType": "Oficio Legal",
            
            # Información básica del oficio
            "OficioNumber": info_extraida.get('numero_oficio', ''),
            "Authority": info_extraida.get('autoridad', ''),
            "IssueDate": parse_date_for_creatio(info_extraida.get('fecha_emision', '')),
            "ReceivedDate": parse_date_for_creatio(info_extraida.get('fecha_recibido', '')),
            
            # Cliente y expediente
            "ClientTarget": info_extraida.get('oficiado_cliente', ''),
            "ClientIdentification": info_extraida.get('numero_identificacion', ''),
            "ExpedientNumber": info_extraida.get('expediente', ''),
            
            # Información legal
            "AutoNumber": info_extraida.get('numero_auto', ''),
            "AutoDate": parse_date_for_creatio(info_extraida.get('fecha_auto', '')),
            "Amount": parse_amount_for_creatio(info_extraida.get('monto', '')),
            "ResolutionNumber": info_extraida.get('numero_resolucion', ''),
            "ResolutionDate": parse_date_for_creatio(info_extraida.get('fecha_resolucion', '')),
            "Crime": info_extraida.get('delito', ''),
            
            # Ubicación y control
            "BranchReceived": info_extraida.get('sucursal_recibido', ''),
            "Folder": info_extraida.get('carpeta', ''),
            "DueDate": parse_date_for_creatio(info_extraida.get('vencimiento', '')),
            "ReceivedStamp": info_extraida.get('sello_recibido', ''),
            "AuthorityStamp": info_extraida.get('sello_autoridad', ''),
            
            # Nuevos campos
            "ProductType": info_extraida.get('tipo_producto', ''),
            "Complainant": info_extraida.get('denuciante', ''),
            "DirectedToGlobalBank": info_extraida.get('dirigido_global_bank', ''),
            
            # Clasificación automática
            "DocumentClassification": ocr_data.get('tipo_oficio_detectado', ''),
            "ConfidenceLevel": ocr_data.get('nivel_confianza', ''),
            "KeywordsFound": ', '.join(ocr_data.get('palabras_clave_encontradas', [])),
            
            # Metadatos
            "ProcessedAt": datetime.utcnow().isoformat(),
            "ProcessingSource": "Automated OCR",
            "FullText": ocr_data.get('texto_completo', '')[:4000],  # Limitar texto
            "Observations": ocr_data.get('observaciones', ''),
            
            # Estado y prioridad
            "Status": "Pending Review",
            "Priority": determine_priority(info_extraida, ocr_data),
            "RequiresUrgentAction": requires_urgent_action(info_extraida, ocr_data),
            
            # Estadísticas
            "PersonsCount": len(personas),
            "TotalAmount": ocr_data.get('lista_personas', {}).get('monto_total', 0),
            "ExtractionQuality": ocr_data.get('analisis_extraccion', {}).get('resumen', {}).get('calidad_extraccion', 'UNKNOWN')
        }
        
        # Agregar personas involucradas
        if personas:
            crm_payload["InvolvedPersons"] = format_persons_for_creatio(personas)
        
        # Agregar autos si existen
        autos = ocr_data.get('lista_autos', [])
        if autos:
            crm_payload["RelatedAutos"] = format_autos_for_creatio(autos)
        
        logger.info(f"📝 Datos mapeados para Creatio: {len(crm_payload)} campos")
        return crm_payload
        
    except Exception as e:
        logger.error(f"❌ Error mapeando datos: {str(e)}")
        raise

def parse_date_for_creatio(date_str: str) -> Optional[str]:
    """
    Convierte fecha a formato ISO para Creatio
    """
    if not date_str or date_str in ['No especificado', '', 'null']:
        return None
    
    try:
        # Patrones de fecha comunes en Panamá
        import re
        from datetime import datetime
        
        # Limpiar fecha
        date_clean = re.sub(r'[^\d\/\-\.]', '', date_str)
        
        # Intentar diferentes formatos
        formats = [
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%d.%m.%Y',
            '%Y-%m-%d',
            '%d/%m/%y',
            '%d-%m-%y'
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_clean, fmt)
                return dt.strftime('%Y-%m-%d')
            except:
                continue
        
        logger.warning(f"⚠️ No se pudo parsear fecha: {date_str}")
        return None
        
    except Exception as e:
        logger.warning(f"⚠️ Error parseando fecha {date_str}: {str(e)}")
        return None

def parse_amount_for_creatio(amount_str: str) -> float:
    """
    Convierte monto a float para Creatio
    """
    if not amount_str or amount_str in ['No especificado', '', 'null']:
        return 0.0
    
    try:
        # Limpiar monto
        clean_amount = amount_str.replace('B/.', '').replace('$', '').replace(',', '').strip()
        return float(clean_amount) if clean_amount else 0.0
    except:
        return 0.0

def determine_priority(info_extraida: Dict[str, Any], ocr_data: Dict[str, Any]) -> str:
    """
    Determina prioridad basada en contenido del oficio
    """
    keywords = ocr_data.get('palabras_clave_encontradas', [])
    
    # Palabras que indican alta prioridad
    high_priority_keywords = [
        'embargo', 'secuestro', 'allanamiento', 'aprehensión',
        'citación', 'urgente', 'inmediato'
    ]
    
    # Verificar vencimiento próximo
    vencimiento = info_extraida.get('vencimiento', '')
    if vencimiento and vencimiento != 'No especificado':
        try:
            # Si hay fecha de vencimiento, es prioritario
            return "High"
        except:
            pass
    
    # Verificar palabras clave de alta prioridad
    if any(keyword.lower() in [k.lower() for k in keywords] for keyword in high_priority_keywords):
        return "High"
    
    # Verificar montos altos
    monto_str = info_extraida.get('monto', '0')
    try:
        monto = parse_amount_for_creatio(monto_str)
        if monto > 50000:  # Más de 50,000
            return "High"
        elif monto > 10000:  # Más de 10,000
            return "Medium"
    except:
        pass
    
    return "Medium"

def requires_urgent_action(info_extraida: Dict[str, Any], ocr_data: Dict[str, Any]) -> bool:
    """
    Determina si requiere acción urgente
    """
    keywords = ocr_data.get('palabras_clave_encontradas', [])
    
    urgent_keywords = [
        'embargo', 'secuestro', 'allanamiento', 'citación',
        'inmediato', 'urgente', 'aprehensión'
    ]
    
    return any(keyword.lower() in [k.lower() for k in keywords] for keyword in urgent_keywords)

def format_persons_for_creatio(personas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Formatea lista de personas para Creatio
    """
    formatted_persons = []
    
    for persona in personas:
        formatted_person = {
            "FullName": persona.get('nombre_completo', ''),
            "Identification": persona.get('identificacion', ''),
            "IdentificationType": persona.get('tipo_identificacion', ''),
            "Amount": persona.get('monto_numerico', 0),
            "AmountText": persona.get('monto_texto', ''),
            "ExpedientNumber": persona.get('expediente', ''),
            "Sequence": persona.get('secuencia', 0)
        }
        formatted_persons.append(formatted_person)
    
    return formatted_persons

def format_autos_for_creatio(autos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Formatea lista de autos para Creatio
    """
    formatted_autos = []
    
    for auto in autos:
        formatted_auto = {
            "AutoDate": parse_date_for_creatio(auto.get('fecha_auto', '')),
            "AutoNumber": auto.get('numero_auto_placa', ''),
            "Amount": parse_amount_for_creatio(auto.get('monto_auto', ''))
        }
        formatted_autos.append(formatted_auto)
    
    return formatted_autos

def create_creatio_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea solicitud en Creatio CRM
    """
    try:
        logger.info("🚀 Enviando solicitud a Creatio...")
        
        # Headers para API de Creatio
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {CREATIO_API_KEY}',
            'Accept': 'application/json'
        }
        
        # Endpoint para crear solicitud (ajustar según API de Creatio)
        url = f"{CREATIO_API_ENDPOINT}/0/dataservice/json/SyncReply/SelectQuery"
        
        # Payload para Creatio (ajustar según schema)
        creatio_payload = {
            "RootSchemaName": "LegalDocumentRequest",  # Ajustar nombre del schema
            "OperationType": 0,  # Insert
            "ColumnValues": payload
        }
        
        response = requests.post(
            url,
            headers=headers,
            json=creatio_payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Extraer ID de la solicitud creada
            crm_id = result.get('id') or result.get('Id') or 'unknown'
            
            logger.info(f"✅ Solicitud creada en Creatio con ID: {crm_id}")
            
            return {
                'success': True,
                'crm_id': crm_id,
                'response': result
            }
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            logger.error(f"❌ Error en API de Creatio: {error_msg}")
            
            return {
                'success': False,
                'error': error_msg,
                'status_code': response.status_code
            }
        
    except requests.exceptions.Timeout:
        error_msg = "Timeout conectando con Creatio API"
        logger.error(f"⏰ {error_msg}")
        return {'success': False, 'error': error_msg}
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Error de conexión con Creatio: {str(e)}"
        logger.error(f"🔌 {error_msg}")
        return {'success': False, 'error': error_msg}
        
    except Exception as e:
        error_msg = f"Error inesperado en Creatio API: {str(e)}"
        logger.error(f"💥 {error_msg}")
        return {'success': False, 'error': error_msg}

def update_tracking_status(batch_id: str, job_id: str, status: str, details: str = ''):
    """
    Actualiza el estado en DynamoDB
    """
    try:
        table = dynamodb.Table(TRACKING_TABLE)
        
        update_expression = """
            SET #status = :status,
                crm_status = :crm_status,
                updated_at = :updated_at
        """
        
        expression_values = {
            ':status': status,
            ':crm_status': status,
            ':updated_at': datetime.utcnow().isoformat()
        }
        
        expression_names = {
            '#status': 'status'
        }
        
        if details:
            update_expression += ", crm_details = :details"
            expression_values[':details'] = details
        
        if status == 'completed':
            update_expression += ", completed_at = :completed_at"
            expression_values[':completed_at'] = datetime.utcnow().isoformat()
        
        table.update_item(
            Key={
                'batch_id': batch_id,
                'oficio_id': job_id
            },
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_names,
            ExpressionAttributeValues=expression_values
        )
        
        logger.info(f"✅ Estado actualizado en DynamoDB: {job_id} -> {status}")
        
        # Actualizar contador del batch si es completion
        if status == 'completed':
            update_batch_completion_counter(batch_id, True)
        elif status in ['crm_error', 'error']:
            update_batch_completion_counter(batch_id, False)
        
    except Exception as e:
        logger.error(f"❌ Error actualizando estado en DynamoDB: {str(e)}")

def update_batch_completion_counter(batch_id: str, success: bool):
    """
    Actualiza contadores de completitud del batch
    """
    try:
        table = dynamodb.Table(TRACKING_TABLE)
        
        if success:
            update_expression = """
                ADD completed_oficios :inc
                SET updated_at = :updated_at
            """
        else:
            update_expression = """
                ADD failed_oficios :inc
                SET updated_at = :updated_at
            """
        
        table.update_item(
            Key={
                'batch_id': batch_id,
                'oficio_id': 'BATCH_SUMMARY'
            },
            UpdateExpression=update_expression,
            ExpressionAttributeValues={
                ':inc': 1,
                ':updated_at': datetime.utcnow().isoformat()
            }
        )
        
        # Verificar si el batch está completo
        check_batch_completion(batch_id)
        
    except Exception as e:
        logger.error(f"❌ Error actualizando contador del batch: {str(e)}")

def check_batch_completion(batch_id: str):
    """
    Verifica si el batch está completo y actualiza estado
    """
    try:
        table = dynamodb.Table(TRACKING_TABLE)
        
        # Obtener resumen del batch
        response = table.get_item(
            Key={
                'batch_id': batch_id,
                'oficio_id': 'BATCH_SUMMARY'
            }
        )
        
        if 'Item' not in response:
            return
        
        batch_item = response['Item']
        total_oficios = batch_item.get('total_oficios', 0)
        completed_oficios = batch_item.get('completed_oficios', 0)
        failed_oficios = batch_item.get('failed_oficios', 0)
        
        processed_total = completed_oficios + failed_oficios
        
        # Si todos los oficios están procesados
        if processed_total >= total_oficios:
            completion_rate = (completed_oficios / total_oficios) * 100 if total_oficios > 0 else 0
            
            batch_status = 'completed' if completion_rate >= 80 else 'completed_with_errors'
            
            table.update_item(
                Key={
                    'batch_id': batch_id,
                    'oficio_id': 'BATCH_SUMMARY'
                },
                UpdateExpression="""
                    SET #status = :status,
                        completed_at = :completed_at,
                        completion_rate = :completion_rate,
                        updated_at = :updated_at
                """,
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': batch_status,
                    ':completed_at': datetime.utcnow().isoformat(),
                    ':completion_rate': completion_rate,
                    ':updated_at': datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"🏁 Batch {batch_id} completado: {completion_rate:.1f}% éxito")
        
    except Exception as e:
        logger.error(f"❌ Error verificando completitud del batch: {str(e)}")

# Función auxiliar para testing de API de Creatio
def test_creatio_connection() -> bool:
    """
    Prueba la conexión con Creatio API
    """
    try:
        headers = {
            'Authorization': f'Bearer {CREATIO_API_KEY}',
            'Accept': 'application/json'
        }
        
        # Endpoint de prueba (ajustar según API de Creatio)
        test_url = f"{CREATIO_API_ENDPOINT}/0/ServiceModel/AuthService.svc/GetCurrentUserInfo"
        
        response = requests.get(test_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            logger.info("✅ Conexión con Creatio API exitosa")
            return True
        else:
            logger.error(f"❌ Error de conexión con Creatio: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error probando conexión con Creatio: {str(e)}")
        return False