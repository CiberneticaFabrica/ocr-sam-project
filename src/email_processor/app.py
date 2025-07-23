# src/email_processor/app.py - VERSIÓN CORREGIDA
import json
import boto3
import logging
import os
import uuid
import re
from datetime import datetime
from typing import Dict, Any, List, Tuple
import PyPDF2
from io import BytesIO
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
TRACKING_TABLE = os.environ['TRACKING_TABLE']
SES_FROM_EMAIL = os.environ.get('SES_FROM_EMAIL', 'notify@softwarefactory.cibernetica.xyz')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Procesa emails de SES y separa PDFs en oficios individuales con validación completa
    """
    try:
        logger.info(f"📧 Event received: {json.dumps(event, default=str)}")
        
        # Procesar eventos de S3 (cuando SES guarda el email)
        for record in event.get('Records', []):
            if record.get('eventSource') == 'aws:s3':
                process_s3_email_event(record)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Email processing completed'})
        }
        
    except Exception as e:
        logger.error(f"❌ Error en email processor: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def process_s3_email_event(record: Dict[str, Any]):
    """
    Procesa evento de S3 cuando llega un email completo de SES
    """
    try:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        
        logger.info(f"📧 Procesando email: s3://{bucket}/{key}")
        
        # Verificar que es un email de SES
        if not key.startswith('emails/'):
            logger.info("❌ Archivo no es email de SES, ignorando")
            return
        
        # Descargar y parsear el email completo
        logger.info("📥 Descargando email desde S3...")
        email_data = download_and_parse_email(bucket, key)
        
        if not email_data:
            logger.error("❌ No se pudo parsear el email")
            return
        
        # Extraer datos del cuerpo del email
        email_metadata = extract_email_body_data(email_data)
        logger.info(f"📊 Datos extraídos: {email_metadata}")
        
        # Buscar attachment PDF
        pdf_attachment = find_pdf_attachment(email_data)
        
        if not pdf_attachment:
            logger.error("❌ No se encontró attachment PDF en el email")
            # Solo enviar notificación si SES está configurado
            try:
                send_error_notification(
                    email_metadata.get('contact_email', 'unknown@email.com'),
                    "Error: No se encontró archivo PDF adjunto",
                    "Por favor incluya un archivo PDF con los oficios en su correo."
                )
            except Exception as ses_error:
                logger.warning(f"⚠️ No se pudo enviar notificación SES: {ses_error}")
                save_notification_for_later(email_metadata.get('contact_email'), "No PDF found", "No se encontró PDF adjunto")
            return
        
        # Generar ID único para este lote
        batch_id = str(uuid.uuid4())
        logger.info(f"🏷️ Batch ID generado: {batch_id}")
        
        # Agregar información del batch a metadata
        email_metadata['batch_id'] = batch_id
        email_metadata['email_s3_location'] = f"s3://{bucket}/{key}"
        
        # Separar PDF y validar cantidad - VERSIÓN CORREGIDA
        logger.info("✂️ Iniciando separación y validación de PDF...")
        validation_result = process_pdf_with_validation_improved(pdf_attachment, batch_id, email_metadata)
        
        if not validation_result['success']:
            logger.error(f"❌ Validación fallida: {validation_result['error']}")
            try:
                send_validation_error_notification(email_metadata, validation_result)
            except Exception as ses_error:
                logger.warning(f"⚠️ No se pudo enviar notificación SES: {ses_error}")
                save_notification_for_later(email_metadata.get('contact_email'), "Validation failed", validation_result['error'])
            save_failed_processing_log(batch_id, email_metadata, validation_result)
            return
        
        # Si la validación es exitosa, crear trabajos de OCR
        oficios = validation_result['oficios']
        logger.info(f"✅ Validación exitosa. Creando {len(oficios)} trabajos de OCR...")
        
        # Crear trabajos de OCR
        create_ocr_jobs(oficios, batch_id, email_metadata)
        
        # Crear registro del lote en DynamoDB
        create_enhanced_batch_record(batch_id, len(oficios), email_metadata, validation_result)
        
        # Guardar log de éxito
        save_successful_processing_log(batch_id, email_metadata, validation_result)
        
        # Enviar confirmación al cliente (solo si SES funciona)
        try:
            send_success_notification(email_metadata, len(oficios), batch_id, validation_result.get('validation_status', 'exact_match'))
        except Exception as ses_error:
            logger.warning(f"⚠️ No se pudo enviar notificación SES: {ses_error}")
            save_notification_for_later(email_metadata.get('contact_email'), "Success", f"Lote {batch_id} procesado con {len(oficios)} oficios")
        
        logger.info(f"🎉 Procesamiento completado exitosamente para batch {batch_id}")
        
    except Exception as e:
        logger.error(f"❌ Error procesando email: {str(e)}")
        raise

def download_and_parse_email(bucket: str, key: str) -> Dict[str, Any]:
    """
    Descarga y parsea el email completo desde S3
    """
    try:
        # Descargar email raw
        response = s3_client.get_object(Bucket=bucket, Key=key)
        email_content = response['Body'].read()
        
        # Parsear email usando librería email de Python
        email_message = email.message_from_bytes(email_content)
        
        # Extraer información básica
        email_data = {
            'subject': email_message.get('Subject', ''),
            'from': email_message.get('From', ''),
            'to': email_message.get('To', ''),
            'date': email_message.get('Date', ''),
            'message_id': email_message.get('Message-ID', ''),
            'body': '',
            'attachments': []
        }
        
        # Extraer cuerpo y attachments
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get('Content-Disposition', ''))
                
                # Extraer cuerpo del email
                if content_type == 'text/plain' and 'attachment' not in content_disposition:
                    body = part.get_payload(decode=True)
                    if body:
                        email_data['body'] += body.decode('utf-8', errors='ignore')
                
                # Extraer attachments
                elif 'attachment' in content_disposition:
                    filename = part.get_filename()
                    if filename and filename.lower().endswith('.pdf'):
                        attachment_data = part.get_payload(decode=True)
                        email_data['attachments'].append({
                            'filename': filename,
                            'content': attachment_data,
                            'content_type': content_type
                        })
        
        logger.info(f"📧 Email parseado: {len(email_data['attachments'])} attachments, body: {len(email_data['body'])} chars")
        return email_data
        
    except Exception as e:
        logger.error(f"❌ Error parseando email: {str(e)}")
        return None

def extract_email_body_data(email_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae información estructurada del cuerpo del email
    """
    try:
        body = email_data.get('body', '').strip()
        
        # EXTRAER EMAIL DEL REMITENTE DIRECTAMENTE
        from_header = email_data.get('from', '')
        contact_email = extract_email_from_header(from_header)
        
        # Patterns simplificados
        patterns = {
            'empresa': [
                r'(?:empresa|compañia|organizacion):\s*([^\n\r]+)',
                r'(?:empresa|compañia|organizacion)\s*([^\n\r]+)',
            ],
            'cantidad_oficios': [
                r'(?:cantidad_oficios|cantidad\s+oficios|oficios):\s*(\d+)',
                r'(\d+)\s*oficios',
                r'(?:total|son|contiene)\s*(\d+)\s*(?:oficios|documentos)',
            ],
            'origen': [
                r'(?:origen|enviado\s+desde|ubicacion|provincia):\s*([^\n\r]+)',
                r'(?:desde|de)\s*([a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+)(?:\s|$)',
            ],
            'observaciones': [
                r'(?:observaciones|comentarios|notas):\s*([^\n\r]+)',
                r'(?:obs|nota):\s*([^\n\r]+)',
            ]
        }
        
        extracted_data = {
            'contact_email': contact_email,
            'empresa': extract_empresa_from_email(contact_email),
            'cantidad_oficios_declarada': 0,
            'origen': 'No especificado',
            'fecha_envio': datetime.utcnow().strftime('%Y-%m-%d'),
            'observaciones': 'Procesado automáticamente',
            'extraction_success': bool(contact_email),
            'email_subject': email_data.get('subject', ''),
            'email_date': email_data.get('date', ''),
            'raw_body': body[:500]
        }
        
        # Normalizar texto para búsqueda
        normalized_body = body.lower()
        
        # Extraer campos del cuerpo
        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, normalized_body, re.IGNORECASE | re.MULTILINE)
                if match:
                    value = match.group(1).strip()
                    
                    if field == 'empresa':
                        if len(value) > 3:
                            extracted_data['empresa'] = value
                    elif field == 'cantidad_oficios':
                        try:
                            extracted_data['cantidad_oficios_declarada'] = int(value)
                        except:
                            pass
                    elif field == 'origen':
                        extracted_data['origen'] = value
                    elif field == 'observaciones':
                        extracted_data['observaciones'] = value
                    
                    break
        
        logger.info(f"📊 Datos extraídos del email: {extracted_data}")
        return extracted_data
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo datos del email: {str(e)}")
        return {
            'contact_email': 'unknown@email.com',
            'empresa': 'No especificado',
            'cantidad_oficios_declarada': 0,
            'origen': 'No especificado',
            'fecha_envio': datetime.utcnow().strftime('%Y-%m-%d'),
            'observaciones': 'Error en procesamiento',
            'extraction_success': False
        }

