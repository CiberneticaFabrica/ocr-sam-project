# Configuración S3 para Integración con Sistema de Procesamiento de Documentos

## Resumen Ejecutivo

Este documento especifica los requisitos técnicos que el banco debe configurar en su infraestructura AWS S3 para permitir la integración con nuestro sistema de procesamiento de documentos legales.

**IMPORTANTE:** Los roles IAM ya están creados en la cuenta AWS `390428552564`. El banco solo necesita configurar el bucket S3 y los eventos.

## 1. Roles IAM Existentes

### 1.1 Roles Ya Configurados

**✅ CONFIRMADO:** Los siguientes roles IAM ya existen en la cuenta AWS (`390428552564`) y están listos para usar. El banco NO necesita crearlos.

#### Role 1: DocumentProcessorFunction
```json
{
  "RoleName": "ocr-sam-stack-DocumentProcessorFunctionRole-0efPhhcJvImN",
  "AssumeRolePolicyDocument": {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "lambda.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  },
  "Policies": [
    {
      "PolicyName": "S3DocumentAccess",
      "PolicyDocument": {
        "Version": "2012-10-17",
        "Statement": [
          {
            "Effect": "Allow",
            "Action": [
              "s3:GetObject",
              "s3:PutObject",
              "s3:DeleteObject"
            ],
            "Resource": "arn:aws:s3:::BUCKET_NAME/*"
          },
          {
            "Effect": "Allow",
            "Action": [
              "s3:ListBucket"
            ],
            "Resource": "arn:aws:s3:::BUCKET_NAME"
          }
        ]
      }
    }
  ]
}
```

#### Role 2: OCRProcessorFunction
```json
{
  "RoleName": "ocr-sam-stack-OCRProcessorFunctionRole-38pFvpYZALEs",
  "AssumeRolePolicyDocument": {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "lambda.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  },
  "Policies": [
    {
      "PolicyName": "S3DocumentProcessing",
      "PolicyDocument": {
        "Version": "2012-10-17",
        "Statement": [
          {
            "Effect": "Allow",
            "Action": [
              "s3:GetObject",
              "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::BUCKET_NAME/*"
          },
          {
            "Effect": "Allow",
            "Action": [
              "s3:ListBucket"
            ],
            "Resource": "arn:aws:s3:::BUCKET_NAME"
          }
        ]
      }
    }
  ]
}
```

#### Role 3: CRMIntegratorFunction
```json
{
  "RoleName": "ocr-sam-stack-CRMIntegratorFunctionRole-HH1YS0BjmWnX",
  "AssumeRolePolicyDocument": {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "lambda.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  },
  "Policies": [
    {
      "PolicyName": "S3ResultAccess",
      "PolicyDocument": {
        "Version": "2012-10-17",
        "Statement": [
          {
            "Effect": "Allow",
            "Action": [
              "s3:GetObject",
              "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::BUCKET_NAME/results/*"
          }
        ]
      }
    }
  ]
}
```

## 2. Configuración del Bucket S3

### 2.1 Estructura de Carpetas Requerida

El bucket S3 debe tener la siguiente estructura:

```
BUCKET_NAME/
├── input/                    # Documentos entrantes desde impresora
│   ├── scanned-documents/    # PDFs escaneados por la impresora
│   └── batch-files/         # Archivos de lote (opcional)
├── processing/              # Documentos en procesamiento
│   ├── batches/            # Lotes de procesamiento
│   └── individual/         # Procesamiento individual
├── results/                # Resultados del procesamiento
│   ├── ocr-results/        # Resultados de extracción
│   ├── structured-data/    # Datos estructurados
│   └── reports/           # Reportes de procesamiento
└── archive/               # Documentos procesados (backup)
    ├── processed/         # Documentos ya procesados
    └── failed/           # Documentos con errores
```

### 2.2 Configuración de Eventos S3

El banco debe configurar los siguientes eventos S3:

#### Evento 1: Documento Nuevo en Input
```json
{
  "Rules": [
    {
      "Name": "NewDocumentTrigger",
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "input/scanned-documents/"
            },
            {
              "Name": "suffix",
              "Value": ".pdf"
            }
          ]
        }
      },
      "Status": "Enabled",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]
}
```

#### Evento 2: Lote Nuevo
```json
{
  "Rules": [
    {
      "Name": "NewBatchTrigger",
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "input/batch-files/"
            }
          ]
        }
      },
      "Status": "Enabled",
      "Events": ["s3:ObjectCreated:*"]
    }
  ]
}
```

