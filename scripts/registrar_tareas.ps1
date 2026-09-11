# Registra las 2 Tareas Programadas de Gorrolandia (worker al iniciar sesion,
# backup diario a las 3am). Correr una sola vez, desde una PowerShell normal
# tuya (no hace falta "Ejecutar como administrador").
$Raiz = Split-Path -Parent $PSScriptRoot

schtasks.exe /Create /TN "Gorrolandia-Worker" `
    /TR "`"$Raiz\scripts\iniciar_worker.bat`"" /SC ONLOGON /RL LIMITED /F

schtasks.exe /Create /TN "Gorrolandia-BackupDiario" `
    /TR "`"$Raiz\scripts\backup_diario.bat`"" /SC DAILY /ST 03:00 /RL LIMITED /F

Write-Output ""
Write-Output "--- Tareas creadas ---"
schtasks.exe /Query /TN "Gorrolandia-Worker" /FO LIST | Select-String "Nombre de tarea|Estado|Siguiente|Programador"
schtasks.exe /Query /TN "Gorrolandia-BackupDiario" /FO LIST | Select-String "Nombre de tarea|Estado|Siguiente|Programador"
