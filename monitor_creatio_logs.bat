@echo off
echo ================================================================================
echo 📊 MONITOR DE LOGS DE CREATIO CRM EN TIEMPO REAL
echo ================================================================================
echo.
echo 🔍 Monitoreando logs de la función CRM Integrator...
echo 💡 Presiona Ctrl+C para detener
echo.

REM Verificar si AWS CLI está instalado
aws --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ AWS CLI no está instalado o no está en el PATH
    echo 💡 Instala AWS CLI desde: https://aws.amazon.com/cli/
    pause
    exit /b 1
)

REM Verificar configuración de AWS
aws sts get-caller-identity >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ AWS no está configurado correctamente
    echo 💡 Ejecuta: aws configure
    pause
    exit /b 1
)

echo ✅ AWS CLI configurado correctamente
echo.

REM Monitorear logs en tiempo real
echo 🚀 Iniciando monitoreo de logs...
echo.
aws logs tail /aws/lambda/ocr-sam-stack-crm-integrator --follow --filter-pattern "DATOS EXTRAÍDOS DEL OCR OR DATOS ESPECÍFICOS ENVIADOS A CREATIO OR CASO CREADO EXITOSAMENTE OR Schema-compatible integration SUCCESS"

pause