### 2.3 Configuración de Notificaciones

El banco debe configurar las notificaciones S3 para invocar las funciones Lambda:

```json
{
  "LambdaConfigurations": [
    {
      "Id": "DocumentProcessorTrigger",
      "LambdaFunctionArn": "arn:aws:lambda:us-east-1:390428552564:function:ocr-sam-stack-document-processing",
      "Events": ["s3:ObjectCreated:*"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "input/scanned-documents/"
            }
          ]
        }
      }
    }
  ]
}
```

## 3. Permisos de Bucket

### 3.1 Política de Bucket

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowLambdaAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::390428552564:role/ocr-sam-stack-DocumentProcessorFunctionRole-0efPhhcJvImN",
          "arn:aws:iam::390428552564:role/ocr-sam-stack-OCRProcessorFunctionRole-38pFvpYZALEs",
          "arn:aws:iam::390428552564:role/ocr-sam-stack-CRMIntegratorFunctionRole-HH1YS0BjmWnX"
        ]
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::BUCKET_NAME",
        "arn:aws:s3:::BUCKET_NAME/*"
      ]
    }
  ]
}
```

## 4. Configuración de la Impresora

### 4.1 Formato de Archivos

La impresora debe enviar archivos con las siguientes características:

- **Formato:** PDF
- **Nomenclatura:** `YYYYMMDD_HHMMSS_documento.pdf`
- **Ubicación:** `s3://BUCKET_NAME/input/scanned-documents/`
- **Metadatos requeridos:**
  - `source`: "printer"
  - `timestamp`: ISO 8601 format
  - `batch_id`: (opcional, para lotes)

### 4.2 Ejemplo de Metadatos

```json
{
  "source": "printer",
  "timestamp": "2024-01-15T10:30:00Z",
  "batch_id": "BATCH_20240115_001",
  "document_type": "legal_document",
  "printer_id": "PRINTER_001"
}
```

## 5. Flujo de Procesamiento

### 5.1 Flujo Esperado

1. **Impresora** → Sube PDF a `input/scanned-documents/`
2. **Sistema** → Detecta nuevo archivo y lo mueve a `processing/`
3. **Sistema** → Procesa documento y genera resultados
4. **Sistema** → Guarda resultados en `results/`
5. **Sistema** → Mueve documento original a `archive/processed/`

### 5.2 Estados de Procesamiento

- `pending`: Documento recibido, esperando procesamiento
- `processing`: Documento en proceso
- `completed`: Procesamiento exitoso
- `failed`: Error en procesamiento
- `archived`: Documento movido a archivo

## 6. Monitoreo y Logs

### 6.1 CloudWatch Logs

El banco debe configurar acceso a los siguientes grupos de logs:

- `/aws/lambda/ocr-sam-stack-document-processing`
- `/aws/lambda/ocr-sam-stack-ocr-processing`
- `/aws/lambda/ocr-sam-stack-crm-integration`

### 6.2 Métricas Importantes

- Número de documentos procesados por hora
- Tiempo promedio de procesamiento
- Tasa de éxito/error
- Uso de almacenamiento S3

## 7. Consideraciones de Seguridad

### 7.1 Encriptación

- **En tránsito:** TLS 1.2+
- **En reposo:** AES-256
- **Claves:** AWS KMS (recomendado)

### 7.2 Acceso

- Solo los roles especificados tienen acceso al bucket
- Logs de acceso habilitados
- Versionado de objetos habilitado

## 8. Pruebas Técnicas

### 8.1 Prueba de Conectividad

1. Subir un PDF de prueba a `input/scanned-documents/`
2. Verificar que se active el procesamiento
3. Confirmar que aparezcan resultados en `results/`
4. Validar que el documento se archive correctamente

### 8.2 Archivo de Prueba

El banco puede usar cualquier PDF legal para las pruebas iniciales.

## 9. Contacto Técnico

Para soporte técnico durante la configuración:
- **Email:** soporte-tecnico@empresa.com
- **Horario:** Lunes a Viernes, 8:00 AM - 6:00 PM
- **Urgencias:** +1-XXX-XXX-XXXX

---

**Nota:** Esta configuración es específica para la integración con nuestro sistema de procesamiento de documentos. Cualquier modificación debe ser coordinada con nuestro equipo técnico.