def extract_email_from_header(from_header: str) -> str:
    """
    Extrae el email limpio del header From
    """
    try:
        email_patterns = [
            r'<([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>',
            r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        ]
        
        for pattern in email_patterns:
            match = re.search(pattern, from_header)
            if match:
                email = match.group(1).lower().strip()
                logger.info(f"📧 Email extraído del From header: {email}")
                return email
        
        logger.warning(f"⚠️ No se pudo extraer email del header: {from_header}")
        return 'unknown@email.com'
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo email del header: {str(e)}")
        return 'unknown@email.com'

def extract_empresa_from_email(email: str) -> str:
    """
    Infiere el nombre de la empresa basado en el dominio del email
    """
    try:
        if '@' not in email or email == 'unknown@email.com':
            return 'No especificado'
        
        domain = email.split('@')[1].lower()
        
        domain_mapping = {
            'gmail.com': 'Cliente Gmail',
            'hotmail.com': 'Cliente Hotmail', 
            'outlook.com': 'Cliente Outlook',
            'yahoo.com': 'Cliente Yahoo',
            'globalbank.com.pa': 'Global Bank',
            'bancoazteca.com.pa': 'Banco Azteca',
            'bancogeneral.com': 'Banco General',
            'bac.net': 'BAC',
            'citi.com': 'Citibank',
            'cibernetica.net': 'Cibernética'  # Agregado
        }
        
        if domain in domain_mapping:
            return domain_mapping[domain]
        
        if '.' in domain:
            company_part = domain.split('.')[0]
            return company_part.capitalize()
        
        return f"Cliente {domain}"
        
    except Exception as e:
        logger.error(f"❌ Error infiriendo empresa del email: {str(e)}")
        return 'No especificado'

def find_pdf_attachment(email_data: Dict[str, Any]) -> bytes:
    """
    Busca y retorna el primer attachment PDF encontrado
    """
    try:
        attachments = email_data.get('attachments', [])
        
        for attachment in attachments:
            if attachment['filename'].lower().endswith('.pdf'):
                logger.info(f"📎 PDF encontrado: {attachment['filename']}")
                return attachment['content']
        
        logger.warning("⚠️ No se encontró attachment PDF")
        return None
        
    except Exception as e:
        logger.error(f"❌ Error buscando PDF attachment: {str(e)}")
        return None

