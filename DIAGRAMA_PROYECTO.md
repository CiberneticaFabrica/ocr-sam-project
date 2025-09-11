# 📋 DIAGRAMA CONCEPTUAL - PROYECTO OCR SAM

## 🏗️ ARQUITECTURA GENERAL DEL SISTEMA

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SISTEMA OCR SAM - AWS                            │
│                    Procesamiento Automático de Oficios                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   EMAIL INPUT   │    │   PDF STORAGE   │    │   OCR PROCESS   │
│   (SES/S3)      │    │     (S3)        │    │   (Lambda)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  EMAIL PROCESS  │    │  PDF SPLITTER   │    │  MISTRAL AI     │
│   (Lambda)      │    │   (Lambda)      │    │   (API)         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   SQS QUEUE     │    │   SQS QUEUE     │    │   SQS QUEUE     │
│  (Email Batch)  │    │  (PDF Jobs)     │    │  (OCR Results)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  BATCH STATUS   │    │   PROCESSOR     │    │  CRM INTEGRATOR │
│   (Lambda)      │    │   (Lambda)      │    │   (Lambda)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   DYNAMODB      │    │   S3 RESULTS    │    │   CREATIO CRM   │
│  (Tracking)     │    │   (Storage)     │    │   (External)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 📁 ESTRUCTURA DE CARPETAS Y COMPONENTES

### 🗂️ CARPETA RAIZ (`/`)
```
ocr-sam-project/
├── 📄 template.yaml          # Configuración SAM (AWS Serverless Application Model)
├── 📄 samconfig.toml         # Configuración de despliegue por ambiente
├── 📄 README.md              # Documentación del proyecto
├── 📄 .gitignore             # Archivos ignorados por Git
├── 📁 events/                # Eventos de prueba para Lambdas
├── 📁 infrastructure/        # Recursos de infraestructura adicionales
├── 📁 tests/                 # Pruebas unitarias e integración
└── 📁 src/                   # CÓDIGO FUENTE PRINCIPAL
```

### 🧩 CARPETA `src/` - COMPONENTES PRINCIPALES

#### 📧 `src/email_processor/` - Procesador de Emails
```
email_processor/
├── 📄 app.py                 # Lambda principal para procesar emails
└── 📄 requirements.txt       # Dependencias Python
```

**🎯 FUNCIÓN:**
- Recibe emails automáticamente desde SES (Simple Email Service)
- Extrae metadatos del email (empresa, cantidad, origen, observaciones)
- Busca archivos PDF adjuntos
- Separa PDFs en oficios individuales
- Valida cantidad declarada vs cantidad extraída
- Envía oficios a cola SQS para procesamiento OCR

**🔄 FLUJO:**
1. Email llega → SES → S3 → Lambda trigger
2. Extrae metadatos con regex del cuerpo del email
3. Descarga PDF adjunto desde S3
4. Divide PDF en oficios individuales (PyPDF2)
5. Valida cantidad y guarda cada oficio en S3
6. Envía mensajes a SQS para procesamiento OCR

---

#### 🔄 `src/processor/` - Procesador OCR Principal
```
processor/
├── 📄 app.py                 # Lambda principal para OCR
└── 📄 requirements.txt       # Dependencias Python
```

**🎯 FUNCIÓN:**
- Procesa oficios individuales desde SQS
- Extrae texto del PDF con OCR
- Envía texto a Mistral AI para análisis inteligente
- Extrae información estructurada (personas, montos, fechas, etc.)
- Guarda resultados en S3
- Envía resultados a cola CRM

**🔄 FLUJO:**
1. Recibe mensaje SQS con datos del oficio
2. Descarga PDF desde S3
3. Extrae texto con OCR
4. Envía a Mistral AI con prompt estructurado
5. Parsea respuesta JSON con información extraída
6. Guarda resultado en S3 (`jobs/{job_id}/result.json`)
7. Envía a cola CRM para integración

---

#### 🏢 `src/crm_integrator/` - Integrador CRM
```
crm_integrator/
├── 📄 app.py                 # Lambda para integración con Creatio
└── 📄 requirements.txt       # Dependencias Python
```

