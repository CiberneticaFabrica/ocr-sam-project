# Documentación de Funciones Lambda - Sistema OCR

## Resumen Ejecutivo

Este documento explica el funcionamiento de cada función Lambda en el sistema de procesamiento OCR de documentos legales.

## Arquitectura General

```
S3 (Banco) → DocumentProcessor → OCRProcessor → CRMIntegrator
     ↓              ↓               ↓              ↓
  PDF Input    Split PDFs    Extract Data    Send to CRM
```

---

## 1. DocumentProcessorFunction
**ARN:** `arn:aws:lambda:us-east-1:390428552564:function:ocr-sam-stack-document-processing`

### 🎯 Propósito
Función principal que recibe documentos PDF desde el S3 del banco y los divide en oficios individuales.

### 📥 Entrada
- **Trigger:** Evento S3 cuando se sube un PDF
- **Ubicación:** `poc-globalbank-662498641605-us-east-1/input/scanned-documents/`
- **Formato:** PDF de documentos legales

### ⚙️ Procesamiento
1. **Descarga PDF** desde S3 del banco
2. **Valida contenido** del PDF
3. **Extrae metadatos** de la primera página
4. **Crea batch tracking** en DynamoDB
5. **Divide PDF** en oficios individuales
6. **Almacena oficios** en S3 (processing/)
7. **Envía oficios** a cola SQS para procesamiento OCR
8. **Actualiza estado** del batch

### 📤 Salida
- **Oficios individuales** en S3 (processing/)
- **Mensajes SQS** para cada oficio
- **Tracking** en DynamoDB
- **Métricas** en CloudWatch

### 🔧 Configuración
- **Memoria:** 2048 MB
- **Timeout:** 600 segundos
- **Runtime:** Python 3.9
- **Handler:** `document_processor.app.lambda_handler`

---

## 2. OCRProcessorFunction
**ARN:** `arn:aws:lambda:us-east-1:390428552564:function:ocr-sam-stack-ocr-processing`

### 🎯 Propósito
Procesa oficios individuales usando OCR mejorado con Mistral AI para extraer información estructurada.

### 📥 Entrada
- **Trigger:** Mensajes SQS desde DocumentProcessor
- **Contenido:** Oficios individuales en S3
- **Formato:** PDF de oficios legales

### ⚙️ Procesamiento
1. **Recibe mensaje SQS** con información del oficio
2. **Descarga PDF** del oficio desde S3
3. **Procesa con OCR Mistral AI** para extraer texto
4. **Valida y enriquece** resultados con PostOCRValidator
5. **Estructura datos** (personas, montos, fechas, etc.)
6. **Almacena resultados** en S3 (results/)
7. **Actualiza tracking** en DynamoDB
8. **Envía a CRM** si está configurado

### 📤 Salida
- **Resultados estructurados** en S3 (results/)
- **Datos JSON** con información extraída
- **Tracking actualizado** en DynamoDB
- **Mensajes CRM** (opcional)
- **Métricas** en CloudWatch

### 🔧 Configuración
- **Memoria:** 2048 MB
- **Timeout:** 600 segundos
- **Runtime:** Python 3.9
- **Handler:** `ocr_processor.app.lambda_handler`

### 📊 Datos Extraídos
- **Información general:** Número de oficio, autoridad, fecha, destinatario
- **Lista de personas:** Nombres, identificaciones, montos, cuentas
- **Clasificación:** Tipo de oficio, trámite, departamento
- **Palabras clave:** Términos importantes encontrados
- **Texto completo:** Contenido completo del documento

---

## 3. CRMIntegratorFunction
**ARN:** `arn:aws:lambda:us-east-1:390428552564:function:ocr-sam-stack-crm-integration`

### 🎯 Propósito
Integra los resultados OCR con el sistema CRM (Creatio) para crear registros de clientes y casos.

### 📥 Entrada
- **Trigger:** Mensajes SQS desde OCRProcessor
- **Contenido:** Resultados OCR estructurados
- **Formato:** JSON con datos extraídos

### ⚙️ Procesamiento
1. **Recibe mensaje SQS** con resultados OCR
2. **Descarga resultados** desde S3
3. **Valida estructura** de datos
4. **Formatea datos** para CRM
5. **Crea registros** en Creatio CRM
6. **Actualiza tracking** en DynamoDB
7. **Maneja errores** y reintentos

### 📤 Salida
- **Registros CRM** creados/actualizados
- **Tracking actualizado** en DynamoDB
- **Métricas** en CloudWatch
- **Logs** de integración

### 🔧 Configuración
- **Memoria:** 1024 MB
- **Timeout:** 300 segundos
- **Runtime:** Python 3.9
- **Handler:** `crm_integrator.app.lambda_handler`

### 🏢 Integración CRM
- **URL:** Configurable (Creatio)
- **Autenticación:** Username/Password
- **Datos:** Personas, montos, casos legales
- **Schema:** Compatible con estructura existente

---

## 4. BatchStatusFunction
**ARN:** `arn:aws:lambda:us-east-1:390428552564:function:ocr-sam-stack-batch-status`

