# Corre fase8_backup_db.py (backup seguro + poda de backups viejos) -
# pensado para la Tarea Programada "Gorrolandia-BackupDiario" (trigger:
# diario). No requiere que el worker este detenido - la API de backup de
# sqlite3 es segura de correr sobre una base viva.
$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Raiz ".venv\Scripts\python.exe"
$Script = Join-Path $Raiz "src\fase8_backup_db.py"
$CarpetaLogs = Join-Path $Raiz "output\logs"
$ArchivoLog = Join-Path $CarpetaLogs "backup.log"

New-Item -ItemType Directory -Force -Path $CarpetaLogs | Out-Null

Set-Location (Join-Path $Raiz "src")

$marca = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $ArchivoLog -Value "`n=== [$marca] backup diario ==="

# redireccion via cmd.exe, no la de PowerShell (*>>) - PowerShell reinterpreta
# el stream de salida como texto y lo puede recodificar mal (UTF-16 con un
# espacio entre cada caracter); cmd.exe hace redireccion de bytes cruda, sin
# tocar la codificacion que Python ya escribe.
& cmd.exe /c "`"$Python`" `"$Script`" >> `"$ArchivoLog`" 2>&1"
