# Arranca fase8_worker_ingesta.py en segundo plano (sin ventana visible) y
# redirige toda su salida a output/logs/worker.log - pensado para que lo
# llame la Tarea Programada "Gorrolandia-Worker" (trigger: al iniciar
# sesion), no para correrlo a mano (para eso, corre el .py directamente y
# ve la salida en tu propia terminal).
$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Raiz ".venv\Scripts\python.exe"
$Script = Join-Path $Raiz "src\fase8_worker_ingesta.py"
$CarpetaLogs = Join-Path $Raiz "output\logs"
$ArchivoLog = Join-Path $CarpetaLogs "worker.log"

New-Item -ItemType Directory -Force -Path $CarpetaLogs | Out-Null

Set-Location (Join-Path $Raiz "src")

$marca = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $ArchivoLog -Value "`n=== [$marca] iniciando worker (Tarea Programada) ==="

# redireccion via cmd.exe, no la de PowerShell (*>>) - ver backup_diario.ps1
# para el detalle de por que (evita que PowerShell recodifique mal el log).
& cmd.exe /c "`"$Python`" `"$Script`" >> `"$ArchivoLog`" 2>&1"
