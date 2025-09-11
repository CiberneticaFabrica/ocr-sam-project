# src/s3_document_processor/app.py
import json
import boto3
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List
import PyPDF2
import io

# Configuración de logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Clientes AWS
s3_client = boto3.client('s3')
sqs_client = boto3.client('sqs')
ses_client = boto3.client('ses')
dynamodb = boto3.resource('dynamodb')

# Variables de entorno
S3_BUCKET_NAME = os.environ['S3_BUCKET_NAME']
OCR_QUEUE_URL = os.environ['OCR_QUEUE_URL']
TRACKING_TABLE = os.environ.get('TRACKING_TABLE', '')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Procesa documentos depositados en la carpeta incoming del S3
    """
    try:
        logger.info(f"📁 S3 Document Processor event received: {json.dumps(event, default=str)}")
        
        # Procesar eventos S3
        results = []
        for record in event.get('Records', []):
            try:
                result = process_s3_event(record)
                results.append(result)
            except Exception as e:
                logger.error(f"❌ Error procesando evento S3: {str(e)}")
                results.append({'success': False, 'error': str(e)})
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'processed_events': len(results),
                'results': results
            })
        }
        
    except Exception as e:
        logger.error(f"❌ Error en S3 Document Processor: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def process_s3_event(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procesa un evento individual de S3
    """
    try:
        # Extraer información del evento S3
        bucket_name = record['s3']['bucket']['name']
        object_key = record['s3']['object']['key']
        
        logger.info(f"🔄 [S3-DOCUMENT-PROCESSOR] Procesando documento S3: {bucket_name}/{object_key}")
        logger.info(f"🔄 [S3-DOCUMENT-PROCESSOR] Event record completo: {record}")
        
        # Verificar que sea un PDF
        if not object_key.lower().endswith('.pdf'):
            logger.info(f"⚠️ Archivo no es PDF, saltando: {object_key}")
            return {'success': True, 'skipped': True, 'reason': 'Not a PDF file'}
        
        # Generar batch_id único
        batch_id = str(uuid.uuid4())
        
        # Extraer nombre del archivo sin extensión
        file_name = os.path.splitext(os.path.basename(object_key))[0]
        
        # Crear metadatos del batch
        batch_metadata = {
            'source': 's3_direct',
            'file_name': file_name,
            'original_key': object_key,
            'deposited_at': datetime.utcnow().isoformat(),
            'batch_id': batch_id
        }
        
        # Procesar PDF con validación completa
        processing_result = process_pdf_from_s3(bucket_name, object_key, batch_id)
        
        if not processing_result['success']:
            logger.error(f"❌ Procesamiento fallido: {processing_result['error']}")
            
            # Enviar notificación de error si hay configuración válida
            if 'config_data' in processing_result:
                send_validation_error_notification(
                    processing_result['config_data'],
                    processing_result.get('validation_result', {}),
                    batch_id
                )
            
            return {
                'success': False,
                'error': processing_result['error'],
                'batch_id': batch_id,
                'config_data': processing_result.get('config_data', {}),
                'validation_result': processing_result.get('validation_result', {})
            }
        
        # Extraer datos del resultado exitoso
        oficios = processing_result['oficios']
        config_data = processing_result['config_data']
        config_validation = processing_result['config_validation']
        quantity_validation = processing_result['quantity_validation']
        
        # Log de variables extraídas
        logger.info(f"📋 Variables extraídas de la primera página:")
        logger.info(f"   CANTIDAD_OFICIOS: {config_data.get('cantidad_oficios', 'No encontrado')}")
        logger.info(f"   EMPRESA: {config_data.get('empresa', 'No encontrado')}")
        logger.info(f"   ORIGEN: {config_data.get('origen', 'No encontrado')}")
        logger.info(f"   OBSERVACIONES: {config_data.get('observaciones', 'No encontrado')}")
        logger.info(f"   OPERADOR: {config_data.get('operador', 'No encontrado')}")
        
        # Si llegamos aquí, la validación ya pasó en process_pdf_from_s3
        logger.info(f"✅ Validación de cantidad exitosa - Continuando con procesamiento")
        
        # Actualizar metadatos con configuración extraída
        batch_metadata.update({
            'config_data': config_data,
            'config_validation': config_validation,
            'quantity_validation': quantity_validation
        })
        
        # Crear registro en DynamoDB si está habilitado
        if TRACKING_TABLE:
            create_batch_tracking_record(batch_id, len(oficios), batch_metadata)
        
        # Enviar oficios a la cola de procesamiento
        jobs_sent = send_oficios_to_processing_queue(oficios, batch_id)
        
        logger.info(f"✅ Documento procesado: {len(oficios)} oficios, {jobs_sent} jobs enviados")
        
        return {
            'success': True,
            'batch_id': batch_id,
            'oficios_count': len(oficios),
            'jobs_sent': jobs_sent,
            'source': 's3_direct',
            'config_data': config_data,
            'validation_status': quantity_validation.get('validation_status', 'unknown')
        }
        
    except Exception as e:
        logger.error(f"❌ Error procesando evento S3: {str(e)}")
        return {'success': False, 'error': str(e)}