**🎯 FUNCIÓN:**
- Recibe resultados OCR desde SQS
- Mapea datos al formato de Creatio CRM
- Autentica con Creatio usando OData4 API
- Crea casos en Creatio
- Crea registros de personas asociadas al caso
- Actualiza estado en DynamoDB

**🔄 FLUJO:**
1. Recibe mensaje SQS con job_id
2. Lee resultado OCR desde S3
3. Mapea datos al formato Creatio
4. Autentica con Creatio (cookies/BPMCSRF)
5. Crea caso en Creatio
6. Crea registros de personas en `NdosPersonasOCR`
7. Actualiza tracking en DynamoDB

---

#### 📊 `src/batch_status/` - Estado de Lotes
```
batch_status/
├── 📄 app.py                 # Lambda para consultar estado
└── 📄 requirements.txt       # Dependencias Python
```

**🎯 FUNCIÓN:**
- API REST para consultar estado de lotes
- Lee información desde DynamoDB
- Proporciona estadísticas de procesamiento
- Permite seguimiento en tiempo real

**🔄 FLUJO:**
1. Recibe petición HTTP GET/POST
2. Consulta DynamoDB por batch_id
3. Agrega información de oficios individuales
4. Calcula estadísticas (completados, errores, etc.)
5. Retorna respuesta JSON estructurada

---

#### 📧 `src/notification/` - Notificaciones
```
notification/
├── 📄 app.py                 # Lambda para enviar notificaciones
└── 📄 requirements.txt       # Dependencias Python
```

**🎯 FUNCIÓN:**
- Envía notificaciones por email
- Notifica sobre completitud de lotes
- Envía alertas de errores
- Usa SES para envío de emails

---

#### 🔄 `src/retry/` - Reintentos
```
retry/
├── 📄 app.py                 # Lambda para manejo de reintentos
└── 📄 requirements.txt       # Dependencias Python
```

**🎯 FUNCIÓN:**
- Maneja reintentos automáticos
- Reprocesa jobs fallidos
- Implementa backoff exponencial
- Evita loops infinitos

---

#### 🛣️ `src/router/` - Enrutador
```
router/
├── 📄 app.py                 # Lambda para enrutamiento
└── 📄 requirements.txt       # Dependencias Python
```

**🎯 FUNCIÓN:**
- Enruta peticiones a componentes correctos
- API Gateway principal
- Maneja diferentes tipos de requests
- Distribuye carga

---

#### 📈 `src/status/` - Estado Individual
```
status/
├── 📄 app.py                 # Lambda para estado individual
└── 📄 requirements.txt       # Dependencias Python
```

**🎯 FUNCIÓN:**
- Consulta estado de oficios individuales
- Lee desde DynamoDB
- Proporciona detalles específicos
- API para seguimiento granular

---

#### 🤝 `src/shared/` - Utilidades Compartidas
```
shared/
├── 📄 __init__.py            # Inicializador del módulo
└── 📄 utils.py               # Funciones utilitarias compartidas
```

**🎯 FUNCIÓN:**
- Funciones utilitarias reutilizables
- Formateo de datos
- Validaciones comunes
- Funciones de limpieza de texto
- Cálculos de estadísticas

**🔧 FUNCIONES PRINCIPALES:**
- `format_persons_for_lambda()` - Formatea personas para Lambda
- `clean_value_lambda()` - Limpia valores de texto
- `parse_currency_lambda()` - Parsea montos monetarios
- `calculate_extraction_percentage()` - Calcula porcentajes de extracción

---

## 🔄 FLUJO COMPLETO DEL SISTEMA

### 📥 PASO 1: RECEPCIÓN DE EMAIL
```
Usuario → Email → SES → S3 → email_processor Lambda
```

**Datos del Email:**
```
cantidad_oficios: 5
empresa: Banco Global
origen: Panamá
observaciones: Oficios urgentes
```

### 📄 PASO 2: PROCESAMIENTO DE PDF
```
email_processor → PDF Split → S3 Storage → SQS Queue
```

**Resultado:**
- PDF original guardado en S3
- 5 oficios individuales separados
- Metadatos extraídos del email
- Mensajes enviados a cola SQS

