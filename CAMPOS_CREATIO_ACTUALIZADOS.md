# 🏢 CAMPOS CREATIO ACTUALIZADOS - MAPEO DESDE OCR

## 📋 CAMPOS AGREGADOS AL CASO EN CREATIO

### 🔧 CAMPOS DEL CASO (CASE)

| Campo Creatio | Origen OCR | Descripción | Tipo |
|---------------|------------|-------------|------|
| `NdosSensitivo` | `RequiresUrgentAction` | Indica si el oficio es sensible/urgente | Boolean |
| `NdosDirigidoaGlobalBank` | `DirectedToGlobalBank` | Si está dirigido a Global Bank | Boolean |
| `NdosSellodeAutoridad` | `AuthorityStamp` | Si tiene sello de autoridad | Boolean |
| `NdosDelito` | `Crime` | Tipo de delito mencionado | String |
| `NdosFechadeResolucion` | `ResolutionDate` | Fecha de resolución | Date |
| `NdosNdeResolucion` | `ResolutionNumber` | Número de resolución | String |
| `NdosVencimiento` | `DueDate` | Fecha de vencimiento | Date |
| `NdosCarpeta` | `Folder` | Número de carpeta | String |
| `NdosSucursaldeRecibido` | `BranchReceived` | Sucursal donde se recibió | String |
| `NdosColumn6` | `Amount` | Monto del oficio | Float |
| `NdosFechadeRecibido` | `ReceivedDate` | Fecha de recepción | Date |
| `NdosFechadeEmision` | `IssueDate` | Fecha de emisión | Date |
| `NdosAutoridad` | `Authority` | Autoridad que emitió | String |
| `NdosClasificaciondeOficio` | `DocumentClassification` | Clasificación del oficio | String |
| `NdosNoficio` | `OficioNumber` | Número del oficio | String |
| `NdosPalabrasClaves` | `KeywordsFound` | Palabras clave encontradas | String |
| `NdosObservaciones` | `Observations` | Observaciones generales | String |

### 👤 CAMPOS DE PERSONA (NDOSPERSONASOCR)

| Campo Creatio | Origen OCR | Descripción | Tipo |
|---------------|------------|-------------|------|
| `NdosNombreCompleto` | `nombre + apellidos` | Nombre completo construido | String |

## 🔄 MAPEO DETALLADO

### 📊 CÓMO SE CONSTRUYEN LOS DATOS

#### 1. **Campos Booleanos**
```python
"NdosSensitivo": payload.get('RequiresUrgentAction', False)
"NdosDirigidoaGlobalBank": payload.get('DirectedToGlobalBank', '').lower() in ['true', 'si', 'yes', '1']
"NdosSellodeAutoridad": bool(payload.get('AuthorityStamp', ''))
```

#### 2. **Campos de Fecha**
```python
"NdosFechadeResolucion": payload.get('ResolutionDate', '')  # Ya formateado como ISO
"NdosVencimiento": payload.get('DueDate', '')
"NdosFechadeRecibido": payload.get('ReceivedDate', '')
"NdosFechadeEmision": payload.get('IssueDate', '')
```

#### 3. **Campos de Texto**
```python
"NdosDelito": payload.get('Crime', '')
"NdosNdeResolucion": payload.get('ResolutionNumber', '')
"NdosCarpeta": payload.get('Folder', '')
"NdosSucursaldeRecibido": payload.get('BranchReceived', '')
"NdosAutoridad": payload.get('Authority', '')
"NdosNoficio": payload.get('OficioNumber', '')
"NdosPalabrasClaves": payload.get('KeywordsFound', '')
"NdosObservaciones": payload.get('Observations', '')
```

#### 4. **Campos Numéricos**
```python
"NdosColumn6": float(payload.get('Amount', 0))
```

#### 5. **Nombre Completo de Persona**
```python
nombre_completo = f"{person_data.get('nombre', '')} {person_data.get('apellido_paterno', '')} {person_data.get('apellido_materno', '')} {person_data.get('nombre_segundo', '')}".strip()
"NdosNombreCompleto": nombre_completo
```