def process_pdf_from_s3(bucket_name: str, object_key: str, batch_id: str) -> Dict[str, Any]:
    """
    Procesa PDF desde S3 con extracción de configuración y validación completa
    """
    try:
        # Descargar PDF desde S3
        logger.info(f"🔍 Intentando descargar: s3://{bucket_name}/{object_key}")
        
        # Verificar si el objeto existe
        try:
            s3_client.head_object(Bucket=bucket_name, Key=object_key)
            logger.info(f"✅ Objeto encontrado en S3")
        except Exception as e:
            logger.error(f"❌ Objeto no encontrado: {str(e)}")
            # Intentar con URL decode
            import urllib.parse
            decoded_key = urllib.parse.unquote_plus(object_key)
            logger.info(f"🔄 Intentando con clave decodificada: {decoded_key}")
            try:
                s3_client.head_object(Bucket=bucket_name, Key=decoded_key)
                object_key = decoded_key
                logger.info(f"✅ Objeto encontrado con clave decodificada")
            except Exception as e2:
                logger.error(f"❌ Objeto tampoco existe con clave decodificada: {str(e2)}")
                raise e
        
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        pdf_content = response['Body'].read()
        
        logger.info(f"📄 PDF descargado: {len(pdf_content)} bytes")
        
        # Extraer configuración de la primera página
        config_data = extract_batch_metadata_from_pdf(pdf_content, object_key)
        logger.info(f"📊 Configuración extraída: {config_data}")
        
        # Validar configuración
        config_validation = validate_config_data(config_data)
        
        if not config_validation['success']:
            logger.error(f"❌ Validación de configuración fallida: {config_validation['error']}")
            return {
                'success': False,
                'error': config_validation['error'],
                'config_data': config_data,
                'validation_result': config_validation
            }
        
        # PRIMERO: Validar cantidad de oficios vs declarada (SIN dividir el PDF aún)
        cantidad_declarada = config_data.get('cantidad_oficios', 0)
        
        # Contar separadores para validar cantidad SIN dividir
        separador_count = count_separators_in_pdf(pdf_content)
        cantidad_extraida = separador_count + 1  # +1 porque hay un oficio después del último separador
        
        quantity_validation = validate_quantity(cantidad_declarada, cantidad_extraida)
        
        # SI HAY DISCREPANCIA, DETENER PROCESO INMEDIATAMENTE
        if quantity_validation.get('validation_status') == 'mismatch_warning':
            logger.error(f"🚨 DISCREPANCIA DETECTADA - DETENIENDO PROCESO")
            logger.error(f"   Se declararon {cantidad_declarada} oficios")
            logger.error(f"   Se encontraron {cantidad_extraida} oficios")
            logger.error(f"   Diferencia: {quantity_validation.get('diferencia', 0)} oficios")
            
            return {
                'success': False,
                'error': f'Discrepancia en cantidad de oficios. Se declararon {cantidad_declarada} pero se encontraron {cantidad_extraida}. Proceso detenido.',
                'config_data': config_data,
                'validation_result': quantity_validation
            }
        
        # SOLO SI PASA LA VALIDACIÓN: Dividir PDF en oficios
        logger.info(f"✅ Validación exitosa - Dividiendo PDF en {cantidad_extraida} oficios")
        oficios = split_pdf_into_oficios_skip_config(pdf_content, batch_id)
        
        if not oficios:
            logger.error(f"❌ No se pudieron extraer oficios del PDF: {object_key}")
            return {
                'success': False,
                'error': 'No se pudieron extraer oficios del PDF',
                'config_data': config_data
            }
        
        # Guardar oficios individuales en S3
        saved_oficios = []
        for i, oficio_content in enumerate(oficios, 1):
            oficio_id = f"{batch_id}_oficio_{i:03d}"
            s3_key = f"oficios/lotes/{batch_id}/{oficio_id}.pdf"
            
            # Guardar oficio individual
            s3_client.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=s3_key,
                Body=oficio_content,
                ContentType='application/pdf'
            )
            
            saved_oficios.append({
                'oficio_id': oficio_id,
                's3_key': s3_key,
                'sequence_number': i,
                'size_bytes': len(oficio_content)
            })
            
            logger.info(f"💾 Oficio guardado: {s3_key}")
        
        return {
            'success': True,
            'oficios': saved_oficios,
            'config_data': config_data,
            'config_validation': config_validation,
            'quantity_validation': quantity_validation
        }
        
    except Exception as e:
        logger.error(f"❌ Error procesando PDF desde S3: {str(e)}")
        return {
            'success': False,
            'error': f'Error técnico procesando PDF: {str(e)}'
        }