### 🔍 PASO 3: PROCESAMIENTO OCR
```
SQS → processor Lambda → Mistral AI → S3 Results
```

**Proceso OCR:**
1. Descarga PDF individual
2. Extrae texto con OCR
3. Envía a Mistral AI con prompt estructurado
4. Recibe JSON con información extraída:
   ```json
   {
     "informacion_extraida": {
       "numero_oficio": "2024-001",
       "autoridad": "Juzgado Civil",
       "oficiado_cliente": "Juan Pérez"
     },
     "lista_personas": {
       "total_personas": 2,
       "monto_total": 15000.00,
       "listado": [
         {
           "nombre_completo": "María García",
           "identificacion": "8-123-456",
           "monto_numerico": 7500.00
         }
       ]
     }
   }
   ```

### 🏢 PASO 4: INTEGRACIÓN CRM
```
SQS → crm_integrator → Creatio API → DynamoDB Update
```

**Proceso CRM:**
1. Lee resultado OCR desde S3
2. Mapea datos al formato Creatio
3. Autentica con Creatio (OData4)
4. Crea caso en Creatio
5. Crea registros de personas en `NdosPersonasOCR`
6. Actualiza estado en DynamoDB

### 📊 PASO 5: SEGUIMIENTO
```
API Gateway → batch_status Lambda → DynamoDB → JSON Response
```

**Consulta de Estado:**
```json
{
  "batch_id": "a2761de8-e5be-4ca9-a9db-abb166ac7a63",
  "status": "completed",
  "total_oficios": 5,
  "completed_oficios": 5,
  "failed_oficios": 0,
  "completion_rate": 100.0,
  "oficios": [
    {
      "oficio_id": "a2761de8-e5be-4ca9-a9db-abb166ac7a63_oficio_001",
      "status": "completed",
      "crm_id": "case-12345"
    }
  ]
}
```

## 🗄️ ALMACENAMIENTO DE DATOS

### 📦 S3 BUCKETS
```
ocr-legal-documents-{env}/
├── emails/                   # Emails originales
├── oficios/lotes/           # PDFs separados por lotes
├── jobs/{job_id}/           # Resultados OCR por job
│   ├── input.json           # Datos de entrada
│   └── result.json          # Resultado OCR
└── logs/                    # Logs del sistema
```

### 🗃️ DYNAMODB TABLES
```
ocr-tracking-table
├── batch_id (Partition Key)
├── oficio_id (Sort Key)
├── status (pending/processing/completed/error)
├── ocr_status
├── crm_status
├── created_at
├── updated_at
├── completed_at
└── crm_details
```

## 🔧 CONFIGURACIÓN Y DESPLIEGUE

### 📄 `template.yaml`
- Define todos los recursos AWS
- Lambdas, SQS, S3, DynamoDB, SES
- Permisos IAM
- Variables de entorno

### 📄 `samconfig.toml`
- Configuración por ambiente (dev/staging/prod)
- Parámetros específicos por entorno
- URLs de Creatio, emails, etc.

## 🎯 BENEFICIOS DEL SISTEMA

1. **🔄 Automatización Completa**: Desde email hasta CRM
2. **📈 Escalabilidad**: Serverless, se adapta automáticamente
3. **🔍 Inteligencia Artificial**: OCR + Mistral AI para extracción precisa
4. **📊 Seguimiento en Tiempo Real**: Estado detallado de cada oficio
5. **🛡️ Confiabilidad**: Reintentos automáticos y manejo de errores
6. **🔗 Integración CRM**: Conexión directa con Creatio
7. **📱 API REST**: Consultas programáticas del estado

## 🚀 TECNOLOGÍAS UTILIZADAS

- **AWS Lambda**: Computación serverless
- **AWS S3**: Almacenamiento de archivos
- **AWS SQS**: Colas de mensajes
- **AWS SES**: Envío de emails
- **AWS DynamoDB**: Base de datos NoSQL
- **AWS SAM**: Framework de despliegue
- **Python**: Lenguaje de programación
- **Mistral AI**: Inteligencia artificial para OCR
- **Creatio CRM**: Sistema CRM externo
- **OData4**: Protocolo de API para Creatio 