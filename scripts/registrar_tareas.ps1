# Registra las 2 tareas de Gorrolandia para el usuario actual, sin elevacion:
# - worker al iniciar sesion
# - backup diario a las 03:00 (o tan pronto como sea posible si se pierde la hora)
$ErrorActionPreference = "Stop"

$Raiz = Split-Path -Parent $PSScriptRoot
$Usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Cmd = Join-Path $env:SystemRoot "System32\cmd.exe"
$Principal = New-ScheduledTaskPrincipal `
    -UserId $Usuario -LogonType Interactive -RunLevel Limited

function Nueva-AccionBat([string]$RutaBat) {
    New-ScheduledTaskAction -Execute $Cmd -Argument "/d /c `"`"$RutaBat`"`""
}

$RutaWorker = Join-Path $Raiz "scripts\iniciar_worker.bat"
$RutaBackup = Join-Path $Raiz "scripts\backup_diario.bat"

if (-not (Test-Path -LiteralPath $RutaWorker)) {
    throw "No existe el lanzador del worker: $RutaWorker"
}
if (-not (Test-Path -LiteralPath $RutaBackup)) {
    throw "No existe el lanzador del backup: $RutaBackup"
}

$AjustesWorker = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$AjustesBackup = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

# Delay de 1 minuto: un LogonTrigger sin retraso puede dispararse antes de
# que el escritorio/window station termine de estabilizarse tras un arranque
# en frio, matando al proceso con STATUS_CONTROL_C_EXIT (-1073741510) casi
# de inmediato - confirmado en un reinicio real de prueba (el "Ultimo
# resultado" de la tarea mostraba justo ese codigo). El RestartOnFailure de
# 3 intentos no lo compensaba en la practica.
$TriggerWorker = New-ScheduledTaskTrigger -AtLogOn -User $Usuario
$TriggerWorker.Delay = "PT1M"

Register-ScheduledTask `
    -TaskName "Gorrolandia-Worker" `
    -Action (Nueva-AccionBat $RutaWorker) `
    -Trigger $TriggerWorker `
    -Principal $Principal `
    -Settings $AjustesWorker `
    -Force | Out-Null

Register-ScheduledTask `
    -TaskName "Gorrolandia-BackupDiario" `
    -Action (Nueva-AccionBat $RutaBackup) `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "03:00") `
    -Principal $Principal `
    -Settings $AjustesBackup `
    -Force | Out-Null

Write-Output ""
Write-Output "--- Tareas registradas ---"
Get-ScheduledTask -TaskName "Gorrolandia-Worker", "Gorrolandia-BackupDiario" |
    Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName "Gorrolandia-BackupDiario" |
    Select-Object NextRunTime, LastRunTime, LastTaskResult
