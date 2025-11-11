# Credenciales S3 Requeridas del Banco

## Resumen

Para que nuestro sistema pueda acceder al S3 del banco, necesitamos las siguientes credenciales y configuraciones.

## 1. Credenciales AWS del Banco

### 1.1 Acceso Programático
```json
{
  "AccessKeyId": "AKIA...",
  "SecretAccessKey": "...",
  "Region": "us-east-1"
}
```

**Nota:** Estas credenciales deben tener permisos específicos para el bucket S3.

### 1.2 Permisos Requeridos
Las credenciales deben incluir estos permisos IAM:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::poc-globalbank-662498641605-us-east-1",
        "arn:aws:s3:::poc-globalbank-662498641605-us-east-1/*"
      ]
    }
  ]
}
```

## 2. Información del Bucket S3

### 2.1 Detalles del Bucket
- **Nombre del Bucket:** `poc-globalbank-662498641605-us-east-1`
- **Región:** `us-east-1` (o la región donde esté)
- **Tipo de Encriptación:** (AES-256, KMS, etc.)
- **Versionado:** (Habilitado/Deshabilitado)

### 2.2 Estructura de Carpetas
Confirmar que tengan estas carpetas:
```
poc-globalbank-662498641605-us-east-1/
├── input/scanned-documents/    # Donde suben PDFs
├── processing/                # Para documentos en proceso
├── results/                   # Para resultados
└── archive/                   # Para documentos procesados
```

## 3. Configuración de Eventos S3

### 3.1 Evento Configurado
Confirmar que tengan configurado este evento:

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

## 4. Política de Bucket Aplicada

### 4.1 Política Cross-Account
Confirmar que tengan aplicada esta política:

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
      ]
    }
  ]
}
```

## 5. Información de la Impresora

### 5.1 Configuración de Subida
- **Formato de archivos:** PDF
- **Nomenclatura:** `YYYYMMDD_HHMMSS_documento.pdf`
- **Frecuencia de subida:** (Cada X minutos/horas)
- **Tamaño máximo:** (MB por archivo)

### 5.2 Metadatos
Confirmar que la impresora incluya estos metadatos:
```json
{
  "source": "printer",
  "timestamp": "2024-01-15T10:30:00Z",
  "document_type": "legal_document",
  "printer_id": "PRINTER_001"
}
```

## 6. Configuración de Seguridad

### 6.1 Encriptación
- **En tránsito:** TLS 1.2+
- **En reposo:** (AES-256, KMS, etc.)
- **Claves KMS:** (Si usan KMS)

### 6.2 Logs de Acceso
- **CloudTrail:** Habilitado para el bucket
- **S3 Access Logs:** Habilitados
- **Retención de logs:** (Días/meses)

## 7. Información de Contacto Técnico

### 7.1 Equipo del Banco
- **Contacto técnico:** (Nombre, email, teléfono)
- **Horario de soporte:** (Lunes a Viernes, 8AM-6PM)
- **Escalación:** (Para emergencias)

### 7.2 Notificaciones
- **Email para alertas:** (Cuando hay errores de procesamiento)
- **Slack/Teams:** (Para notificaciones en tiempo real)

## 8. Pruebas de Conectividad

### 8.1 Prueba Inicial
Una vez configurado, realizar:
1. Subir un PDF de prueba a `input/scanned-documents/`
2. Verificar que se active el procesamiento
3. Confirmar que aparezcan resultados en `results/`
4. Validar que el documento se archive en `archive/`

### 8.2 Monitoreo
- **Métricas CloudWatch:** Habilitadas
- **Alertas:** Configuradas para errores
- **Dashboard:** Para monitoreo en tiempo real

---

**Nota:** Todas estas credenciales y configuraciones son necesarias para una integración exitosa y segura con el S3 del banco.