def process_pdf_with_validation_improved(pdf_content: bytes, batch_id: str, email_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procesa PDF con lógica de separación mejorada
    """
    try:
        logger.info("🔍 Analizando PDF con lógica mejorada...")
        oficios = split_pdf_into_oficios_smart(pdf_content, batch_id, email_metadata)
        
        cantidad_extraida = len(oficios)
        cantidad_declarada = email_metadata.get('cantidad_oficios_declarada', 0)
        
        logger.info(f"📊 Cantidad declarada: {cantidad_declarada}, Cantidad extraída: {cantidad_extraida}")
        
        # Validación más flexible
        validation_result = {
            'success': False,
            'cantidad_declarada': cantidad_declarada,
            'cantidad_extraida': cantidad_extraida,
            'diferencia': abs(cantidad_declarada - cantidad_extraida),
            'oficios': oficios,
            'error': None,
            'validation_status': 'pending'
        }
        
        # Lógica de validación mejorada
        if cantidad_declarada == 0:
            # Si no se declaró cantidad, procesar todo como está
            validation_result['success'] = True
            validation_result['validation_status'] = 'no_declaration_proceeding'
            logger.info("⚠️ No se declaró cantidad, procesando oficios encontrados")
            
        elif cantidad_extraida == 0:
            validation_result['validation_status'] = 'no_oficios_found'
            validation_result['error'] = 'No se pudieron extraer oficios del PDF. Verifique el formato del archivo.'
            logger.error("❌ No se encontraron oficios en el PDF")
            
        elif cantidad_declarada == cantidad_extraida:
            validation_result['success'] = True
            validation_result['validation_status'] = 'exact_match'
            logger.info("✅ Cantidad declarada coincide exactamente")
            
        else:
            # Validación más flexible - permitir procesar si hay oficios
            if cantidad_extraida > 0:
                validation_result['success'] = True
                validation_result['validation_status'] = 'partial_match'
                logger.info(f"⚠️ Procesando {cantidad_extraida} oficios de {cantidad_declarada} declarados")
            else:
                validation_result['validation_status'] = 'mismatch'
                validation_result['error'] = f'No se encontraron oficios. Se declararon {cantidad_declarada} pero no se pudieron extraer.'
                logger.error(f"❌ No se encontraron oficios: {validation_result['error']}")
        
        return validation_result
        
    except Exception as e:
        logger.error(f"❌ Error procesando PDF: {str(e)}")
        return {
            'success': False,
            'error': f'Error técnico procesando PDF: {str(e)}',
            'validation_status': 'error',
            'oficios': []
        }

def split_pdf_into_oficios_smart(pdf_content: bytes, batch_id: str, email_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    VERSIÓN MEJORADA: Separación inteligente de PDF en oficios
    """
    oficios = []
    
    try:
        pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_content))
        total_pages = len(pdf_reader.pages)
        
        logger.info(f"📄 PDF tiene {total_pages} páginas")
        
        # ESTRATEGIA 1: Buscar separadores explícitos primero
        explicit_separators = detect_explicit_separators(pdf_reader)
        
        if explicit_separators:
            logger.info(f"🎯 Encontrados separadores explícitos: {len(explicit_separators)}")
            oficio_groups = group_pages_by_explicit_separators(total_pages, explicit_separators)
        else:
            # ESTRATEGIA 2: Análisis de contenido para detectar inicios de oficios
            logger.info("🔍 No hay separadores explícitos, analizando contenido...")
            oficio_starts = detect_document_starts(pdf_reader)
            
            if len(oficio_starts) > 1:
                logger.info(f"📋 Detectados {len(oficio_starts)} inicios de documentos")
                oficio_groups = group_pages_by_document_starts(total_pages, oficio_starts)
            else:
                # ESTRATEGIA 3: Dividir por patrones de páginas
                logger.info("📄 Usando estrategia de páginas por defecto...")
                cantidad_declarada = email_metadata.get('cantidad_oficios_declarada', 0)
                oficio_groups = divide_by_page_estimation(total_pages, cantidad_declarada)
        
        logger.info(f"📋 Grupos finales detectados: {len(oficio_groups)}")
        
        # Crear PDFs individuales para cada oficio
        for i, page_range in enumerate(oficio_groups, 1):
            oficio_id = f"{batch_id}_oficio_{i:03d}"
            
            try:
                # Crear PDF individual
                oficio_pdf_bytes = create_individual_pdf(pdf_reader, page_range)
                
                # Guardar en S3
                s3_key = f"oficios/lotes/{batch_id}/{oficio_id}.pdf"
                s3_client.put_object(
                    Bucket=S3_BUCKET_NAME,
                    Key=s3_key,
                    Body=oficio_pdf_bytes,
                    ContentType='application/pdf',
                    Metadata={
                        'batch_id': batch_id,
                        'oficio_sequence': str(i),
                        'total_pages': str(len(page_range)),
                        'original_pages': f"{page_range[0]+1}-{page_range[-1]+1}",
                        'contact_email': email_metadata.get('contact_email', ''),
                        'empresa': email_metadata.get('empresa', '')
                    }
                )
                
                # Extraer texto de preview
                preview_text = extract_preview_text_enhanced(pdf_reader, page_range)
                
                # Información del oficio
                oficio_info = {
                    'oficio_id': oficio_id,
                    'batch_id': batch_id,
                    'sequence_number': i,
                    'page_range': page_range,
                    'original_page_numbers': f"{page_range[0]+1}-{page_range[-1]+1}",
                    's3_key': s3_key,
                    'preview_text': preview_text[:500],
                    'page_count': len(page_range),
                    'status': 'pending',
                    'created_at': datetime.utcnow().isoformat(),
                    'estimated_document_type': classify_document_type(preview_text)
                }
                
                oficios.append(oficio_info)
                
                logger.info(f"✅ Oficio {oficio_id} extraído: páginas {page_range[0]+1}-{page_range[-1]+1}")
                
            except Exception as e:
                logger.error(f"❌ Error extrayendo oficio {oficio_id}: {str(e)}")
                continue
        
        return oficios
        
    except Exception as e:
        logger.error(f"❌ Error separando PDF: {str(e)}")
        raise

def detect_explicit_separators(pdf_reader) -> List[int]:
    """
    Detecta solo separadores EXPLÍCITOS y obvios
    """
    separators = []
    
    try:
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text = page.extract_text().lower().strip()
            
            # Solo buscar separadores MUY ESPECÍFICOS
            explicit_patterns = [
                r'separador\s+de\s+oficios',
                r'={5,}\s*separador',
                r'nueva?\s+oficio',
                r'fin\s+de\s+oficio',
                r'separador\s+oficios',
                r'^\s*separador\s*$',
                r'^\s*={10,}\s*$',
                r'^\s*-{10,}\s*$'
            ]
            
            # Página debe ser muy corta Y tener patrón específico
            if len(text) < 100:  # Muy poco texto
                for pattern in explicit_patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        separators.append(page_num)
                        logger.debug(f"📄 Separador explícito en página {page_num + 1}: {pattern}")
                        break
        
        return separators
        
    except Exception as e:
        logger.error(f"❌ Error detectando separadores explícitos: {str(e)}")
        return []