def split_pdf_into_oficios_skip_config(pdf_content: bytes, batch_id: str) -> List[bytes]:
    """
    Divide PDF en oficios individuales usando separador de oficios
    """
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        total_pages = len(pdf_reader.pages)
        
        logger.info(f"📋 PDF tiene {total_pages} páginas")
        
        # Saltar la primera página (página de configuración)
        start_page = 1 if total_pages > 1 else 0
        oficios = []
        
        # Buscar separadores de oficios en las páginas
        separador_pages = []
        logger.info(f"🔍 Buscando separadores desde página {start_page + 1} hasta {total_pages}")
        
        for page_num in range(start_page, total_pages):
            page_text = pdf_reader.pages[page_num].extract_text()
            logger.info(f"📄 Página {page_num + 1}: {len(page_text)} caracteres")
            
            # Buscar el patrón de separador (más flexible)
            if "SEPARADOR DE OFICIOS" in page_text.upper() and "====" in page_text:
                separador_pages.append(page_num)
                logger.info(f"🔍 Separador encontrado en página {page_num + 1}")
                logger.info(f"   Texto de la página: {page_text[:200]}...")
            elif "SEPARADOR" in page_text.upper():
                logger.info(f"⚠️ Página {page_num + 1} contiene 'SEPARADOR' pero no coincide con patrón")
                logger.info(f"   Texto: {page_text[:200]}...")
        
        if separador_pages:
            # Dividir por separadores
            oficios = split_by_separators(pdf_reader, separador_pages, start_page, total_pages)
        else:
            # Fallback: dividir por páginas si no hay separadores
            logger.warning("⚠️ No se encontraron separadores, dividiendo por páginas")
            for page_num in range(start_page, total_pages):
                pdf_writer = PyPDF2.PdfWriter()
                pdf_writer.add_page(pdf_reader.pages[page_num])
                
                output = io.BytesIO()
                pdf_writer.write(output)
                oficios.append(output.getvalue())
        
        logger.info(f"✂️ PDF dividido en {len(oficios)} oficios usando separadores")
        return oficios
        
    except Exception as e:
        logger.error(f"❌ Error dividiendo PDF: {str(e)}")
        return []

def split_by_separators(pdf_reader, separador_pages: List[int], start_page: int, total_pages: int) -> List[bytes]:
    """
    Divide PDF usando las páginas con separadores como puntos de división
    """
    try:
        oficios = []
        
        # Crear rangos de páginas para cada oficio
        ranges = []
        prev_page = start_page
        
        for sep_page in separador_pages:
            if sep_page > prev_page:
                ranges.append((prev_page, sep_page - 1))
            prev_page = sep_page + 1
        
        # Agregar el último rango si hay páginas después del último separador
        if prev_page < total_pages:
            ranges.append((prev_page, total_pages - 1))
        
        logger.info(f"📊 Rangos de oficios detectados: {ranges}")
        
        # Crear PDFs individuales para cada rango
        for i, (start, end) in enumerate(ranges):
            pdf_writer = PyPDF2.PdfWriter()
            
            for page_num in range(start, end + 1):
                pdf_writer.add_page(pdf_reader.pages[page_num])
            
            output = io.BytesIO()
            pdf_writer.write(output)
            oficios.append(output.getvalue())
            
            logger.info(f"📄 Oficio {i+1}: páginas {start+1}-{end+1}")
        
        return oficios
        
    except Exception as e:
        logger.error(f"❌ Error dividiendo por separadores: {str(e)}")
        return []