## 📄 EJEMPLO DE DATOS OCR → CREATIO

### 🔍 DATOS EXTRAÍDOS POR OCR
```json
{
  "informacion_extraida": {
    "numero_oficio": "2024-001",
    "autoridad": "Juzgado Civil",
    "fecha_emision": "15/07/2024",
    "fecha_recibido": "20/07/2024",
    "fecha_resolucion": "10/07/2024",
    "numero_resolucion": "RES-2024-001",
    "delito": "Fraude",
    "monto": "B/. 25,000.00",
    "vencimiento": "30/07/2024",
    "carpeta": "CARP-001",
    "sucursal_recibido": "Sucursal Centro",
    "sello_autoridad": "Sello Oficial",
    "dirigido_global_bank": "Si"
  },
  "palabras_clave_encontradas": ["urgente", "fraude", "embargo"],
  "observaciones": "Oficio de alta prioridad"
}
```

### 🏢 DATOS ENVIADOS A CREATIO
```json
{
  "NdosSensitivo": true,
  "NdosDirigidoaGlobalBank": true,
  "NdosSellodeAutoridad": true,
  "NdosDelito": "Fraude",
  "NdosFechadeResolucion": "2024-07-10",
  "NdosNdeResolucion": "RES-2024-001",
  "NdosVencimiento": "2024-07-30",
  "NdosCarpeta": "CARP-001",
  "NdosSucursaldeRecibido": "Sucursal Centro",
  "NdosColumn6": 25000.00,
  "NdosFechadeRecibido": "2024-07-20",
  "NdosFechadeEmision": "2024-07-15",
  "NdosAutoridad": "Juzgado Civil",
  "NdosClasificaciondeOficio": "oficio_general",
  "NdosNoficio": "2024-001",
  "NdosPalabrasClaves": "urgente, fraude, embargo",
  "NdosObservaciones": "Oficio de alta prioridad"
}
```

### 👤 DATOS DE PERSONA
```json
{
  "NdosNombre": "María",
  "NdosApellidoPaterno": "García",
  "NdosApellidoMaterno": "López",
  "NdosNombreSegundo": "Ana",
  "NdosNombreCompleto": "María García López Ana",
  "NdosIdentificacionNumero": "8-123-456",
  "NdosImporte": 12500.00,
  "NdosExpediente": "EXP-2024-001",
  "NdosObservaciones": "Persona extraída por OCR - Secuencia: 1"
}
```

## 🔧 FUNCIONES ACTUALIZADAS

### 1. **`create_case()`**
- Agregado parámetro `case_data_extra`
- Permite enviar campos adicionales al crear el caso

### 2. **`create_person_record()`**
- Agregado campo `NdosNombreCompleto`
- Construye nombre completo automáticamente

### 3. **`create_creatio_request()`**
- Mapea todos los nuevos campos desde el payload
- Convierte tipos de datos apropiadamente

### 4. **`map_ocr_data_to_creatio()`**
- Incluye todos los campos necesarios en el payload
- Asegura que los datos estén disponibles para el mapeo

## 🎯 BENEFICIOS DE LOS NUEVOS CAMPOS

1. **📊 Información Más Completa**: Captura todos los detalles del oficio
2. **🔍 Mejor Clasificación**: Permite categorizar oficios por sensibilidad
3. **📅 Seguimiento Temporal**: Fechas de emisión, recepción, vencimiento
4. **🏢 Información Institucional**: Autoridad, sucursal, carpetas
5. **💰 Datos Financieros**: Montos y resoluciones
6. **👤 Identificación Completa**: Nombre completo de personas

## 🚀 PRÓXIMOS PASOS

1. **Desplegar** los cambios actualizados
2. **Probar** con un oficio real
3. **Verificar** que todos los campos se mapeen correctamente
4. **Validar** que los datos lleguen a Creatio en el formato esperado 