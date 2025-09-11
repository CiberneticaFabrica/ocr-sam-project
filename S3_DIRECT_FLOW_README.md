# 📁 FLUJO S3 DIRECTO - SISTEMA OCR SAM

## 🎯 DESCRIPCIÓN

El **Flujo S3 Directo** es una nueva funcionalidad que permite a los proveedores depositar documentos PDF directamente en una carpeta S3, iniciando automáticamente el proceso de OCR y integración con CRM, sin necesidad de enviar emails.

## 🚀 BENEFICIOS

### ✅ **AUTOMATIZACIÓN COMPLETA**
- Procesamiento automático al depositar archivos
- Sin intervención manual requerida
- Flujo end-to-end automatizado

### 🔄 **COMPATIBILIDAD TOTAL**
- Mantiene el flujo de email existente
- No afecta funcionalidades actuales
- Ambos flujos funcionan en paralelo

### 📈 **ESCALABILIDAD**
- Procesa múltiples documentos simultáneamente
- Escala automáticamente según demanda
- Sin límites de concurrencia

### 🎯 **FLEXIBILIDAD**
- Ideal para integraciones con sistemas externos
- API-first approach para proveedores
- Configuración simple y directa

## 🔄 FLUJO DE PROCESAMIENTO

### 📋 **PASO 1: DEPÓSITO DEL DOCUMENTO**
```
Proveedor → S3 Bucket → Carpeta incoming/ → Trigger Lambda
```

**📁 Ubicación S3:**
```
s3://ocr-legal-documents-dev/incoming/
```

**📄 Formato Aceptado:**
- Solo archivos PDF
- Tamaño máximo: 50MB
- Nombre descriptivo recomendado
- **Primera página debe contener configuración del lote**

### 📋 **PÁGINA DE CONFIGURACIÓN REQUERIDA**

La primera página del PDF debe incluir las siguientes variables:

```
┌─────────────────────────────────────────────────────────┐
│                    CONFIGURACIÓN DE LOTE                │
│                                                         │
│ cantidad_oficios: 50                                    │
│ empresa: Banco Global                                   │
│ origen: Chitre                                          │
│ observaciones: Oficios urgentes                         │
│                                                         │
│ Fecha: 2025-01-03                                       │
│ Operador: edwinpeñalba                                  │
└─────────────────────────────────────────────────────────┘
```

**✅ Campos Obligatorios:**
- `cantidad_oficios`: Número de oficios en el lote
- `empresa`: Nombre de la empresa

**📝 Campos Opcionales:**
- `origen`: Ubicación de origen
- `observaciones`: Comentarios adicionales
- `operador`: Nombre del operador (se extrae del filename si no se especifica)

**📋 Ver documentación completa:** [S3_CONFIG_PAGE_EXAMPLE.md](S3_CONFIG_PAGE_EXAMPLE.md)

### 📋 **PASO 2: PROCESAMIENTO AUTOMÁTICO**
```
S3DocumentProcessor → PDF Download → Config Extraction → Validation → PDF Split → Oficios Individuales
```

**🔍 Validaciones Realizadas:**
1. **Extracción de Configuración**: Lee primera página del PDF
2. **Validación de Campos**: Verifica campos obligatorios
3. **Validación de Cantidad**: Compara declarado vs extraído
4. **Notificación de Errores**: Envía alertas si falla validación

**🔧 Funciones:**
- Descarga PDF desde S3
- Divide PDF en oficios (por página)
- Crea lote automáticamente
- Genera IDs únicos para tracking

### 📋 **PASO 3: ENVÍO A PROCESAMIENTO**
```
SQS Queue → Processor Lambda → Mistral AI → OCR Results
```

**🔍 Proceso OCR:**
- Extracción de texto del PDF
- Análisis con IA (Mistral)
- Estructuración de datos
- Almacenamiento de resultados

### 📋 **PASO 4: INTEGRACIÓN CRM**
```
CRM Queue → CRM Integrator → Creatio → DynamoDB Update
```

**🏢 Integración:**
- Creación automática de casos
- Registro de personas involucradas
- Actualización de estado en tiempo real

## 🏗️ ARQUITECTURA TÉCNICA

### 🔧 **NUEVA LAMBDA: S3DocumentProcessor**

**Archivo:** `src/s3_document_processor/app.py`
**Trigger:** S3 Object Created (carpeta `incoming/`)
**Memoria:** 2048 MB
**Timeout:** 600 segundos

**📋 Funciones Principales:**
```python
def process_s3_event(record)           # Procesa eventos S3
def process_pdf_from_s3(bucket, key)   # Descarga y procesa PDF
def split_pdf_into_oficios(content)    # Divide PDF en oficios
def create_batch_tracking_record()      # Crea registros DynamoDB
def send_oficios_to_processing_queue() # Envía a cola SQS
```