def detect_document_starts(pdf_reader) -> List[int]:
    """
    Detecta inicios de documentos legales basado en patrones comunes
    """
    document_starts = [0]  # Primera página siempre es inicio
    
    try:
        for page_num in range(1, len(pdf_reader.pages)):  # Empezar desde página 2
            page = pdf_reader.pages[page_num]
            text = page.extract_text().strip()
            
            if len(text) < 50:  # Página muy vacía, probablemente no es inicio
                continue
            
            text_lines = text.split('\n')
            first_lines = ' '.join(text_lines[:5]).lower()  # Primeras 5 líneas
            
            # Patrones que indican inicio de documento legal
            document_start_patterns = [
                r'oficio\s+n[°º]?\s*\d+',
                r'juzgado\s+.+\s+de\s+.+',
                r'tribunal\s+.+',
                r'autoridad\s+competente',
                r'ref\s*[:.]?\s*expediente',
                r'exp\s*[:.]?\s*\d+',
                r'mediante\s+la\s+presente',
                r'por\s+medio\s+de\s+la\s+presente',
                r'fecha\s*[:.]?\s*\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}',
                r'despacho\s+judicial',
                r'sala\s+.+\s+de\s+.+',
                r'corte\s+suprema'
            ]
            
            # Verificar si algún patrón coincide en las primeras líneas
            for pattern in document_start_patterns:
                if re.search(pattern, first_lines):
                    document_starts.append(page_num)
                    logger.debug(f"📄 Inicio de documento detectado en página {page_num + 1}: {pattern}")
                    break
        
        # Remover duplicados y ordenar
        document_starts = sorted(list(set(document_starts)))
        
        logger.info(f"🎯 Inicios de documento detectados en páginas: {[p+1 for p in document_starts]}")
        return document_starts
        
    except Exception as e:
        logger.error(f"❌ Error detectando inicios de documentos: {str(e)}")
        return [0]  # Al menos la primera página

def group_pages_by_explicit_separators(total_pages: int, separators: List[int]) -> List[List[int]]:
    """
    Agrupa páginas usando separadores explícitos
    """
    oficios = []
    current_start = 0
    
    for separator in separators:
        if separator > current_start:
            pages = list(range(current_start, separator))
            if pages:
                oficios.append(pages)
        current_start = separator + 1
    
    # Agregar último grupo
    if current_start < total_pages:
        pages = list(range(current_start, total_pages))
        if pages:
            oficios.append(pages)
    
    return [grupo for grupo in oficios if len(grupo) > 0]

def group_pages_by_document_starts(total_pages: int, starts: List[int]) -> List[List[int]]:
    """
    Agrupa páginas usando inicios de documentos detectados
    """
    oficios = []
    
    for i in range(len(starts)):
        start_page = starts[i]
        end_page = starts[i + 1] if i + 1 < len(starts) else total_pages
        
        pages = list(range(start_page, end_page))
        if pages:
            oficios.append(pages)
    
    return oficios

