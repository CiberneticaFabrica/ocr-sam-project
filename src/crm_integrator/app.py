# src/crm_integrator/app.py
import json
import boto3
import logging
import os
import requests
import urllib.request
import urllib.parse
import http.cookiejar
from datetime import datetime
from typing import Dict, Any, Optional, List

# Configuración de logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Clientes AWS
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Variables de entorno
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']
TRACKING_TABLE = os.environ['TRACKING_TABLE']
CREATIO_URL = os.environ.get('CREATIO_URL', 'https://11006608-demo.creatio.com')
CREATIO_USERNAME = os.environ.get('CREATIO_USERNAME', 'Supervisor')
CREATIO_PASSWORD = os.environ.get('CREATIO_PASSWORD', '!k*ZPCT&MkuF2cDiM!S')

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
        # Separar nombre completo en partes
        nombre_completo = persona.get('nombre_completo', '')
        nombres = nombre_completo.split()
        
        nombre = nombres[0] if nombres else ''
        apellido_paterno = nombres[1] if len(nombres) > 1 else ''
        apellido_materno = nombres[2] if len(nombres) > 2 else ''
        nombre_segundo = nombres[3] if len(nombres) > 3 else ''
        
        formatted_person = {
            "nombre": nombre,
            "apellido_paterno": apellido_paterno,
            "apellido_materno": apellido_materno,
            "nombre_segundo": nombre_segundo,
            "identificacion": persona.get('identificacion', ''),
            "monto_numerico": persona.get('monto_numerico', 0.0),
            "expediente": persona.get('expediente', ''),
            "observaciones": f"Persona extraída por OCR - Secuencia: {persona.get('secuencia', 0)}"
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

class CreatioService:
    def __init__(self, url, username, password):
        self.url = url
        self.username = username
        self.password = password
        self.bpmcsrf = None
        self.cookie_jar = None
    
    def authenticate(self):
        """Autentica con Creatio y obtiene las cookies de sesión"""
        logger.info("🔐 Autenticando con Creatio...")
        auth_url = f"{self.url}/ServiceModel/AuthService.svc/Login"

        self.cookie_jar = http.cookiejar.CookieJar()
        cookie_handler = urllib.request.HTTPCookieProcessor(self.cookie_jar)
        opener = urllib.request.build_opener(cookie_handler)

        data = json.dumps({
            "UserName": self.username, 
            "UserPassword": self.password
        }).encode("utf-8")
        
        request = urllib.request.Request(
            auth_url, 
            data=data, 
            headers={"Content-Type": "application/json"}
        )
        response = opener.open(request)

        if response.status == 200:
            self.bpmcsrf = next(
                (cookie.value for cookie in self.cookie_jar if cookie.name == "BPMCSRF"), 
                None
            )
            if self.bpmcsrf:
                logger.info(f"✅ Autenticación exitosa. BPMCSRF: {self.bpmcsrf[:20]}...")
                return True
            else:
                raise Exception("No se encontró la cookie BPMCSRF")
        else:
            raise Exception("Error de autenticación: " + response.read().decode("utf-8"))
    
    def _get_headers(self):
        """Prepara los headers estándar para las peticiones"""
        cookie_header = "; ".join([
            f"{cookie.name}={cookie.value}" for cookie in self.cookie_jar
        ])
        return {
            "Content-Type": "application/json",
            "BPMCSRF": self.bpmcsrf,
            "Cookie": cookie_header
        }
    
    def create_case(self, subject, notes, priority_id="d9bd322c-f46b-1410-ee8c-0050ba5d6c38"):
        """Crea un caso en Creatio"""
        logger.info("📋 Creando caso en Creatio...")
        
        url = f"{self.url}/0/odata/case"
        
        # Datos del caso
        case_data = {
            "CreatedOn": datetime.utcnow().isoformat() + "Z",
            "CreatedById": "410006e1-ca4e-4502-a9ec-e54d922d2c00",
            "ModifiedOn": datetime.utcnow().isoformat() + "Z",
            "ModifiedById": "410006e1-ca4e-4502-a9ec-e54d922d2c00",
            "ProcessListeners": 2,
            "RegisteredOn": datetime.utcnow().isoformat() + "Z",
            "Subject": subject,
            "Symptoms": subject,
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
        
        try:
            data = json.dumps(case_data).encode("utf-8")
            request = urllib.request.Request(url, data=data, headers=self._get_headers())
            request.get_method = lambda: 'POST'
            
            response = urllib.request.urlopen(request)
            response_data = response.read().decode("utf-8")
            
            if response.status == 201:
                logger.info("✅ Caso creado exitosamente")
                created_case = json.loads(response_data)
                case_id = created_case.get("Id")
                logger.info(f"ID del caso creado: {case_id}")
                return case_id
            else:
                raise Exception(f"Error al crear caso: {response.status} - {response_data}")
                
        except urllib.error.HTTPError as e:
            error_response = e.read().decode("utf-8")
            logger.error(f"❌ Error HTTP al crear caso: {e.code}")
            logger.error(f"Respuesta de error: {error_response}")
            raise Exception(f"Error HTTP {e.code} al crear caso: {error_response}")
    
    def create_person_record(self, case_id, person_data):
        """Crea un registro de persona en NdosPersonasOCR"""
        logger.info(f"👤 Creando registro de persona para caso {case_id}...")
        
        url = f"{self.url}/0/odata/NdosPersonasOCR"
        
        # Mapear datos de la persona
        persona_record = {
            "CreatedOn": datetime.utcnow().isoformat() + "Z",
            "CreatedById": "410006e1-ca4e-4502-a9ec-e54d922d2c00",
            "ModifiedOn": datetime.utcnow().isoformat() + "Z",
            "ModifiedById": "410006e1-ca4e-4502-a9ec-e54d922d2c00",
            "ProcessListeners": 0,
            "NdosObservaciones": person_data.get('observaciones', ''),
            "NdosImporte": person_data.get('monto_numerico', 0.0),
            "NdosIdentificacionNumero": person_data.get('identificacion', ''),
            "NdosApellidoMaterno": person_data.get('apellido_materno', ''),
            "NdosApellidoPaterno": person_data.get('apellido_paterno', ''),
            "NdosNombreSegundo": person_data.get('nombre_segundo', ''),
            "NdosNombre": person_data.get('nombre', ''),
            "NdosExpediente": person_data.get('expediente', ''),
            "NdosOficioId": case_id
        }
        
        try:
            data = json.dumps(persona_record).encode("utf-8")
            request = urllib.request.Request(url, data=data, headers=self._get_headers())
            request.get_method = lambda: 'POST'
            
            response = urllib.request.urlopen(request)
            response_data = response.read().decode("utf-8")
            
            if response.status == 201:
                logger.info("✅ Registro de persona creado exitosamente")
                created_person = json.loads(response_data)
                person_id = created_person.get("Id")
                logger.info(f"ID de la persona creada: {person_id}")
                return person_id
            else:
                raise Exception(f"Error al crear persona: {response.status} - {response_data}")
                
        except urllib.error.HTTPError as e:
            error_response = e.read().decode("utf-8")
            logger.error(f"❌ Error HTTP al crear persona: {e.code}")
            logger.error(f"Respuesta de error: {error_response}")
            raise Exception(f"Error HTTP {e.code} al crear persona: {error_response}")

def create_creatio_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea caso en Creatio y registra personas encontradas
    """
    try:
        logger.info("🚀 Iniciando integración con Creatio...")
        
        # Inicializar servicio de Creatio
        creatio = CreatioService(CREATIO_URL, CREATIO_USERNAME, CREATIO_PASSWORD)
        
        # Autenticar
        creatio.authenticate()
        
        # Crear caso
        subject = f"Oficio: {payload.get('OficioNumber', 'Sin número')} - {payload.get('Authority', 'Sin autoridad')}"
        notes = f"Oficio procesado automáticamente por OCR\nCliente: {payload.get('ClientTarget', 'No especificado')}\nMonto: {payload.get('Amount', 0)}"
        
        case_id = creatio.create_case(subject, notes)
        
        # Crear registros de personas si existen
        personas = payload.get('InvolvedPersons', [])
        created_persons = []
        
        for persona in personas:
            try:
                person_id = creatio.create_person_record(case_id, persona)
                created_persons.append({
                    'person_id': person_id,
                    'name': persona.get('FullName', 'Sin nombre')
                })
            except Exception as e:
                logger.error(f"❌ Error creando persona {persona.get('FullName', 'Sin nombre')}: {str(e)}")
                created_persons.append({
                    'error': str(e),
                    'name': persona.get('FullName', 'Sin nombre')
                })
        
        logger.info(f"✅ Integración completada: Caso {case_id} con {len(created_persons)} personas")
        
        return {
            'success': True,
            'crm_id': case_id,
            'case_id': case_id,
            'persons_created': len([p for p in created_persons if 'person_id' in p]),
            'persons_errors': len([p for p in created_persons if 'error' in p]),
            'persons_details': created_persons
        }
        
    except Exception as e:
        error_msg = f"Error en integración con Creatio: {str(e)}"
        logger.error(f"❌ {error_msg}")
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
    Prueba la conexión con Creatio
    """
    try:
        # Inicializar servicio de Creatio
        creatio = CreatioService(CREATIO_URL, CREATIO_USERNAME, CREATIO_PASSWORD)
        
        # Intentar autenticar
        if creatio.authenticate():
            logger.info("✅ Conexión con Creatio exitosa")
            return True
        else:
            logger.error("❌ Error de autenticación con Creatio")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error probando conexión con Creatio: {str(e)}")
        return False