### 🔄 **PROCESSOR ACTUALIZADO**

**Archivo:** `src/processor/app.py`
**Cambios:** Soporte para documentos S3 directo

**🔍 Detección Automática:**
```python
# Determina tipo de procesamiento
if 'oficio_data' in message_body or 's3_key' in message_body:
    # Procesamiento de oficio individual (email o S3)
    result = process_batch_oficio_job(message_body, context)
else:
    # Job individual tradicional
    result = process_individual_ocr_job(job_id, context)
```

### 📊 **TRACKING MEJORADO**

**Nuevo Campo:** `source` en DynamoDB
- `"email"` - Documentos procesados por email
- `"s3_direct"` - Documentos depositados directamente en S3

**📈 Estadísticas por Fuente:**
- Procesamiento por origen
- Tiempos de procesamiento
- Tasa de éxito por flujo

## 🗄️ ESTRUCTURA DE DATOS

### 📦 **ESTRUCTURA S3 ACTUALIZADA**

```
ocr-legal-documents-dev/
├── incoming/                    # ← NUEVA CARPETA
│   ├── documento_001.pdf       # ← PDF depositado por proveedor
│   ├── documento_002.pdf       # ← PDF depositado por proveedor
│   └── ...
├── emails/                      # ← MANTENER (flujo email existente)
│   └── {email_id}/
├── oficios/
│   └── lotes/
│       └── {batch_id}/
│           ├── {batch_id}_oficio_001.pdf
│           ├── {batch_id}_oficio_002.pdf
│           └── ...
└── jobs/
    └── {job_id}/
        ├── input.json
        └── result.json
```

### 🗃️ **SCHEMA DYNAMODB ACTUALIZADO**

```json
{
  "batch_id": "string (Partition Key)",
  "oficio_id": "string (Sort Key)",
  "status": "pending|processing|completed|error",
  "ocr_status": "pending|processing|completed|error",
  "crm_status": "pending|processing|completed|error",
  "sequence_number": "number",
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp",
  "completed_at": "ISO timestamp",
  "crm_id": "string",
  "crm_details": "string",
  "error_message": "string",
  "source": "email|s3_direct"  // ← NUEVO CAMPO
}
```

## 🚀 IMPLEMENTACIÓN

### 📋 **PASO 1: DESPLIEGUE DE INFRAESTRUCTURA**

```bash
# Desplegar stack actualizado
sam build
sam deploy --guided
```

**✅ Recursos Creados:**
- Nueva Lambda: `S3DocumentProcessor`
- Trigger S3 para carpeta `incoming/`
- Permisos IAM actualizados

### 📋 **PASO 2: CONFIGURACIÓN DEL PROVEEDOR**

**🔑 Permisos S3:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl"
      ],
      "Resource": "arn:aws:s3:::ocr-legal-documents-dev/incoming/*"
    }
  ]
}
```

**📁 Carpeta de Destino:**
```
s3://ocr-legal-documents-dev/incoming/
```

### 📋 **PASO 3: TESTING Y VALIDACIÓN**

**🧪 Probar Flujo:**
1. Depositar PDF en carpeta `incoming/`
2. Verificar trigger de lambda
3. Monitorear procesamiento en CloudWatch
4. Verificar resultados en DynamoDB
5. Consultar estado via API

## 📊 MONITOREO Y CONSULTAS

### 🔍 **API ENDPOINTS**

**Estado del Lote:**
```bash
GET /batch/status/{batch_id}
```

**Estado del Oficio:**
```bash
GET /document/status/{job_id}
```

### 📈 **MÉTRICAS DISPONIBLES**

**Por Fuente:**
- Documentos procesados por email
- Documentos procesados por S3 directo
- Tiempo de procesamiento por flujo
- Tasa de éxito por origen

**Generales:**
- Total de documentos procesados
- Tiempo promedio de procesamiento
- Errores por tipo y fuente
- Estado de integración CRM

### 🚨 **ALERTAS Y NOTIFICACIONES**

**CloudWatch Alarms:**
- Errores de procesamiento
- Tiempo de procesamiento excesivo
- Fallos en integración CRM

**SNS Topics:**
- Notificaciones de completitud
- Alertas de errores críticos
- Resúmenes de procesamiento

## 🔧 CONFIGURACIÓN AVANZADA

### ⚙️ **VARIABLES DE ENTORNO**

```yaml
# S3DocumentProcessor
S3_BUCKET_NAME: ocr-legal-documents-dev
OCR_QUEUE_URL: https://sqs.us-east-1.amazonaws.com/...
TRACKING_TABLE: ocr-sam-project-dev-tracking
LOG_LEVEL: INFO
```

### 🔒 **PERMISOS IAM**

**S3DocumentProcessor:**
```json
{
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:PutObject",
    "s3:DeleteObject"
  ],
  "Resource": "arn:aws:s3:::ocr-legal-documents-dev/*"
}
```

**SQS:**
```json
{
  "Effect": "Allow",
  "Action": [
    "sqs:SendMessage"
  ],
  "Resource": "arn:aws:sqs:us-east-1:..."
}
```

**DynamoDB:**
```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:GetItem"
  ],
  "Resource": "arn:aws:dynamodb:us-east-1:..."
}
```

## 🧪 TESTING Y VALIDACIÓN

### 📋 **CASOS DE PRUEBA**

**✅ Caso Exitoso:**
1. Depositar PDF válido en `incoming/`
2. Verificar procesamiento automático
3. Confirmar creación de oficios
4. Validar integración CRM
5. Verificar tracking en DynamoDB

**❌ Casos de Error:**
1. Archivo no PDF
2. PDF corrupto o vacío
3. Error en división de páginas
4. Fallo en integración CRM
5. Timeout de lambda

### 🔍 **LOGS Y DEBUGGING**

**CloudWatch Logs:**
```
/aws/lambda/ocr-sam-project-dev-s3-document-processor
```

**Filtros Útiles:**
```
# Errores de procesamiento
ERROR