### 🎯 Propósito
Proporciona API para consultar el estado de lotes de procesamiento.

### 📥 Entrada
- **Trigger:** API Gateway (GET/POST)
- **Parámetros:** batch_id
- **Formato:** HTTP Request

### ⚙️ Procesamiento
1. **Recibe request** HTTP
2. **Consulta DynamoDB** para estado del batch
3. **Calcula progreso** del procesamiento
4. **Formatea respuesta** JSON
5. **Retorna estado** actualizado

### 📤 Salida
- **Estado del batch** (pending, processing, completed, failed)
- **Progreso** (X de Y oficios procesados)
- **Detalles** de cada oficio
- **Tiempo estimado** de finalización

### 🔧 Configuración
- **Memoria:** 256 MB
- **Timeout:** 30 segundos
- **Runtime:** Python 3.9
- **Handler:** `batch_status.app.lambda_handler`

---

## 5. StatusFunction
**ARN:** `arn:aws:lambda:us-east-1:390428552564:function:ocr-sam-stack-status`

### 🎯 Propósito
Proporciona API para consultar el estado de oficios individuales.

### 📥 Entrada
- **Trigger:** API Gateway (GET)
- **Parámetros:** job_id
- **Formato:** HTTP Request

### ⚙️ Procesamiento
1. **Recibe request** HTTP con job_id
2. **Consulta DynamoDB** para estado del oficio
3. **Obtiene resultados** desde S3 si están disponibles
4. **Formatea respuesta** JSON
5. **Retorna estado** y resultados

### 📤 Salida
- **Estado del oficio** (pending, processing, completed, failed)
- **Resultados OCR** (si están disponibles)
- **Metadatos** del procesamiento
- **Enlaces** a archivos S3

### 🔧 Configuración
- **Memoria:** 256 MB
- **Timeout:** 30 segundos
- **Runtime:** Python 3.9
- **Handler:** `status.app.lambda_handler`

---

## Flujo de Procesamiento Completo

### 1. Entrada de Documento
```
Impresora → S3 (input/scanned-documents/) → DocumentProcessor
```

### 2. División y Procesamiento
```
DocumentProcessor → S3 (processing/) → SQS → OCRProcessor
```

### 3. Extracción de Datos
```
OCRProcessor → Mistral AI → S3 (results/) → SQS → CRMIntegrator
```

### 4. Integración CRM
```
CRMIntegrator → Creatio CRM → DynamoDB (tracking)
```

### 5. Consulta de Estado
```
API Gateway → BatchStatus/Status → DynamoDB → Respuesta JSON
```

---

## Configuración de Recursos

### S3 Buckets
- **Input:** `poc-globalbank-662498641605-us-east-1/input/`
- **Processing:** `poc-globalbank-662498641605-us-east-1/processing/`
- **Results:** `poc-globalbank-662498641605-us-east-1/results/`
- **Archive:** `poc-globalbank-662498641605-us-east-1/archive/`

### SQS Queues
- **OCR Processing:** `ocr-sam-stack-ocr-processing`
- **CRM Integration:** `ocr-sam-stack-crm-integration`
- **Dead Letter:** `ocr-sam-stack-ocr-dlq`, `ocr-sam-stack-crm-dlq`

### DynamoDB Tables
- **Batch Tracking:** `OCRBatchTracking`
- **Job Tracking:** `OCRJobTracking`

### API Gateway
- **Base URL:** Configurable
- **Endpoints:** `/batch-status/{batch_id}`, `/status/{job_id}`

---

## Monitoreo y Métricas

### CloudWatch Metrics
- **Procesamiento:** Documentos procesados, tiempo, errores
- **OCR:** Confianza, texto extraído, personas encontradas
- **CRM:** Registros creados, errores de integración
- **SQS:** Mensajes procesados, cola de mensajes

### Logs
- **Nivel:** INFO (configurable)
- **Retención:** 14 días
- **Filtros:** Por función, nivel de error, job_id

### Alertas
- **Error Rate:** > 5% de errores
- **Queue Depth:** > 100 mensajes pendientes
- **Timeout:** Funciones que exceden tiempo límite

---

## Consideraciones de Seguridad

### IAM Roles
- **Principio de menor privilegio**
- **Permisos específicos** por función
- **Cross-account access** para S3 del banco

### Encriptación
- **En tránsito:** TLS 1.2+
- **En reposo:** AES-256
- **API Keys:** Encriptadas en parámetros

### Acceso
- **VPC:** Configurable
- **API Gateway:** Autenticación opcional
- **S3:** Políticas de bucket restrictivas

---

## Troubleshooting

### Errores Comunes
1. **Timeout:** Aumentar memoria o timeout
2. **Permisos S3:** Verificar políticas cross-account
3. **Queue Depth:** Revisar procesamiento OCR
4. **CRM Errors:** Verificar credenciales y conectividad

### Debugging
- **CloudWatch Logs:** Revisar logs por función
- **X-Ray:** Habilitar para tracing distribuido
- **Métricas:** Monitorear tendencias y picos

---

**Nota:** Esta documentación refleja la configuración actual del sistema desplegado en la cuenta AWS `390428552564`.
