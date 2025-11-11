# Requisitos Técnicos para Integración S3 - Banco

## Resumen Ejecutivo

Para que nuestro sistema de procesamiento de documentos funcione con el S3 del banco, se requiere la siguiente configuración técnica.

## 1. Política de Bucket S3 (CRÍTICO)

El banco debe aplicar esta política a su bucket S3:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CiberneticaOCRAccess",
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
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::poc-globalbank-662498641605-us-east-1",
        "arn:aws:s3:::poc-globalbank-662498641605-us-east-1/*"
      ],
      "Condition": {
        "StringEquals": {
          "s3:prefix": ["input/", "processing/", "results/", "archive/"]
        }
      }
    }
  ]
}
```

**IMPORTANTE:** Reemplazar `NOMBRE-BUCKET-BANCO` con el nombre real del bucket del banco.

## 2. Estructura de Carpetas S3

El banco debe crear esta estructura en su bucket:

```
poc-globalbank-662498641605-us-east-1/
├── input/                    # Documentos entrantes desde impresora
│   └── scanned-documents/    # PDFs escaneados por la impresora
├── processing/              # Documentos en procesamiento (automático)
├── results/                # Resultados del procesamiento (automático)
└── archive/               # Documentos procesados (automático)
```

## 3. Configuración de Eventos S3

El banco debe configurar este evento en su bucket:

### Evento: Nuevo Documento PDF
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

### Notificación Lambda
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

## 4. Configuración de la Impresora

### Formato de Archivos
- **Formato:** PDF
- **Nomenclatura:** `YYYYMMDD_HHMMSS_documento.pdf`
- **Ubicación:** `s3://poc-globalbank-662498641605-us-east-1/input/scanned-documents/`

### Metadatos Requeridos
```json
{
  "source": "printer",
  "timestamp": "2024-01-15T10:30:00Z",
  "document_type": "legal_document",
  "printer_id": "PRINTER_001"
}
```

## 5. Flujo de Procesamiento

1. **Impresora** → Sube PDF a `input/scanned-documents/`
2. **Sistema** → Detecta archivo y lo procesa automáticamente
3. **Sistema** → Guarda resultados en `results/`
4. **Sistema** → Mueve documento a `archive/`

## 6. Información de Contacto

- **Cuenta AWS:** `390428552564`
- **Región:** `us-east-1`
- **Stack:** `ocr-sam-stack`

## 7. Prueba de Funcionamiento

Para probar la integración:

1. Subir un PDF de prueba a `poc-globalbank-662498641605-us-east-1/input/scanned-documents/`
2. Verificar que aparezcan resultados en `results/`
3. Confirmar que el documento se archive en `archive/`

---

**Nota:** Los roles IAM ya están creados y configurados en nuestra cuenta AWS. El banco solo necesita configurar su bucket S3 según estas especificaciones.
