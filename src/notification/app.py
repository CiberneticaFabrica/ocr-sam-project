# src/notification/app.py
import json
import boto3
import logging
import os
from datetime import datetime
from typing import Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuración de logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Clientes AWS
ses_client = boto3.client('ses')
s3_client = boto3.client('s3')

# Variables de entorno
SES_FROM_EMAIL = os.environ.get('SES_FROM_EMAIL', 'noreply@cibernetica.com')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Maneja notificaciones por email y reintentos de notificaciones fallidas
    """
    try:
        logger.info(f"📧 Notification event received: {json.dumps(event, default=str)}")
        
        # Procesar mensajes de SNS
        for record in event.get('Records', []):
            if record.get('EventSource') == 'aws:sns':
                process_sns_notification(record)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Notifications processed successfully'})
        }
        
    except Exception as e:
        logger.error(f"❌ Error en notification handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def process_sns_notification(record: Dict[str, Any]):
    """
    Procesa notificación de SNS
    """
    try:
        sns_message = json.loads(record['Sns']['Message'])
        notification_type = sns_message.get('type', 'general')
        
        if notification_type == 'email_notification':
            send_email_notification(
                sns_message.get('recipient'),
                sns_message.get('subject'),
                sns_message.get('body')
            )
        elif notification_type == 'alarm':
            handle_alarm_notification(sns_message)
        else:
            logger.info(f"📧 Tipo de notificación no manejado: {notification_type}")
        
    except Exception as e:
        logger.error(f"❌ Error procesando notificación SNS: {str(e)}")

def send_email_notification(recipient: str, subject: str, body: str):
    """
    Envía notificación por email usando SES
    """
    try:
        if not recipient or not subject or not body:
            logger.warning("⚠️ Datos incompletos para envío de email")
            return
        
        # Crear mensaje
        message = MIMEMultipart()
        message['From'] = SES_FROM_EMAIL
        message['To'] = recipient
        message['Subject'] = subject
        
        # Agregar cuerpo
        message.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Enviar usando SES
        response = ses_client.send_raw_email(
            Source=SES_FROM_EMAIL,
            Destinations=[recipient],
            RawMessage={'Data': message.as_string()}
        )
        
        logger.info(f"✅ Email enviado a {recipient}: {response['MessageId']}")
        
    except Exception as e:
        logger.error(f"❌ Error enviando email: {str(e)}")
        # Guardar para reintento
        save_failed_notification(recipient, subject, body, str(e))

def handle_alarm_notification(alarm_data: Dict[str, Any]):
    """
    Maneja notificaciones de alarmas de CloudWatch
    """
    try:
        alarm_name = alarm_data.get('AlarmName', 'Unknown')
        alarm_reason = alarm_data.get('NewStateReason', 'No reason provided')
        
        logger.info(f"🚨 Alarma activada: {alarm_name} - {alarm_reason}")
        
        # Aquí puedes agregar lógica adicional para manejar alarmas
        # Por ejemplo, enviar notificaciones a Slack, Teams, etc.
        
    except Exception as e:
        logger.error(f"❌ Error manejando alarma: {str(e)}")

def save_failed_notification(recipient: str, subject: str, body: str, error: str):
    """
    Guarda notificación fallida para reintento posterior
    """
    try:
        failed_notification = {
            'recipient': recipient,
            'subject': subject,
            'body': body,
            'error': error,
            'timestamp': datetime.utcnow().isoformat(),
            'retry_count': 0
        }
        
        # Guardar en S3 para reintento manual o automático
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        key = f"notifications/failed/{timestamp}_{recipient.replace('@', '_at_')}.json"
        
        # Nota: Necesitarías agregar permisos de S3 y variable de entorno para el bucket
        # s3_client.put_object(
        #     Bucket='tu-bucket',
        #     Key=key,
        #     Body=json.dumps(failed_notification, ensure_ascii=False, indent=2),
        #     ContentType='application/json'
        # )
        
        logger.info(f"💾 Notificación fallida guardada: {key}")
        
    except Exception as e:
        logger.error(f"❌ Error guardando notificación fallida: {str(e)}")