def split_pdf_into_oficios(pdf_content: bytes, batch_id: str) -> List[bytes]:
    """
    Divide PDF en oficios individuales usando PyPDF2 (versión original)
    """
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
        total_pages = len(pdf_reader.pages)
        
        logger.info(f"📋 PDF tiene {total_pages} páginas")
        
        # Estrategia simple: dividir por páginas
        # En el futuro se puede implementar detección inteligente de separadores
        oficios = []
        
        # Por ahora, asumimos que cada página es un oficio
        # Esto se puede mejorar con detección de separadores
        for page_num in range(total_pages):
            pdf_writer = PyPDF2.PdfWriter()
            pdf_writer.add_page(pdf_reader.pages[page_num])
            
            # Escribir a bytes
            output = io.BytesIO()
            pdf_writer.write(output)
            oficios.append(output.getvalue())
        
        logger.info(f"✂️ PDF dividido en {len(oficios)} oficios")
        return oficios
        
    except Exception as e:
        logger.error(f"❌ Error dividiendo PDF: {str(e)}")
        return []

def create_batch_tracking_record(batch_id: str, total_oficios: int, metadata: Dict[str, Any]) -> None:
    """
    Crea registro de tracking en DynamoDB
    """
    try:
        if not TRACKING_TABLE:
            return
            
        table = dynamodb.Table(TRACKING_TABLE)
        
        # Crear resumen del batch
        batch_summary = {
            'batch_id': batch_id,
            'oficio_id': 'BATCH_SUMMARY',
            'total_oficios': total_oficios,
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'source': 's3_direct',
            'metadata': metadata
        }
        
        table.put_item(Item=batch_summary)
        
        # Crear registros individuales para cada oficio
        for i in range(1, total_oficios + 1):
            oficio_id = f"{batch_id}_oficio_{i:03d}"
            oficio_record = {
                'batch_id': batch_id,
                'oficio_id': oficio_id,
                'sequence_number': i,
                'status': 'pending',
                'ocr_status': 'pending',
                'crm_status': 'pending',
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat(),
                'source': 's3_direct'
            }
            
            table.put_item(Item=oficio_record)
        
        logger.info(f"📊 Registros de tracking creados para batch {batch_id}")
        
    except Exception as e:
        logger.error(f"❌ Error creando registros de tracking: {str(e)}")

def send_oficios_to_processing_queue(oficios: List[Dict[str, Any]], batch_id: str) -> int:
    """
    Envía oficios a la cola de procesamiento OCR
    """
    try:
        jobs_sent = 0
        
        for oficio in oficios:
            # Crear mensaje para la cola de procesamiento
            message = {
                'job_id': oficio['oficio_id'],
                'batch_id': batch_id,
                's3_key': oficio['s3_key'],
                'sequence_number': oficio['sequence_number'],
                'source': 's3_direct',
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Enviar a SQS
            response = sqs_client.send_message(
                QueueUrl=OCR_QUEUE_URL,
                MessageBody=json.dumps(message)
            )
            
            if response.get('MessageId'):
                jobs_sent += 1
                logger.info(f"📤 Job enviado a cola: {oficio['oficio_id']}")
            else:
                logger.error(f"❌ Error enviando job: {oficio['oficio_id']}")
        
        return jobs_sent
        
    except Exception as e:
        logger.error(f"❌ Error enviando oficios a cola: {str(e)}")
        return 0

def count_separators_in_pdf(pdf_content: bytes) -> int:
    """
    Cuenta los separadores en el PDF sin dividirlo
    """
    try:
        from io import BytesIO
        
        # Leer el PDF
        pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_content))
        total_pages = len(pdf_reader.pages)
        
        # Saltar la primera página (página de configuración)
        start_page = 1 if total_pages > 1 else 0
        separador_count = 0
        
        # Buscar separadores en las páginas
        for page_num in range(start_page, total_pages):
            page_text = pdf_reader.pages[page_num].extract_text()
            # Buscar el patrón de separador
            if "SEPARADOR DE OFICIOS" in page_text.upper() and "====" in page_text:
                separador_count += 1
                logger.info(f"🔍 Separador encontrado en página {page_num + 1}")
        
        logger.info(f"📊 Total de separadores encontrados: {separador_count}")
        return separador_count
        
    except Exception as e:
        logger.error(f"❌ Error contando separadores: {str(e)}")
        return 0

def extract_batch_metadata_from_pdf(pdf_content: bytes, object_key: str) -> Dict[str, Any]:
    """
    Extrae metadatos de configuración de la primera página del PDF
    """
    try:
        import PyPDF2
        from io import BytesIO
        
        # Leer la primera página del PDF
        pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_content))
        if len(pdf_reader.pages) == 0:
            logger.error("❌ PDF no tiene páginas")
            return {}
        
        first_page = pdf_reader.pages[0]
        page_text = first_page.extract_text()
        
        logger.info(f"📄 Texto de primera página extraído: {len(page_text)} caracteres")
        
        # Extraer configuración usando patrones similares al email processor
        config_data = extract_config_from_text(page_text, object_key)
        
        return config_data
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo metadatos del PDF: {str(e)}")
        return {}

