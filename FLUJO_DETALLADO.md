# 🔄 FLUJO DETALLADO PASO A PASO - SISTEMA OCR SAM

## 📊 DIAGRAMA DE FLUJO COMPLETO

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    SISTEMA OCR SAM - FLUJO COMPLETO                                     │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   USUARIO       │
│   Envía Email   │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   SES (AWS)     │───▶│   S3 BUCKET     │───▶│ EMAIL PROCESSOR │
│   Recibe Email  │    │   Almacena      │    │   LAMBDA        │
└─────────────────┘    └─────────────────┘    └─────────┬───────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PDF SPLITTER  │◀───│   S3 STORAGE    │◀───│   METADATA      │
│   LAMBDA        │    │   PDF Original  │    │   EXTRACTION    │
└─────────┬───────┘    └─────────────────┘    └─────────────────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   SQS QUEUE     │───▶│   PROCESSOR     │───▶│   MISTRAL AI    │
│   PDF Jobs      │    │   LAMBDA        │    │   API           │
└─────────────────┘    └─────────┬───────┘    └─────────────────┘
                                │
                                ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   S3 RESULTS    │◀───│   OCR RESULTS   │───▶│   SQS QUEUE     │
│   Storage       │    │   JSON Format   │    │   CRM Jobs      │
└─────────────────┘    └─────────────────┘    └─────────┬───────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   DYNAMODB      │◀───│   CRM INTEGRATOR│───▶│   CREATIO CRM   │
│   Tracking      │    │   LAMBDA        │    │   OData4 API    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   BATCH STATUS  │◀───│   API GATEWAY   │◀───│   USUARIO       │
│   LAMBDA        │    │   REST API      │    │   Consulta      │
└─────────────────┘    └─────────────────┘    └─────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PROVEEDOR     │───▶│   S3 BUCKET     │───▶│ S3 DOCUMENT     │
│   Deposita PDF  │    │   incoming/     │    │   PROCESSOR     │
└─────────────────┘    └─────────────────┘    └─────────┬───────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   PDF SPLITTER  │◀───│   S3 STORAGE    │◀───│   PDF DIVISION  │
│   LAMBDA        │    │   PDF Original  │    │   & VALIDATION  │
└─────────┬───────┘    └─────────────────┘    └─────────────────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   SQS QUEUE     │───▶│   PROCESSOR     │───▶│   MISTRAL AI    │
│   PDF Jobs      │    │   LAMBDA        │    │   API           │
└─────────────────┘    └─────────┬───────┘    └─────────────────┘
                                │
                                ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   S3 RESULTS    │◀───│   OCR RESULTS   │───▶│   SQS QUEUE     │
│   Storage       │    │   JSON Format   │    │   CRM Jobs      │
└─────────────────┘    └─────────────────┘    └─────────┬───────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   DYNAMODB      │◀───│   CRM INTEGRATOR│───▶│   CREATIO CRM   │
│   Tracking      │    │   LAMBDA        │    │   OData4 API    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
          │
          ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   BATCH STATUS  │◀───│   API GATEWAY   │◀───│   USUARIO       │
│   LAMBDA        │    │   REST API      │    │   Consulta      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📋 PASOS DETALLADOS

### 🎯 PASO 1A: RECEPCIÓN Y PROCESAMIENTO DE EMAIL (FLUJO EXISTENTE)

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   EMAIL     │───▶│     SES     │───▶│     S3      │───▶│   LAMBDA    │
│   INPUT     │    │   RECEIVE   │    │   STORE     │    │   TRIGGER   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

**📧 EMAIL FORMATO:**
```
cantidad_oficios: 5
empresa: Banco Global
origen: Panamá
observaciones: Oficios urgentes

[PDF ADJUNTO]
```

**🔧 PROCESAMIENTO:**
1. **SES** recibe email automáticamente
2. **S3** almacena email y PDF adjunto
3. **Lambda trigger** ejecuta `email_processor`
4. **Regex extraction** extrae metadatos del cuerpo
5. **PDF download** descarga archivo desde S3
6. **PDF splitting** divide en oficios individuales
7. **Validation** verifica cantidad declarada vs extraída

---

### 🎯 PASO 1B: RECEPCIÓN Y PROCESAMIENTO DE S3 DIRECTO (NUEVO FLUJO)

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ PROVEEDOR   │───▶│   S3 BUCKET │───▶│   incoming/ │───▶│   LAMBDA    │
│   Deposita  │    │   incoming/ │    │   Trigger   │    │   Trigger   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

**📁 ESTRUCTURA S3:**
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
└── jobs/
    └── {job_id}/
