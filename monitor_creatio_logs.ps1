# Script de PowerShell para monitorear logs de Creatio CRM
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "📊 MONITOR DE LOGS DE CREATIO CRM EN TIEMPO REAL" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "🔍 Monitoreando logs de la función CRM Integrator..." -ForegroundColor Yellow
Write-Host "💡 Presiona Ctrl+C para detener" -ForegroundColor Yellow
Write-Host ""

# Verificar si AWS CLI está instalado
try {
    $awsVersion = aws --version 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI no encontrado"
    }
    Write-Host "✅ AWS CLI encontrado: $awsVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ AWS CLI no está instalado o no está en el PATH" -ForegroundColor Red
    Write-Host "💡 Instala AWS CLI desde: https://aws.amazon.com/cli/" -ForegroundColor Yellow
    Read-Host "Presiona Enter para salir"
    exit 1
}

# Verificar configuración de AWS
try {
    aws sts get-caller-identity 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "AWS no configurado"
    }
    Write-Host "✅ AWS configurado correctamente" -ForegroundColor Green
} catch {
    Write-Host "❌ AWS no está configurado correctamente" -ForegroundColor Red
    Write-Host "💡 Ejecuta: aws configure" -ForegroundColor Yellow
    Read-Host "Presiona Enter para salir"
    exit 1
}

Write-Host ""
Write-Host "🚀 Iniciando monitoreo de logs..." -ForegroundColor Green
Write-Host ""

# Monitorear logs en tiempo real
try {
    aws logs tail /aws/lambda/ocr-sam-stack-crm-integrator --follow --filter-pattern "DATOS EXTRAÍDOS DEL OCR OR DATOS ESPECÍFICOS ENVIADOS A CREATIO OR CASO CREADO EXITOSAMENTE OR Schema-compatible integration SUCCESS"
} catch {
    Write-Host "❌ Error monitoreando logs: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "💡 Verifica que el log group exista y tengas permisos" -ForegroundColor Yellow
}

Read-Host "Presiona Enter para salir"