# Procesamiento exitoso
INFO

# Tiempo de procesamiento
Duration
```

## 📚 RECURSOS ADICIONALES

### 🔗 **DOCUMENTACIÓN RELACIONADA**

- [FLUJO_DETALLADO.md](./FLUJO_DETALLADO.md) - Flujo completo del sistema
- [DIAGRAMA_PROYECTO.md](./DIAGRAMA_PROYECTO.md) - Diagrama de arquitectura
- [README.md](./README.md) - Documentación principal del proyecto

### 🛠️ **HERRAMIENTAS DE DESARROLLO**

**SAM CLI:**
```bash
# Construir proyecto
sam build

# Desplegar
sam deploy

# Logs en tiempo real
sam logs -f S3DocumentProcessor --tail
```

**AWS CLI:**
```bash
# Verificar triggers S3
aws s3api get-bucket-notification-configuration --bucket ocr-legal-documents-dev

# Listar objetos en incoming
aws s3 ls s3://ocr-legal-documents-dev/incoming/
```

## 🚀 PRÓXIMOS PASOS

### 🔮 **MEJORAS FUTURAS**

1. **Detección Inteligente de Separadores**
   - IA para identificar fin de oficios
   - Mejor división que por página

2. **Validación de Contenido**
   - Verificación de formato de oficio
   - Validación de campos requeridos

3. **Notificaciones Avanzadas**
   - Webhooks para proveedores
   - Dashboard de estado en tiempo real

4. **Métricas Avanzadas**
   - Análisis de rendimiento
   - Predicción de tiempos de procesamiento

### 📋 **ROADMAP**

**Fase 1 (Actual):** ✅
- Implementación básica del flujo S3 directo
- Compatibilidad con flujo email existente
- Tracking básico por fuente

**Fase 2 (Próxima):**
- Mejoras en división de PDFs
- Validación avanzada de contenido
- Métricas y alertas mejoradas

**Fase 3 (Futura):**
- API para proveedores
- Dashboard de monitoreo
- Integración con sistemas externos

## 📞 SOPORTE Y CONTACTO

### 🆘 **PROBLEMAS COMUNES**

**Documento no se procesa:**
1. Verificar formato PDF
2. Revisar logs de CloudWatch
3. Confirmar permisos S3
4. Verificar trigger de lambda

**Error en división de PDF:**
1. Verificar integridad del archivo
2. Revisar tamaño del PDF
3. Confirmar permisos de lectura
4. Verificar logs de procesamiento

### 📧 **CONTACTO**

- **Desarrollador:** Edwin Peñalba
- **Email:** edwin.penalba@cibernetica.net
- **Proyecto:** OCR SAM Project
- **Repositorio:** [GitHub Repository]

---

## 📝 NOTAS DE IMPLEMENTACIÓN

### 🔧 **CAMBIOS REALIZADOS**

1. **Nueva Lambda:** `S3DocumentProcessor`
2. **Template actualizado:** `template.yaml`
3. **Processor modificado:** Soporte para S3 directo
4. **Documentación actualizada:** Flujo y arquitectura

### ✅ **COMPATIBILIDAD**

- **Flujo Email:** ✅ Mantiene funcionalidad completa
- **Flujo S3 Directo:** ✅ Nueva funcionalidad
- **APIs existentes:** ✅ Sin cambios
- **Tracking:** ✅ Mejorado con campo source

### 🚀 **DESPLIEGUE**

El nuevo flujo se despliega automáticamente con el stack existente. No requiere cambios en la infraestructura actual, solo agrega la nueva lambda y configuración.