```

**🔧 PROCESAMIENTO:**
1. **Proveedor** deposita PDF en carpeta `incoming/`
2. **S3 trigger** ejecuta `s3_document_processor`
3. **PDF processing** descarga y procesa PDF
4. **PDF splitting** divide en oficios individuales (por página)
5. **Batch creation** crea lote automáticamente
6. **Job creation** envía oficios a cola de procesamiento

---

### 🎯 PASO 2: SEPARACIÓN DE PDF Y CREACIÓN DE JOBS

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   PDF       │───▶│   SPLITTER  │───▶│   S3 STORE  │───▶│   SQS SEND  │
│   ORIGINAL  │    │   LAMBDA    │    │   INDIVIDUAL│    │   JOBS      │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

**📄 RESULTADO:**
- PDF original: `emails/batch_id/email.pdf` o `incoming/documento.pdf`
- Oficio 1: `oficios/lotes/batch_id/batch_id_oficio_001.pdf`
- Oficio 2: `oficios/lotes/batch_id/batch_id_oficio_002.pdf`
- ...
- Oficio N: `oficios/lotes/batch_id/batch_id_oficio_NNN.pdf`

**📊 DYNAMODB ENTRIES:**
```json
{
  "batch_id": "a2761de8-e5be-4ca9-a9db-abb166ac7a63",
  "oficio_id": "BATCH_SUMMARY",
  "total_oficios": 5,
  "status": "pending",
  "created_at": "2025-07-23T22:03:08.628954",
  "source": "email"  // o "s3_direct"
}
```

---

### 🎯 PASO 3: PROCESAMIENTO OCR INDIVIDUAL

```
┌─────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────┐
│   SQS       │───▶│   PROCESSOR     │───▶│   MISTRAL   │───▶│   S3 STORE  │
│   MESSAGE   │    │   LAMBDA        │    │     AI      │    │   RESULTS   │
└─────────────┘    └─────────────────┘    └─────────────┘    └─────────────┘
```

**🔍 PROCESO OCR:**
1. **SQS** envía mensaje con job_id y source ('email' o 's3_direct')
2. **Processor Lambda** descarga PDF individual
3. **OCR extraction** extrae texto del PDF
4. **Mistral AI** analiza texto con prompt estructurado
5. **JSON parsing** convierte respuesta a estructura de datos
6. **S3 storage** guarda resultado en `jobs/{job_id}/result.json`

**📄 RESULTADO OCR:**
```json
{
  "success": true,
  "data": {
    "informacion_extraida": {
      "numero_oficio": "2024-001",
      "autoridad": "Juzgado Civil",
      "oficiado_cliente": "Juan Pérez",
      "monto": "B/. 15,000.00"
    },
    "lista_personas": {
      "total_personas": 2,
      "monto_total": 15000.00,
      "listado": [
        {
          "secuencia": 1,
          "nombre_completo": "María García López",
          "identificacion": "8-123-456",
          "monto_numerico": 7500.00,
          "expediente": "EXP-2024-001"
        }
      ]
    }
  }
}
```

---

### 🎯 PASO 4: INTEGRACIÓN CON CREATIO CRM

```
┌─────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────┐
│   SQS       │───▶│   CRM           │───▶│   CREATIO   │───▶│   DYNAMODB  │
│   CRM JOB   │    │   INTEGRATOR    │    │   OData4    │    │   UPDATE    │
└─────────────┘    └─────────────────┘    └─────────────┘    └─────────────┘
```

**🏢 PROCESO CRM:**
1. **SQS** envía mensaje con job_id y batch_id
2. **CRM Integrator** lee resultado OCR desde S3
3. **Data mapping** convierte formato OCR a Creatio
4. **Authentication** autentica con Creatio (cookies/BPMCSRF)
5. **Case creation** crea caso en Creatio
6. **Person records** crea registros en `NdosPersonasOCR`
7. **DynamoDB update** actualiza estado de tracking

**📊 CREATIO CASE:**
```json
{
  "Subject": "Oficio: 2024-001 - Juzgado Civil",
  "Notes": "Oficio procesado automáticamente por OCR\nCliente: Juan Pérez\nMonto: 15000.00",
  "PriorityId": "d9bd322c-f46b-1410-ee8c-0050ba5d6c38"
}
```

**👤 CREATIO PERSON:**
```json
{
  "NdosNombre": "María",
  "NdosApellidoPaterno": "García",
  "NdosApellidoMaterno": "López",
  "NdosIdentificacionNumero": "8-123-456",
  "NdosImporte": 7500.00,
  "NdosExpediente": "EXP-2024-001",
  "NdosOficioId": "case-12345"
}
```

---

### 🎯 PASO 5: SEGUIMIENTO Y CONSULTA

```
┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐
│   USUARIO   │───▶│   API           │───▶│   BATCH         │───▶│   DYNAMODB  │
│   CONSULTA  │    │   GATEWAY       │    │   STATUS        │    │   QUERY     │
└─────────────┘    └─────────────────┘    └─────────────────┘    └─────────────┘
```

**📊 RESPUESTA API:**
```json
{
  "batch_id": "a2761de8-e5be-4ca9-a9db-abb166ac7a63",
  "status": "completed",
  "total_oficios": 5,
  "completed_oficios": 5,
  "failed_oficios": 0,
  "completion_rate": 100.0,
  "created_at": "2025-07-23T22:03:08.628954",
  "completed_at": "2025-07-23T22:04:36.649",
  "source": "s3_direct",  // o "email"
  "oficios": [
    {
      "oficio_id": "a2761de8-e5be-4ca9-a9db-abb166ac7a63_oficio_001",
      "sequence_number": 1,
      "status": "completed",
      "ocr_status": "completed",
      "crm_status": "completed",
      "crm_id": "case-12345",
      "created_at": "2025-07-23T22:03:08.628954",
      "completed_at": "2025-07-23T22:04:17.649"
    }
  ]
}
```

## 🔧 COMPONENTES TÉCNICOS DETALLADOS

### 📧 EMAIL PROCESSOR LAMBDA (FLUJO EXISTENTE)
**Archivo:** `src/email_processor/app.py`
**Trigger:** S3 Object Created (carpeta `emails/`)
**Función:** Procesa emails entrantes

**🔧 FUNCIONES PRINCIPALES:**
- `extract_email_body_data()` - Extrae metadatos con regex
- `process_pdf_with_validation_improved()` - Divide PDF y valida
- `send_to_processor_queue()` - Envía a cola SQS

### 📁 S3 DOCUMENT PROCESSOR LAMBDA (NUEVO FLUJO)
**Archivo:** `src/s3_document_processor/app.py`
**Trigger:** S3 Object Created (carpeta `incoming/`)
**Función:** Procesa documentos depositados directamente en S3

**🔧 FUNCIONES PRINCIPALES:**
- `process_s3_event()` - Procesa eventos S3
- `process_pdf_from_s3()` - Descarga y procesa PDF desde S3
- `split_pdf_into_oficios()` - Divide PDF en oficios individuales
- `create_batch_tracking_record()` - Crea registros de tracking
- `send_oficios_to_processing_queue()` - Envía a cola de procesamiento

### 🔄 PROCESSOR LAMBDA (ACTUALIZADO)
**Archivo:** `src/processor/app.py`
**Trigger:** SQS Message
**Función:** Procesa OCR individual (email y S3 directo)

**🔧 FUNCIONES PRINCIPALES:**
- `process_batch_oficio_job()` - Procesa oficios de lotes (email o S3)
- `process_ocr_with_mistral()` - Integración con Mistral AI
- `format_ocr_response_for_lambda()` - Formatea respuesta
- `send_to_crm_queue()` - Envía a cola CRM

### 🏢 CRM INTEGRATOR LAMBDA
**Archivo:** `src/crm_integrator/app.py`
**Trigger:** SQS Message
**Función:** Integra con Creatio CRM

**🔧 FUNCIONES PRINCIPALES:**
- `CreatioService` - Clase para autenticación y API calls
- `map_ocr_data_to_creatio()` - Mapea datos al formato Creatio
- `create_creatio_request()` - Crea caso y personas

### 📊 BATCH STATUS LAMBDA
**Archivo:** `src/batch_status/app.py`
**Trigger:** API Gateway
**Función:** Consulta estado de lotes

**🔧 FUNCIONES PRINCIPALES:**
- `get_batch_status()` - Consulta DynamoDB
- `format_oficios_for_response()` - Formatea respuesta
- `calculate_batch_statistics()` - Calcula estadísticas

## 🗄️ ESTRUCTURA DE DATOS

### 📦 S3 BUCKET STRUCTURE
```
ocr-legal-documents-dev/
├── incoming/                    # ← NUEVA CARPETA
│   ├── documento_001.pdf       # ← PDF depositado por proveedor
│   ├── documento_002.pdf       # ← PDF depositado por proveedor
│   └── ...
├── emails/                      # ← MANTENER (flujo email existente)
│   └── {email_id}/
│       ├── email.json
│       └── attachments/
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

