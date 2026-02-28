# Restart Script for RocotoClip
# Detiene todos los procesos de Python y Node relacionados con el proyecto y reinicia el servidor.

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "DETENIENDO SERVICIOS ROCOTOCLIP..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Detener Python (Servidor y Pipelines)
Write-Host "[1/4] Finalizando procesos de Python..." -ForegroundColor Yellow
$pyProcs = Get-WmiObject Win32_Process -Filter "Name = 'python.exe' AND CommandLine LIKE '%server.py%'"
if ($pyProcs) {
    $pyProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Write-Host "      Servidor detenido." -ForegroundColor Green
} else {
    Write-Host "      No se detectaron servidores activos." -ForegroundColor DarkGray
}

# 2. Detener Node (Frontend)
Write-Host "[2/4] Finalizando procesos de Node (Frontend)..." -ForegroundColor Yellow
$nodeProcs = Get-Process node -ErrorAction SilentlyContinue
if ($nodeProcs) {
    Stop-Process -Name node -Force
    Write-Host "      Node finalizado." -ForegroundColor Green
} else {
    Write-Host "      No se detectaron procesos de Node." -ForegroundColor DarkGray
}

# 3. Limpiar temporales si es necesario (Opcional)
Write-Host "[3/4] Inicializando sistema..." -ForegroundColor Yellow
Start-Sleep -Seconds 1

# 4. Reiniciar Servidor
Write-Host "[4/4] REINICIANDO SERVIDOR PRINCIPAL..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python server.py"
Write-Host "      Servidor Python lanzado en nueva ventana." -ForegroundColor Green

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "SISTEMA LISTO. REGRESA AL NAVEGADOR." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