def extract_config_from_text(page_text: str, object_key: str) -> Dict[str, Any]:
    """
    Extrae variables de configuración del texto de la primera página
    """
    try:
        import re
        
        # Patrones para extraer configuración (más específicos)
        patterns = {
            'cantidad_oficios': [
                r'CANTIDAD_OFICIOS\s*:\s*(\d+)',
                r'(?:cantidad_oficios|cantidad\s+oficios|oficios)\s*:?\s*(\d+)',
                r'(\d+)\s*oficios',
                r'(?:total|son|contiene)\s*(\d+)\s*(?:oficios|documentos)',
            ],
            'empresa': [
                r'EMPRESA\s*:\s*([A-Za-z\s]+?)(?:\n|ORIGEN|CANTIDAD|OBSERVACIONES|PROCESADO|$)',
                r'(?:empresa|compañia|organizacion)\s*:?\s*([A-Za-z\s]+?)(?:\n|ORIGEN|CANTIDAD|OBSERVACIONES|PROCESADO|$)',
            ],
            'origen': [
                r'ORIGEN\s*:\s*([A-Za-z\s]+?)(?:\n|EMPRESA|CANTIDAD|OBSERVACIONES|PROCESADO|$)',
                r'(?:origen|enviado\s+desde|ubicacion|provincia)\s*:?\s*([A-Za-z\s]+?)(?:\n|EMPRESA|CANTIDAD|OBSERVACIONES|PROCESADO|$)',
            ],
            'observaciones': [
                r'OBSERVACIONES\s*:\s*([A-Za-z\s]+?)(?:\n|EMPRESA|ORIGEN|CANTIDAD|PROCESADO|$)',
                r'(?:observaciones|comentarios|notas)\s*:?\s*([A-Za-z\s]+?)(?:\n|EMPRESA|ORIGEN|CANTIDAD|PROCESADO|$)',
            ],
            'operador': [
                r'PROCESADO\s+POR\s*:\s*([A-Za-z\s]+?)(?:\n|EMPRESA|ORIGEN|CANTIDAD|OBSERVACIONES|$)',
                r'(?:operador|usuario|responsable|procesado\s+por)\s*:?\s*([A-Za-z\s]+?)(?:\n|EMPRESA|ORIGEN|CANTIDAD|OBSERVACIONES|$)',
            ]
        }
        
        # Valores por defecto
        config_data = {
            'cantidad_oficios': 0,
            'empresa': 'No especificado',
            'origen': 'No especificado',
            'observaciones': 'Procesado automáticamente',
            'operador': 'Sistema',
            'fecha_procesamiento': datetime.utcnow().strftime('%Y-%m-%d'),
            'archivo_origen': object_key,
            'extraction_success': False
        }
        
        # Normalizar texto para búsqueda
        normalized_text = page_text.lower()
        
        # Extraer campos del texto
        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, normalized_text, re.IGNORECASE | re.MULTILINE)
                if match:
                    value = match.group(1).strip()
                    
                    if field == 'cantidad_oficios':
                        try:
                            config_data['cantidad_oficios'] = int(value)
                        except:
                            pass
                    elif field == 'empresa':
                        if len(value) > 3:
                            config_data['empresa'] = value
                    elif field == 'origen':
                        config_data['origen'] = value
                    elif field == 'observaciones':
                        config_data['observaciones'] = value
                    elif field == 'operador':
                        config_data['operador'] = value
                    
                    break
        
        # Intentar extraer operador del nombre del archivo como fallback
        if config_data['operador'] == 'Sistema':
            operador_from_filename = extract_operador_from_filename(object_key)
            if operador_from_filename:
                config_data['operador'] = operador_from_filename
        
        # Marcar como exitoso si al menos se extrajo cantidad de oficios
        config_data['extraction_success'] = config_data['cantidad_oficios'] > 0
        
        logger.info(f"📊 Configuración extraída: {config_data}")
        return config_data
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo configuración del texto: {str(e)}")
        return {
            'cantidad_oficios': 0,
            'empresa': 'No especificado',
            'origen': 'No especificado',
            'observaciones': 'Error en extracción',
            'operador': 'Sistema',
            'fecha_procesamiento': datetime.utcnow().strftime('%Y-%m-%d'),
            'archivo_origen': object_key,
            'extraction_success': False
        }