### 🗃️ DYNAMODB SCHEMA
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

## 🚀 DESPLIEGUE Y CONFIGURACIÓN

### 📄 TEMPLATE.YAML
Define todos los recursos AWS:
- **Lambdas:** 9 funciones serverless (incluyendo nueva S3DocumentProcessor)
- **SQS:** 3 colas de mensajes
- **S3:** Bucket para almacenamiento con triggers para ambas carpetas
- **DynamoDB:** Tabla para tracking
- **SES:** Configuración de email
- **API Gateway:** Endpoints REST
- **IAM:** Permisos y roles

### 📄 SAMCONFIG.TOML
Configuración por ambiente:
```toml
[default]
parameter_overrides = [
  "EnableDynamoDB=true",
  "S3BucketName=ocr-legal-documents-dev",
  "CreatioUrl=https://11006608-demo.creatio.com",
  "CreatioUsername=Supervisor",
  "CreatioPassword=!k*ZPCT&MkuF2cDiM!S"
]
```

## 🎯 BENEFICIOS Y CARACTERÍSTICAS

### ✅ AUTOMATIZACIÓN COMPLETA
- Procesamiento automático desde email hasta CRM
- Procesamiento automático desde S3 directo hasta CRM
- Sin intervención manual requerida
- Flujo end-to-end automatizado

