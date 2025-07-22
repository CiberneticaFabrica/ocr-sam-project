# OCR SAM Project - Sistema de Procesamiento Automático de Oficios

## 📋 Descripción

Sistema automatizado para procesamiento de oficios legales mediante OCR, desarrollado con AWS SAM (Serverless Application Model). El sistema recibe emails con PDFs adjuntos, separa automáticamente los oficios individuales, procesa el texto mediante OCR y integra los datos al CRM.

## 🏗️ Arquitectura

### Componentes Principales

- **Email Processor**: Procesa emails entrantes y separa PDFs en oficios individuales
- **OCR Processor**: Extrae texto de los PDFs mediante reconocimiento óptico de caracteres
- **CRM Integrator**: Integra los datos procesados al sistema CRM
- **Notification System**: Envía notificaciones por email sobre el estado del procesamiento
- **Status Tracker**: Rastrea el estado de cada oficio en el sistema
- **Batch Status**: Gestiona el estado de lotes completos de oficios

### Servicios AWS Utilizados

- **AWS Lambda**: Funciones serverless para procesamiento
- **Amazon S3**: Almacenamiento de PDFs y logs
- **Amazon SQS**: Colas de mensajes para procesamiento asíncrono
- **Amazon SES**: Envío de notificaciones por email
- **Amazon DynamoDB**: Base de datos para tracking de estado
- **Amazon CloudWatch**: Monitoreo y logging

## 🚀 Instalación

### Prerrequisitos

- AWS CLI configurado
- AWS SAM CLI instalado
- Python 3.8+
- Git

### Pasos de Instalación

1. **Clonar el repositorio**
   ```bash
   git clone <repository-url>
   cd ocr-sam-project
   ```

2. **Instalar dependencias**
   ```bash
   # Para cada función Lambda
   cd src/email_processor
   pip install -r requirements.txt -t .
   
   cd ../processor
   pip install -r requirements.txt -t .
   
   cd ../crm_integrator
   pip install -r requirements.txt -t .
   
   # ... repetir para otras funciones
   ```

3. **Configurar variables de entorno**
   ```bash
   # Crear archivo samconfig.toml con tus configuraciones
   sam deploy --guided
   ```

4. **Desplegar la aplicación**
   ```bash
   sam build
   sam deploy
   ```

## 📧 Uso del Sistema

### Envío de Emails

Para procesar oficios, envía un email con el siguiente formato:

**Asunto**: Cualquier asunto
**Cuerpo**:
```
cantidad_oficios: 5
empresa: Banco General
origen: Panamá
observaciones: Oficios urgentes del mes de enero

[Adjuntar PDF con los oficios]
```

**Adjunto**: Archivo PDF con los oficios a procesar

### Formato del PDF

- **Separadores explícitos**: Páginas con texto como "SEPARADOR DE OFICIOS"
- **Separación automática**: El sistema detecta inicios de documentos automáticamente
- **Múltiples oficios**: Un PDF puede contener varios oficios

## 🔧 Configuración

### Variables de Entorno Requeridas

```yaml
S3_BUCKET_NAME: "nombre-del-bucket-s3"
OCR_QUEUE_URL: "url-de-la-cola-ocr"
TRACKING_TABLE: "nombre-tabla-dynamodb"
SES_FROM_EMAIL: "notificaciones@tuempresa.com"
```

### Configuración de SES

1. Verificar dominio en SES
2. Configurar reglas de recepción de emails
3. Configurar permisos IAM para las funciones Lambda

## 📊 Monitoreo

### CloudWatch Logs

Cada función Lambda genera logs detallados en CloudWatch:

- **Email Processor**: Logs de procesamiento de emails
- **OCR Processor**: Logs de extracción de texto
- **CRM Integrator**: Logs de integración al CRM

### Métricas Disponibles

- Número de emails procesados
- Tiempo de procesamiento por oficio
- Tasa de éxito de OCR
- Errores de validación

## 🧪 Testing

### Tests Unitarios

```bash
# Ejecutar tests unitarios
python -m pytest tests/unit/

# Ejecutar tests de integración
python -m pytest tests/integration/
```

### Tests Manuales

1. Enviar email de prueba con PDF adjunto
2. Verificar procesamiento en CloudWatch Logs
3. Confirmar integración al CRM

## 🔒 Seguridad

### Permisos IAM

El sistema utiliza roles IAM con permisos mínimos necesarios:

- **S3**: Lectura/escritura en bucket específico
- **SQS**: Envío/recepción de mensajes
- **SES**: Envío de emails
- **DynamoDB**: Lectura/escritura en tabla de tracking

### Encriptación

- Datos en tránsito: TLS/SSL
- Datos en reposo: Encriptación AES-256 en S3

## 📈 Escalabilidad

El sistema está diseñado para escalar automáticamente:

- **Lambda**: Escala automáticamente según demanda
- **SQS**: Maneja picos de tráfico con colas de mensajes
- **S3**: Almacenamiento ilimitado para PDFs

## 🐛 Troubleshooting

### Problemas Comunes

1. **Email no procesado**
   - Verificar formato del email
   - Confirmar que el PDF esté adjunto
   - Revisar logs de CloudWatch

2. **Error de validación**
   - Verificar cantidad declarada vs. cantidad encontrada
   - Revisar formato del PDF
   - Confirmar separadores entre oficios

3. **Error de OCR**
   - Verificar calidad del PDF
   - Confirmar que el texto sea legible
   - Revisar logs de la función OCR

### Logs de Debug

Para habilitar logs detallados, configurar:

```bash
export LOG_LEVEL=DEBUG
```

## 🤝 Contribución

1. Fork el proyecto
2. Crear rama para feature (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles.

## 📞 Soporte

Para soporte técnico o consultas:

- **Email**: soporte@cibernetica.net
- **Documentación**: [Link a documentación]
- **Issues**: [GitHub Issues]

## 🔄 Changelog

### v1.0.0
- Implementación inicial del sistema
- Procesamiento de emails con PDFs
- Separación automática de oficios
- Integración OCR básica
- Sistema de notificaciones

---

**Desarrollado por Cibernética - Soluciones Tecnológicas** 