def extract_operador_from_filename(object_key: str) -> str:
    """
    Extrae el nombre del operador del nombre del archivo
    Formato esperado: edwinpeñalba_20250103.pdf
    """
    try:
        import re
        import os
        
        filename = os.path.basename(object_key)
        # Remover extensión
        name_without_ext = os.path.splitext(filename)[0]
        
        # Patrón para extraer nombre antes del primer guión bajo o fecha
        match = re.match(r'^([a-zA-ZáéíóúÁÉÍÓÚñÑ]+)', name_without_ext)
        if match:
            return match.group(1)
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo operador del filename: {str(e)}")
        return None

def validate_config_data(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida que la configuración extraída sea válida
    """
    try:
        validation_result = {
            'success': True,
            'error': None,
            'warnings': [],
            'missing_fields': []
        }
        
        # Verificar campos requeridos
        required_fields = ['cantidad_oficios', 'empresa']
        
        for field in required_fields:
            if not config_data.get(field) or config_data.get(field) == 'No especificado':
                validation_result['missing_fields'].append(field)
        
        # Validar cantidad de oficios
        cantidad = config_data.get('cantidad_oficios', 0)
        if cantidad <= 0:
            validation_result['success'] = False
            validation_result['error'] = 'La cantidad de oficios debe ser mayor a 0'
        elif cantidad > 1000:
            validation_result['warnings'].append('Cantidad de oficios muy alta, verificar')
        
        # Validar empresa
        empresa = config_data.get('empresa', '')
        if len(empresa) < 3:
            validation_result['success'] = False
            validation_result['error'] = 'El nombre de la empresa debe tener al menos 3 caracteres'
        
        # Si hay campos faltantes pero no críticos, marcar como warning
        if validation_result['missing_fields'] and validation_result['success']:
            validation_result['warnings'].append(f'Campos faltantes: {", ".join(validation_result["missing_fields"])}')
        
        return validation_result
        
    except Exception as e:
        logger.error(f"❌ Error validando configuración: {str(e)}")
        return {
            'success': False,
            'error': f'Error técnico en validación: {str(e)}',
            'warnings': [],
            'missing_fields': []
        }

def validate_quantity(cantidad_declarada: int, cantidad_extraida: int) -> Dict[str, Any]:
    """
    Valida que la cantidad de oficios extraídos coincida con la declarada
    """
    try:
        validation_result = {
            'success': True,
            'error': None,
            'cantidad_declarada': cantidad_declarada,
            'cantidad_extraida': cantidad_extraida,
            'diferencia': abs(cantidad_declarada - cantidad_extraida),
            'validation_status': 'pending'
        }
        
        if cantidad_declarada == 0:
            # Si no se declaró cantidad, procesar todo como está
            validation_result['validation_status'] = 'no_declaration_proceeding'
            logger.info("⚠️ No se declaró cantidad, procesando oficios encontrados")
            
        elif cantidad_extraida == 0:
            validation_result['success'] = False
            validation_result['validation_status'] = 'no_oficios_found'
            validation_result['error'] = 'No se pudieron extraer oficios del PDF. Verifique el formato del archivo.'
            logger.error("❌ No se encontraron oficios en el PDF")
            
        elif cantidad_declarada == cantidad_extraida:
            validation_result['validation_status'] = 'exact_match'
            logger.info("✅ Cantidad declarada coincide exactamente")
            
        else:
            # Validación flexible - procesar los oficios encontrados pero advertir
            validation_result['validation_status'] = 'mismatch_warning'
            validation_result['error'] = f'Cantidad de oficios no coincide. Se declararon {cantidad_declarada} pero se encontraron {cantidad_extraida}. Procesando oficios encontrados.'
            logger.warning(f"⚠️ {validation_result['error']}")
        
        return validation_result
        
    except Exception as e:
        logger.error(f"❌ Error validando cantidad: {str(e)}")
        return {
            'success': False,
            'error': f'Error técnico validando cantidad: {str(e)}',
            'validation_status': 'error'
        }

def send_validation_error_notification(config_data: Dict[str, Any], validation_result: Dict[str, Any], batch_id: str):
    """
    Envía notificación de error de validación
    """
    try:
        # Log detallado del error
        logger.error(f"🚨 NOTIFICACIÓN DE DISCREPANCIA - Batch {batch_id}")
        logger.error(f"   Archivo: {config_data.get('archivo_origen', 'Desconocido')}")
        logger.error(f"   Empresa: {config_data.get('empresa', 'No especificado')}")
        logger.error(f"   Origen: {config_data.get('origen', 'No especificado')}")
        logger.error(f"   Operador: {config_data.get('operador', 'Sistema')}")
        logger.error(f"   Error: {validation_result.get('error', 'Error desconocido')}")
        logger.error(f"   Cantidad Declarada: {config_data.get('cantidad_oficios', 0)} oficios")
        logger.error(f"   Cantidad Encontrada: {validation_result.get('cantidad_extraida', 0)} oficios")
        logger.error(f"   Diferencia: {validation_result.get('diferencia', 0)} oficios")
        
        # Intentar enviar email de notificación
        try:
            send_email_notification(config_data, validation_result, batch_id)
        except Exception as email_error:
            logger.error(f"❌ Error enviando email: {str(email_error)}")
            # Guardar notificación para envío posterior
            save_notification_for_later(config_data, validation_result, batch_id)
        
    except Exception as e:
        logger.error(f"❌ Error enviando notificación de error: {str(e)}")

def send_email_notification(config_data: Dict[str, Any], validation_result: Dict[str, Any], batch_id: str):
    """
    Envía notificación por email usando SES (mismo método que email_processor)
    """
    try:
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Obtener email de destino
        recipient_email = os.environ.get('SESFromEmail', 'edwin.penalba@cibernetica.net')
        sender_email = os.environ.get('SESReceiveEmail', 'oficios@cibernetica.xyz')
        
        logger.info(f"📧 Variables de entorno SES:")
        logger.info(f"   SESReceiveEmail: {os.environ.get('SESReceiveEmail', 'NO_DEFINIDO')}")
        logger.info(f"   SESFromEmail: {os.environ.get('SESFromEmail', 'NO_DEFINIDO')}")
        
        # Verificar que las variables de entorno estén definidas
        if not os.environ.get('SESReceiveEmail'):
            logger.warning(f"⚠️ SESReceiveEmail no está definido en variables de entorno")
        if not os.environ.get('SESFromEmail'):
            logger.warning(f"⚠️ SESFromEmail no está definido en variables de entorno")
        
        # Crear asunto
        subject = f"🚨 [S3-DIRECT] DISCREPANCIA EN CANTIDAD DE OFICIOS - Batch {batch_id}"
        
        # Log del contenido del email
        logger.info(f"📧 Preparando email de notificación:")
        logger.info(f"   Destinatario: {recipient_email}")
        logger.info(f"   Remitente: {sender_email}")
        logger.info(f"   Asunto: {subject}")
        
        # Crear cuerpo del email en texto plano
        text_body = f"""
🚨 [S3-DIRECT] DISCREPANCIA EN CANTIDAD DE OFICIOS DETECTADA

Detalles del Lote:
- Batch ID: {batch_id}
- Archivo: {config_data.get('archivo_origen', 'Desconocido')}
- Empresa: {config_data.get('empresa', 'No especificado')}
- Origen: {config_data.get('origen', 'No especificado')}
- Operador: {config_data.get('operador', 'Sistema')}

Discrepancia Detectada:
- Cantidad Declarada: {config_data.get('cantidad_oficios', 0)} oficios
- Cantidad Encontrada: {validation_result.get('cantidad_extraida', 0)} oficios
- Diferencia: {validation_result.get('diferencia', 0)} oficios

Acción Tomada: El sistema DETUVO el procesamiento debido a la discrepancia.

Esta notificación fue generada automáticamente por el sistema OCR SAM.
        """
        
        # Crear cuerpo del email en HTML con estilos
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #dc3545;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    border: 1px solid #dee2e6;
                    border-top: none;
                }}
                .section {{
                    margin-bottom: 20px;
                }}
                .section h3 {{
                    color: #495057;
                    border-bottom: 2px solid #007bff;
                    padding-bottom: 5px;
                }}
                .info-grid {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 10px;
                    margin: 10px 0;
                }}
                .info-item {{
                    background-color: white;
                    padding: 10px;
                    border-radius: 4px;
                    border-left: 4px solid #007bff;
                }}
                .warning {{
                    background-color: #fff3cd;
                    border: 1px solid #ffeaa7;
                    color: #856404;
                    padding: 15px;
                    border-radius: 4px;
                    margin: 15px 0;
                }}
                .footer {{
                    text-align: center;
                    color: #6c757d;
                    font-size: 0.9em;
                    margin-top: 20px;
                    padding-top: 20px;
                    border-top: 1px solid #dee2e6;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🚨 [S3-DIRECT] Discrepancia en Cantidad de Oficios Detectada</h1>
            </div>
            
            <div class="content">
                <div class="section">
                    <h3>📋 Detalles del Lote</h3>
                    <div class="info-grid">
                        <div class="info-item">
                            <strong>Batch ID:</strong><br>
                            {batch_id}
                        </div>
                        <div class="info-item">
                            <strong>Archivo:</strong><br>
                            {config_data.get('archivo_origen', 'Desconocido')}
                        </div>
                        <div class="info-item">
                            <strong>Empresa:</strong><br>
                            {config_data.get('empresa', 'No especificado')}
                        </div>
                        <div class="info-item">
                            <strong>Origen:</strong><br>
                            {config_data.get('origen', 'No especificado')}
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <h3>⚠️ Discrepancia Detectada</h3>
                    <div class="warning">
                        <div class="info-grid">
                            <div class="info-item">
                                <strong>Cantidad Declarada:</strong><br>
                                {config_data.get('cantidad_oficios', 0)} oficios
                            </div>
                            <div class="info-item">
                                <strong>Cantidad Encontrada:</strong><br>
                                {validation_result.get('cantidad_extraida', 0)} oficios
                            </div>
                            <div class="info-item">
                                <strong>Diferencia:</strong><br>
                                {validation_result.get('diferencia', 0)} oficios
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <h3>🛑 Acción Tomada</h3>
                    <p><strong>El sistema DETUVO el procesamiento debido a la discrepancia.</strong></p>
                    <p>Por favor, verifique el archivo PDF y la configuración declarada antes de reintentar el procesamiento.</p>
                </div>
            </div>
            
            <div class="footer">
                <p><em>Esta notificación fue generada automáticamente por el sistema OCR SAM.</em></p>
            </div>
        </body>
        </html>
        """
        
        # Crear mensaje multipart (igual que email_processor)
        message = MIMEMultipart('alternative')
        message['From'] = sender_email
        message['To'] = recipient_email
        message['Subject'] = subject
        
        # Agregar versión texto plano
        text_part = MIMEText(text_body, 'plain', 'utf-8')
        message.attach(text_part)
        
        # Agregar versión HTML
        html_part = MIMEText(html_body, 'html', 'utf-8')
        message.attach(html_part)
        
        # Log del contenido del email para debug
        logger.info(f"📧 Contenido del email (primeras 200 caracteres):")
        logger.info(f"   {text_body[:200]}...")
        
        # Enviar usando SES (mismo método que email_processor)
        response = ses_client.send_raw_email(
            Source=sender_email,
            Destinations=[recipient_email],
            RawMessage={'Data': message.as_string()}
        )
        
        logger.info(f"📧 Email de notificación enviado exitosamente. MessageId: {response['MessageId']}")
        logger.info(f"📧 [FIXED] Datos del email - Cantidad encontrada: {validation_result.get('cantidad_extraida', 0)}")
        logger.info(f"📧 Respuesta completa de SES: {response}")
        
        # Verificar si el email fue realmente enviado
        if 'MessageId' in response:
            logger.info(f"✅ Email confirmado enviado con ID: {response['MessageId']}")
        else:
            logger.warning(f"⚠️ Email enviado pero sin MessageId en respuesta")
        
    except Exception as e:
        logger.error(f"❌ Error enviando email de notificación: {str(e)}")
        logger.error(f"❌ Tipo de error: {type(e).__name__}")
        logger.error(f"❌ Detalles del error: {str(e)}")
        raise e

def save_notification_for_later(config_data: Dict[str, Any], validation_result: Dict[str, Any], batch_id: str):
    """
    Guarda notificación que no se pudo enviar para reintento posterior
    """
    try:
        failed_notification = {
            'batch_id': batch_id,
            'recipient': config_data.get('operador', 'sistema'),
            'subject': f"Error en Procesamiento de Lote - {config_data.get('empresa', 'Cliente')}",
            'message': validation_result.get('error', 'Error desconocido'),
            'config_data': config_data,
            'validation_result': validation_result,
            'timestamp': datetime.utcnow().isoformat(),
            'reason': 'validation_failed'
        }
        
        notification_key = f"notifications/s3_errors/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{batch_id}.json"
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=notification_key,
            Body=json.dumps(failed_notification, ensure_ascii=False, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"📧 Notificación de error guardada: {notification_key}")
        
    except Exception as e:
        logger.error(f"❌ Error guardando notificación pendiente: {str(e)}")