def divide_by_page_estimation(total_pages: int, cantidad_declarada: int) -> List[List[int]]:
    """
    División por estimación de páginas (estrategia de respaldo)
    """
    if cantidad_declarada <= 0:
        # Si no hay cantidad declarada, asumir documentos de 1-3 páginas
        estimated_docs = max(1, total_pages // 2)  # Promedio 2 páginas por documento
        pages_per_doc = max(1, total_pages // estimated_docs)
    else:
        # Usar cantidad declarada
        estimated_docs = cantidad_declarada
        pages_per_doc = max(1, total_pages // estimated_docs)
    
    logger.info(f"📐 Estimación: {estimated_docs} documentos, ~{pages_per_doc} páginas cada uno")
    
    oficios = []
    current_page = 0
    
    for i in range(estimated_docs):
        # Calcular rango de páginas para este documento
        if i == estimated_docs - 1:  # Último documento, tomar páginas restantes
            end_page = total_pages
        else:
            end_page = min(current_page + pages_per_doc, total_pages)
        
        if current_page < total_pages:
            pages = list(range(current_page, end_page))
            if pages:
                oficios.append(pages)
        
        current_page = end_page
    
    return oficios

def create_individual_pdf(pdf_reader, page_range: List[int]) -> bytes:
    """
    Crea un PDF individual a partir de un rango de páginas
    """
    try:
        pdf_writer = PyPDF2.PdfWriter()
        
        for page_num in page_range:
            if page_num < len(pdf_reader.pages):
                pdf_writer.add_page(pdf_reader.pages[page_num])
        
        output_stream = BytesIO()
        pdf_writer.write(output_stream)
        pdf_bytes = output_stream.getvalue()
        output_stream.close()
        
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"❌ Error creando PDF individual: {str(e)}")
        raise

def extract_preview_text_enhanced(pdf_reader, page_range: List[int]) -> str:
    """
    Extrae texto de preview de las primeras páginas del oficio
    """
    try:
        preview_text = ""
        
        for page_num in page_range[:2]:  # Primeras 2 páginas
            if page_num < len(pdf_reader.pages):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                preview_text += text + "\n"
        
        return preview_text.strip()
        
    except Exception as e:
        logger.warning(f"⚠️ Error extrayendo preview text: {str(e)}")
        return ""

def classify_document_type(preview_text: str) -> str:
    """
    Clasifica el tipo de documento basado en el texto de preview
    """
    try:
        text_lower = preview_text.lower()
        
        if any(word in text_lower for word in ['embargo', 'secuestro', 'retención']):
            return 'embargo_secuestro'
        elif any(word in text_lower for word in ['citación', 'comparecer', 'audiencia']):
            return 'citacion'
        elif any(word in text_lower for word in ['levantamiento', 'desbloqueo']):
            return 'levantamiento'
        elif any(word in text_lower for word in ['allanamiento', 'registro']):
            return 'allanamiento'
        elif any(word in text_lower for word in ['investigación', 'información']):
            return 'investigacion'
        else:
            return 'oficio_general'
            
    except Exception as e:
        logger.warning(f"⚠️ Error clasificando documento: {str(e)}")
        return 'unknown'

def create_ocr_jobs(oficios: List[Dict[str, Any]], batch_id: str, email_metadata: Dict[str, Any]):
    """
    Crea trabajos de OCR para cada oficio y los envía a SQS
    """
    try:
        for oficio in oficios:
            ocr_message = {
                'job_id': oficio['oficio_id'],
                'batch_id': batch_id,
                'oficio_data': oficio,
                'email_metadata': email_metadata,
                'created_at': datetime.utcnow().isoformat(),
                'source': 'email_batch_validated'
            }
            
            sqs_client.send_message(
                QueueUrl=OCR_QUEUE_URL,
                MessageBody=json.dumps(ocr_message, ensure_ascii=False),
                MessageAttributes={
                    'BatchId': {
                        'StringValue': batch_id,
                        'DataType': 'String'
                    },
                    'OficioId': {
                        'StringValue': oficio['oficio_id'],
                        'DataType': 'String'
                    },
                    'ContactEmail': {
                        'StringValue': email_metadata.get('contact_email', ''),
                        'DataType': 'String'
                    },
                    'Empresa': {
                        'StringValue': email_metadata.get('empresa', ''),
                        'DataType': 'String'
                    },
                    'Source': {
                        'StringValue': 'email_batch_validated',
                        'DataType': 'String'
                    }
                }
            )
            
            logger.info(f"📤 Job OCR enviado para oficio {oficio['oficio_id']}")
        
        logger.info(f"✅ {len(oficios)} trabajos de OCR enviados a SQS")
        
    except Exception as e:
        logger.error(f"❌ Error creando trabajos OCR: {str(e)}")
        raise

def create_enhanced_batch_record(batch_id: str, total_oficios: int, email_metadata: Dict[str, Any], validation_result: Dict[str, Any]):
    """
    Crea registro completo del lote en DynamoDB
    """
    try:
        if not TRACKING_TABLE:
            logger.warning("⚠️ TRACKING_TABLE no configurada")
            return
        
        table = dynamodb.Table(TRACKING_TABLE)
        
        batch_record = {
            'batch_id': batch_id,
            'oficio_id': 'BATCH_SUMMARY',
            'status': 'processing',
            'created_at': datetime.utcnow().isoformat(),
            'total_oficios': total_oficios,
            'completed_oficios': 0,
            'failed_oficios': 0,
            'contact_email': email_metadata.get('contact_email'),
            'empresa': email_metadata.get('empresa'),
            'origen': email_metadata.get('origen'),
            'cantidad_declarada': email_metadata.get('cantidad_oficios_declarada'),
            'observaciones': email_metadata.get('observaciones'),
            'validation_status': validation_result.get('validation_status'),
            'cantidad_extraida': validation_result.get('cantidad_extraida'),
            'email_s3_location': email_metadata.get('email_s3_location'),
            'processing_started_at': datetime.utcnow().isoformat()
        }
        
        table.put_item(Item=batch_record)
        
        # Crear registros individuales para cada oficio
        for i, oficio in enumerate(validation_result.get('oficios', []), 1):
            oficio_record = {
                'batch_id': batch_id,
                'oficio_id': oficio['oficio_id'],
                'status': 'pending',
                'created_at': datetime.utcnow().isoformat(),
                'sequence_number': i,
                'page_count': oficio['page_count'],
                'original_pages': oficio['original_page_numbers'],
                's3_location': oficio['s3_key'],
                'document_type': oficio['estimated_document_type'],
                'ocr_status': 'queued',
                'crm_status': 'pending'
            }
            table.put_item(Item=oficio_record)
        
        logger.info(f"✅ Registros de tracking creados para batch {batch_id}")
        
    except Exception as e:
        logger.error(f"❌ Error creando registros de tracking: {str(e)}")

def save_successful_processing_log(batch_id: str, email_metadata: Dict[str, Any], validation_result: Dict[str, Any]):
    """
    Guarda log completo del procesamiento exitoso
    """
    try:
        processing_log = {
            'batch_id': batch_id,
            'processing_status': 'success',
            'timestamp': datetime.utcnow().isoformat(),
            'contacto': email_metadata.get('contact_email'),
            'empresa': email_metadata.get('empresa'),
            'cantidad_oficios_enviados': email_metadata.get('cantidad_oficios_declarada'),
            'cantidad_oficios_recibidos': validation_result.get('cantidad_extraida'),
            'fecha_creacion': datetime.utcnow().isoformat(),
            'origen': email_metadata.get('origen'),
            'observacion': f"Procesamiento exitoso desde {email_metadata.get('contact_email')}. {email_metadata.get('observaciones', '')}".strip(),
            'validation_status': validation_result.get('validation_status'),
            'email_subject': email_metadata.get('email_subject'),
            'email_date': email_metadata.get('email_date'),
            's3_location': email_metadata.get('email_s3_location'),
            'contact_source': 'from_header'
        }
        
        log_key = f"logs/successful/{batch_id}/processing_log.json"
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=log_key,
            Body=json.dumps(processing_log, ensure_ascii=False, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"📝 Log de éxito guardado: {log_key}")
        
    except Exception as e:
        logger.error(f"❌ Error guardando log de éxito: {str(e)}")

def save_failed_processing_log(batch_id: str, email_metadata: Dict[str, Any], validation_result: Dict[str, Any]):
    """
    Guarda log de procesamiento fallido
    """
    try:
        processing_log = {
            'batch_id': batch_id,
            'processing_status': 'failed',
            'timestamp': datetime.utcnow().isoformat(),
            'contacto': email_metadata.get('contact_email'),
            'empresa': email_metadata.get('empresa'),
            'cantidad_oficios_enviados': email_metadata.get('cantidad_oficios_declarada'),
            'cantidad_oficios_recibidos': validation_result.get('cantidad_extraida', 0),
            'fecha_creacion': datetime.utcnow().isoformat(),
            'origen': email_metadata.get('origen'),
            'observacion': f"Error en validación: {validation_result.get('error', 'Error desconocido')}",
            'error_type': validation_result.get('validation_status'),
            'error_message': validation_result.get('error'),
            'diferencia': validation_result.get('diferencia', 0)
        }
        
        log_key = f"logs/failed/{batch_id}/processing_log.json"
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=log_key,
            Body=json.dumps(processing_log, ensure_ascii=False, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"📝 Log de error guardado: {log_key}")
        
    except Exception as e:
        logger.error(f"❌ Error guardando log de error: {str(e)}")

def save_notification_for_later(recipient: str, subject: str, message: str):
    """
    Guarda notificación que no se pudo enviar para reintento posterior
    """
    try:
        failed_notification = {
            'recipient': recipient,
            'subject': subject,
            'message': message,
            'timestamp': datetime.utcnow().isoformat(),
            'reason': 'SES_not_configured_or_failed'
        }
        
        notification_key = f"notifications/pending/{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{recipient.replace('@', '_at_')}.json"
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=notification_key,
            Body=json.dumps(failed_notification, ensure_ascii=False, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"📧 Notificación guardada para envío posterior: {notification_key}")
        
    except Exception as e:
        logger.error(f"❌ Error guardando notificación pendiente: {str(e)}")


def create_html_email_template(template_type: str, **kwargs) -> str:
    """
    Crea templates HTML corporativos para diferentes tipos de email
    """
    base_style = """
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            line-height: 1.6; 
            color: #333333; 
            margin: 0; 
            padding: 0; 
            background-color: #f5f5f5;
        }
        .container { 
            max-width: 600px; 
            margin: 20px auto; 
            background-color: #ffffff;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header { 
            background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
            color: white; 
            padding: 30px 40px; 
            text-align: center;
        }
        .header h1 { 
            margin: 0; 
            font-size: 24px; 
            font-weight: 300;
        }
        .content { 
            padding: 40px; 
            margin-top: -50px;
        }
        .alert-error { 
            background-color: #f8d7da; 
            border: 1px solid #f5c6cb; 
            color: #721c24; 
            padding: 20px; 
            border-radius: 6px; 
            margin: 20px 0;
            border-left: 4px solid #dc3545;
        }
        .alert-success { 
            background-color: #d4edda; 
            border: 1px solid #c3e6cb; 
            color: #155724; 
            padding: 20px; 
            border-radius: 6px; 
            margin: 20px 0;
            border-left: 4px solid #28a745;
        }
        .alert-info { 
            background-color: #cce7ff; 
            border: 1px solid #b8daff; 
            color: #004085; 
            padding: 20px; 
            border-radius: 6px; 
            margin: 20px 0;
            border-left: 4px solid #007bff;
        }
        .details-table { 
            width: 100%; 
            border-collapse: collapse; 
            margin: 20px 0; 
            background-color: #f8f9fa;
            border-radius: 6px;
            overflow: hidden;
        }
        .details-table th, .details-table td { 
            padding: 12px 16px; 
            text-align: left; 
            border-bottom: 1px solid #dee2e6;
        }
        .details-table th { 
            background-color: #e9ecef; 
            font-weight: 600;
            color: #495057;
        }
        .action-steps { 
            background-color: #f8f9fa; 
            padding: 25px; 
            border-radius: 6px; 
            margin: 20px 0;
            border-left: 4px solid #ffc107;
        }
        .action-steps h3 { 
            color: #856404; 
            margin-top: 0;
            font-size: 18px;
        }
        .action-steps ol { 
            margin: 15px 0; 
            padding-left: 20px;
        }
        .action-steps li { 
            margin: 8px 0; 
        }
        .footer { 
            background-color: #f8f9fa; 
            padding: 30px 40px; 
            text-align: center; 
            border-top: 1px solid #dee2e6;
        }
        .footer p { 
            margin: 5px 0; 
            color: #6c757d; 
            font-size: 14px;
        }
        .company-logo { 
            font-size: 28px; 
            font-weight: bold; 
            color: #00171F; 
            margin-bottom: 5px;
        }
        .badge { 
            display: inline-block; 
            padding: 6px 12px; 
            border-radius: 20px; 
            font-size: 12px; 
            font-weight: 600; 
            text-transform: uppercase;
        }
        .badge-error { 
            background-color: #dc3545; 
            color: white; 
        }
        .badge-success { 
            background-color: #28a745; 
            color: white; 
        }
        .badge-info { 
            background-color: #17a2b8; 
            color: white; 
        }
        .highlight { 
            background-color: #fff3cd; 
            padding: 2px 6px; 
            border-radius: 3px; 
            font-weight: 600;
        }
    </style>
    """
    
    if template_type == "validation_error":
        return create_validation_error_template(base_style, **kwargs)
    elif template_type == "success":
        return create_success_template(base_style, **kwargs)
    elif template_type == "general_error":
        return create_general_error_template(base_style, **kwargs)
    
    return ""

def create_validation_error_template(base_style: str, email_metadata: Dict[str, Any], validation_result: Dict[str, Any]) -> str:
    """
    Template HTML para errores de validación
    """
    empresa = email_metadata.get('empresa', 'Cliente')
    cantidad_declarada = validation_result.get('cantidad_declarada', 0)
    cantidad_encontrada = validation_result.get('cantidad_extraida', 0)
    diferencia = abs(cantidad_declarada - cantidad_encontrada)
    error_message = validation_result.get('error', 'Error desconocido')
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Error en Procesamiento de Lote</title>
        {base_style}
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="company-logo">CIBERNÉTICA</div>
                <h1 style="color: #00171F;">Sistema de Procesamiento de Oficios</h1>
            </div>
            
            <div class="content">
                <h2>Estimado cliente de <span class="highlight">{empresa}</span>,</h2>
                
                <p>Hemos procesado su solicitud de lote de oficios, sin embargo, hemos detectado una discrepancia que requiere su atención.</p>
                
                <div class="alert-error">
                    <strong><span class="badge badge-error">Error Detectado</span></strong>
                    <p style="margin: 10px 0 0 0;">{error_message}</p>
                </div>
                
                <h3>📊 Resumen de Procesamiento</h3>
                <table class="details-table">
                    <tr>
                        <th>Concepto</th>
                        <th>Valor</th>
                    </tr>
                    <tr>
                        <td>Cantidad declarada en email</td>
                        <td><strong>{cantidad_declarada} oficios</strong></td>
                    </tr>
                    <tr>
                        <td>Cantidad encontrada en PDF</td>
                        <td><strong>{cantidad_encontrada} oficios</strong></td>
                    </tr>
                    <tr>
                        <td>Diferencia</td>
                        <td><strong style="color: #dc3545;">{diferencia} oficios</strong></td>
                    </tr>
                    <tr>
                        <td>Empresa</td>
                        <td>{empresa}</td>
                    </tr>
                    <tr>
                        <td>Origen</td>
                        <td>{email_metadata.get('origen', 'No especificado')}</td>
                    </tr>
                </table>
                
                <div class="action-steps">
                    <h3>🔧 Acción Requerida</h3>
                    <p>Para resolver este problema, por favor verifique los siguientes puntos:</p>
                    <ol>
                        <li><strong>Cantidad declarada:</strong> Confirme que el número de oficios en el email sea correcto</li>
                        <li><strong>Contenido del PDF:</strong> Verifique que todos los oficios estén incluidos en el archivo</li>
                        <li><strong>Separadores:</strong> Asegúrese de que los separadores estén colocados correctamente entre cada oficio</li>
                        <li><strong>Formato:</strong> Confirme que el PDF esté organizado según nuestras especificaciones</li>
                    </ol>
                </div>
                
                <div class="alert-info">
                    <strong>💡 Próximos Pasos</strong>
                    <p>Una vez realizadas las correcciones, puede reenviar el lote usando el mismo formato de email. Si tiene dudas sobre el proceso, no dude en contactarnos respondiendo a este email.</p>
                </div>
            </div>
            
            <div class="footer">
                <p><strong>Sistema de Procesamiento Automático</strong></p>
                <p>Cibernética - Soluciones Tecnológicas</p>
                <p>📧 Para soporte técnico, responda a este email</p>
                <p style="color: #9ca3af; font-size: 12px;">Este es un email automático del sistema de procesamiento de oficios legales.</p>
            </div>
        </div>
    </body>
    </html>
    """

def create_success_template(base_style: str, email_metadata: Dict[str, Any], total_oficios: int, batch_id: str, validation_status: str = 'exact_match') -> str:
    """
    Template HTML para notificaciones de éxito
    """
    empresa = email_metadata.get('empresa', 'Cliente')
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lote Procesado Exitosamente</title>
        {base_style}
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="company-logo">CIBERNÉTICA</div>
                <h1 style="color: #00171F;">Sistema de Procesamiento de Oficios</h1>
            </div>
            
            <div class="content">
                <h2>Estimado cliente de <span class="highlight">{empresa}</span>,</h2>
                
                <div class="alert-success">
                    <strong><span class="badge badge-success">Procesamiento Exitoso</span></strong>
                    <p style="margin: 10px 0 0 0;">Su lote de oficios ha sido procesado correctamente y está siendo analizado por nuestro sistema OCR.</p>
                </div>
                

                
                <h3>📊 Resumen del Procesamiento</h3>
                <table class="details-table">
                    <tr>
                        <th>Concepto</th>
                        <th>Valor</th>
                    </tr>
                    <tr>
                        <td>ID del Lote</td>
                        <td><code style="background: #f8f9fa; padding: 2px 6px; border-radius: 3px; font-family: monospace;">{batch_id}</code></td>
                    </tr>
                    <tr>
                        <td>Oficios procesados</td>
                        <td><strong style="color: #28a745;">{total_oficios} oficios</strong></td>
                    </tr>
                    <tr>
                        <td>Cantidad declarada</td>
                        <td>{email_metadata.get('cantidad_oficios_declarada', 'No especificada')}</td>
                    </tr>
                    <tr>
                        <td>Empresa</td>
                        <td>{empresa}</td>
                    </tr>
                    <tr>
                        <td>Origen</td>
                        <td>{email_metadata.get('origen', 'No especificado')}</td>
                    </tr>
                    <tr>
                        <td>Fecha de procesamiento</td>
                        <td>{datetime.utcnow().strftime('%d/%m/%Y a las %H:%M')} UTC</td>
                    </tr>
                </table>
                
                <div class="alert-info">
                    <strong>⚡ Estado Actual</strong>
                    <p>Todos los oficios están siendo procesados por nuestro sistema OCR de última generación y serán integrados automáticamente al CRM una vez completado el análisis.</p>
                </div>
                
                <div class="action-steps" style="border-left-color: #28a745;">
                    <h3 style="color: #155724;">📬 Próximas Notificaciones</h3>
                    <p>Recibirá notificaciones adicionales cuando:</p>
                    <ol>
                        <li>El procesamiento OCR esté completado</li>
                        <li>Los datos sean integrados al sistema CRM</li>
                        <li>El lote esté completamente finalizado</li>
                    </ol>
                </div>
            </div>
            
            <div class="footer">
                <p><strong>Sistema de Procesamiento Automático</strong></p>
                <p>Cibernética - Soluciones Tecnológicas</p>
                <p>📧 Para consultas, responda a este email</p>
                <p style="color: #9ca3af; font-size: 12px;">Este es un email automático del sistema de procesamiento de oficios legales.</p>
            </div>
        </div>
    </body>
    </html>
    """

def create_general_error_template(base_style: str, subject: str, message: str) -> str:
    """
    Template HTML para errores generales
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Error en Procesamiento</title>
        {base_style}
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="company-logo">CIBERNÉTICA</div>
                <h1 style="color: #00171F;">Sistema de Procesamiento de Oficios</h1>
            </div>
            
            <div class="content">
                <h2>Estimado cliente,</h2>
                
                <div class="alert-error">
                    <strong><span class="badge badge-error">Error de Procesamiento</span></strong>
                    <p style="margin: 10px 0 0 0;">{subject}</p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 6px; margin: 20px 0;">
                    <h3 style="color: #495057; margin-top: 0;">Detalles del Error</h3>
                    <p>{message}</p>
                </div>
                
                <div class="action-steps">
                    <h3>🔧 Cómo Proceder</h3>
                    <ol>
                        <li>Revise el formato de su envío según nuestras especificaciones</li>
                        <li>Verifique que el archivo PDF esté correctamente estructurado</li>
                        <li>Reintente el envío con las correcciones necesarias</li>
                        <li>Si el problema persiste, contacte a nuestro soporte técnico</li>
                    </ol>
                </div>
                
                <div class="alert-info">
                    <strong>💬 Soporte Técnico</strong>
                    <p>Nuestro equipo está disponible para ayudarle. Responda a este email con sus consultas y le brindaremos asistencia personalizada.</p>
                </div>
            </div>
            
            <div class="footer">
                <p><strong>Sistema de Procesamiento Automático</strong></p>
                <p>Cibernética - Soluciones Tecnológicas</p>
                <p>📧 Soporte: Responda a este email</p>
                <p style="color: #9ca3af; font-size: 12px;">Este es un email automático del sistema de procesamiento de oficios legales.</p>
            </div>
        </div>
    </body>
    </html>
    """

# Funciones de notificación (con manejo de errores SES mejorado)
def send_success_notification(email_metadata: Dict[str, Any], total_oficios: int, batch_id: str, validation_status: str = 'exact_match'):
    """
    Envía notificación de éxito con HTML
    """
    try:
        recipient = email_metadata.get('contact_email')
        empresa = email_metadata.get('empresa', 'Cliente')
        
        subject = f"Lote Procesado Exitosamente - {empresa}"
        
        # Crear contenido HTML
        html_body = create_html_email_template('success', 
                                             email_metadata=email_metadata, 
                                             total_oficios=total_oficios, 
                                             batch_id=batch_id,
                                             validation_status=validation_status)
        
        # Versión texto simple
        text_body = f"""
Estimado cliente de {empresa},

Su lote de oficios ha sido procesado exitosamente.

RESUMEN:
- Lote ID: {batch_id}
- Oficios procesados: {total_oficios}
- Cantidad declarada: {email_metadata.get('cantidad_oficios_declarada')}
- Origen: {email_metadata.get('origen')}

Los oficios están siendo procesados por OCR y serán integrados al CRM.

Saludos cordiales,
Sistema de Procesamiento Automático - Cibernética
        """
        
        send_html_email_notification(recipient, subject, html_body, text_body)
        
    except Exception as e:
        logger.error(f"❌ Error enviando notificación de éxito: {str(e)}")


def send_validation_error_notification(email_metadata: Dict[str, Any], validation_result: Dict[str, Any]):
    """
    Envía notificación de error de validación con HTML
    """
    try:
        recipient = email_metadata.get('contact_email')
        empresa = email_metadata.get('empresa', 'Cliente')
        
        subject = f"Error en Procesamiento de Lote - {empresa}"
        
        # Crear contenido HTML
        html_body = create_html_email_template('validation_error', 
                                             email_metadata=email_metadata, 
                                             validation_result=validation_result)
        
        # Crear versión texto simple como fallback
        cantidad_declarada = validation_result.get('cantidad_declarada', 0)
        cantidad_encontrada = validation_result.get('cantidad_extraida', 0)
        error_message = validation_result.get('error', 'Error desconocido')
        
        text_body = f"""
Estimado cliente de {empresa},

PROBLEMA DETECTADO: {error_message}

DETALLES:
- Cantidad declarada: {cantidad_declarada} oficios
- Cantidad encontrada: {cantidad_encontrada} oficios
- Diferencia: {abs(cantidad_declarada - cantidad_encontrada)} oficios

ACCIÓN REQUERIDA:
1. Verifique que la cantidad declarada sea correcta
2. Confirme que todos los oficios estén en el PDF
3. Revise los separadores entre oficios

Puede reenviar el lote una vez corregido.

Saludos cordiales,
Sistema de Procesamiento Automático - Cibernética
        """
        
        send_html_email_notification(recipient, subject, html_body, text_body)
        
    except Exception as e:
        logger.error(f"❌ Error enviando notificación de error: {str(e)}")

def send_error_notification(recipient: str, subject: str, message: str):
    """
    Envía notificación de error general con HTML
    """
    try:
        full_subject = f"Error en Procesamiento - {subject}"
        
        # Crear contenido HTML
        html_body = create_html_email_template('general_error', 
                                             subject=subject, 
                                             message=message)
        
        # Versión texto simple
        text_body = f"""
Estimado cliente,

Ha ocurrido un error durante el procesamiento:

{message}

Por favor revise el formato de su envío y reintente, o contacte soporte si persiste.

Saludos cordiales,
Sistema de Procesamiento Automático - Cibernética
        """
        
        send_html_email_notification(recipient, full_subject, html_body, text_body)
        
    except Exception as e:
        logger.error(f"❌ Error enviando notificación de error general: {str(e)}")

def send_html_email_notification(recipient: str, subject: str, html_body: str, text_body: str):
    """
    Envía email HTML con fallback a texto plano
    """
    try:
        # Verificar configuración SES
        if not SES_FROM_EMAIL or SES_FROM_EMAIL == 'notify@softwarefactory.cibernetica.xyz':
            logger.warning("⚠️ SES_FROM_EMAIL no está configurado correctamente")
            raise Exception("SES_FROM_EMAIL not properly configured")
        
        # Crear mensaje multipart
        message = MIMEMultipart('alternative')
        message['From'] = SES_FROM_EMAIL
        message['To'] = recipient
        message['Subject'] = subject
        
        # Agregar versión texto plano
        text_part = MIMEText(text_body, 'plain', 'utf-8')
        message.attach(text_part)
        
        # Agregar versión HTML
        html_part = MIMEText(html_body, 'html', 'utf-8')
        message.attach(html_part)
        
        # Enviar usando SES
        response = ses_client.send_raw_email(
            Source=SES_FROM_EMAIL,
            Destinations=[recipient],
            RawMessage={'Data': message.as_string()}
        )
        
        logger.info(f"📧 Email HTML enviado a {recipient}: {response['MessageId']}")
        
    except Exception as e:
        logger.error(f"❌ Error enviando email HTML a {recipient}: {str(e)}")
        # Guardar para reintento
        save_notification_for_later(recipient, subject, f"HTML: {html_body[:200]}...")

#def send_email_notification(recipient: str, subject: str, body: str):
#    """
#    Envía email usando SES con manejo mejorado de errores
#    """
#    try:
#        # Verificar que SES está configurado
#        if not SES_FROM_EMAIL or SES_FROM_EMAIL == 'notify@softwarefactory.cibernetica.xyz':
#            logger.warning("⚠️ SES_FROM_EMAIL no está configurado correctamente")
#            raise Exception("SES_FROM_EMAIL not properly configured")
        
#        message = MIMEMultipart()
#        message['From'] = SES_FROM_EMAIL
#        message['To'] = recipient
#        message['Subject'] = subject
        
#        message.attach(MIMEText(body, 'plain', 'utf-8'))
        
#        response = ses_client.send_raw_email(
#            Source=SES_FROM_EMAIL,
#            Destinations=[recipient],
#            RawMessage={'Data': message.as_string()}
#        )
        
#        logger.info(f"📧 Notificación enviada a {recipient}: {response['MessageId']}")
        
#    except Exception as e:
#        logger.error(f"❌ Error enviando email a {recipient}: {str(e)}")
        
#        # Guardar notificación fallida para reintento manual
#        save_notification_for_later(recipient, subject, body)