# 📋 **EJEMPLO DE PÁGINA DE CONFIGURACIÓN PARA S3 DIRECT FLOW**

## **Formato Requerido en la Primera Página del PDF:**

```
┌─────────────────────────────────────────────────────────┐
│                    CONFIGURACIÓN DE LOTE                │
│                                                         │
│ CANTIDAD_OFICIOS:  15                                   │
│ EMPRESA: BANCO GLOBAL                                   │
│ ORIGEN: CHITRE                                          │
│ OBSERVACIONES: Oficios urgentes                         │
│ PROCESADO POR: EDWIN PEÑALBA                            │
│                                                         │
│ Fecha: 2025-01-03                                       │
└─────────────────────────────────────────────────────────┘
```

## **Formato del Separador de Oficios:**

Cada oficio debe estar separado por una página completa con:

```
=====================
SEPARADOR DE OFICIOS
=====================
```

**Importante**: El separador debe estar en una página completa para ser detectado correctamente.

## **Campos Obligatorios:**

- ✅ **CANTIDAD_OFICIOS**: Número de oficios en el lote
- ✅ **EMPRESA**: Nombre de la empresa

## **Campos Opcionales:**

- 📝 **ORIGEN**: Ubicación de origen
- 📝 **OBSERVACIONES**: Comentarios adicionales
- 📝 **PROCESADO POR**: Nombre del operador

## **Ejemplo de Estructura del PDF:**

1. **Página 1**: Configuración (formato arriba)
2. **Página 2**: Oficio 1
3. **Página 3**: Separador de Oficios
4. **Página 4**: Oficio 2
5. **Página 5**: Separador de Oficios
6. **Página 6**: Oficio 3
7. ... y así sucesivamente

## **Validaciones que Realiza el Sistema:**

1. **Extracción de Configuración**: Lee la primera página
2. **Validación de Campos**: Verifica campos obligatorios
3. **Detección de Separadores**: Busca "===================== SEPARADOR DE OFICIOS ====================="
4. **Validación de Cantidad**: Compara declarado vs extraído
5. **Notificación de Errores**: Envía email si falla validación

## **Formato de Notificación de Error:**

Si hay errores, recibirás un email con:
- Detalles del error
- Configuración extraída
- Recomendaciones para corregir
- Información técnica del procesamiento

## **Recomendaciones:**

1. **Usar formato exacto**: Los campos deben estar en mayúsculas
2. **Separadores completos**: Cada separador en su propia página
3. **Cantidad precisa**: La cantidad declarada debe coincidir con los oficios reales
4. **Texto claro**: Evitar caracteres especiales en los nombres de campos