### 📈 ESCALABILIDAD
- Arquitectura serverless
- Escala automáticamente según demanda
- Sin límites de concurrencia
- Soporte para múltiples fuentes de entrada

### 🔍 INTELIGENCIA ARTIFICIAL
- OCR avanzado con Mistral AI
- Extracción inteligente de información
- Análisis contextual de documentos
- Funciona tanto para email como S3 directo

### 📊 SEGUIMIENTO EN TIEMPO REAL
- Estado detallado de cada oficio
- API REST para consultas
- Métricas y estadísticas completas
- Diferenciación por fuente (email vs S3 directo)

### 🛡️ CONFIABILIDAD
- Reintentos automáticos
- Manejo robusto de errores
- Logs detallados para debugging
- Compatibilidad con flujos existentes

### 🔗 INTEGRACIÓN CRM
- Conexión directa con Creatio
- API OData4 estándar
- Mapeo automático de datos
- Funciona para ambos flujos de entrada

## 🔄 FLUJO DE INTEGRACIÓN

### 📧 FLUJO EMAIL (EXISTENTE)
```
Email → SES → S3 (emails/) → EmailProcessor → PDF Split → SQS → Processor → OCR → CRM
```

### 📁 FLUJO S3 DIRECTO (NUEVO)
```
Proveedor → S3 (incoming/) → S3DocumentProcessor → PDF Split → SQS → Processor → OCR → CRM
```

### 🔄 FLUJO COMPARTIDO
```
SQS → Processor → Mistral AI → S3 Results → SQS CRM → CRM Integrator → Creatio → DynamoDB
```

## 🚀 IMPLEMENTACIÓN

### 1. **NUEVA LAMBDA S3DocumentProcessor**
- Monitorea carpeta `incoming/` del S3
- Procesa PDFs depositados por proveedores
- Divide PDFs en oficios individuales
- Crea lotes automáticamente

### 2. **ACTUALIZACIÓN DEL PROCESSOR**
- Maneja tanto documentos de email como de S3 directo
- Detecta fuente del documento automáticamente
- Procesa oficios de ambos flujos

### 3. **ESTRUCTURA S3 ACTUALIZADA**
- Nueva carpeta `incoming/` para documentos directos
- Mantiene carpeta `emails/` para flujo existente
- Organización clara por fuente

### 4. **TRACKING MEJORADO**
- Campo `source` para identificar origen
- Compatibilidad con flujos existentes
- Estadísticas por fuente de entrada

## 🔧 CONFIGURACIÓN DEL PROVEEDOR

### 📁 CARPETA S3
```
s3://ocr-legal-documents-dev/incoming/
```

### 📄 FORMATO DE ARCHIVOS
- Solo archivos PDF
- Nombre descriptivo recomendado
- Tamaño máximo: 50MB por archivo

### 🔄 PROCESAMIENTO AUTOMÁTICO
- Trigger automático al depositar archivo
- Procesamiento inmediato
- Notificaciones de estado disponibles

## 📊 MONITOREO Y CONSULTAS

### 🔍 API ENDPOINTS
- `/batch/status/{batch_id}` - Estado del lote
- `/document/status/{job_id}` - Estado del oficio individual

### 📈 MÉTRICAS DISPONIBLES
- Procesamiento por fuente (email vs S3 directo)
- Tiempos de procesamiento
- Tasa de éxito por flujo
- Estadísticas de errores

### 🚨 ALERTAS Y NOTIFICACIONES
- Errores de procesamiento
- Completitud de lotes
- Fallos en integración CRM 