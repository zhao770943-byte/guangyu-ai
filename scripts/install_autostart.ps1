param(
    [string]$InstallRoot = '',
    [string]$Python = '',
    [switch]$Disable
)
$ErrorActionPreference = 'Stop'
$taskName = 'GuangyuAI-Local-Watchdog'
if (!$InstallRoot) {
    if ((Test-Path -LiteralPath (Join-Path $PSScriptRoot 'launcher.py')) -or (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'GuangyuAI.exe'))) { $InstallRoot = $PSScriptRoot }
    else { $InstallRoot = Split-Path $PSScriptRoot -Parent }
}
if ($Disable) {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-ScheduledTask -TaskName $taskName
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    Write-Output 'Automatic startup disabled. The web service can still be stopped with its normal Stop command.'
    exit
}
$InstallRoot = (Resolve-Path -LiteralPath $InstallRoot).Path
if (Test-Path -LiteralPath (Join-Path $InstallRoot 'GuangyuAI.exe')) {
    $executable = Join-Path $InstallRoot 'GuangyuAI.exe'
    $arguments = '--watchdog --no-browser --keep-awake-ac'
} else {
    if (!$Python) { throw 'Pass -Python with the full path to a Python environment containing requirements.txt dependencies.' }
    $executable = (Resolve-Path -LiteralPath $Python).Path
    $windowless = Join-Path (Split-Path $executable -Parent) 'pythonw.exe'
    if (Test-Path -LiteralPath $windowless) { $executable = $windowless }
    if (!(Test-Path -LiteralPath (Join-Path $InstallRoot 'watchdog.py'))) { throw 'watchdog.py is missing.' }
    $arguments = '-X utf8 "' + (Join-Path $InstallRoot 'watchdog.py') + '" --no-browser --keep-awake-ac'
}
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and $existing.Actions.WorkingDirectory -ne $InstallRoot) { throw 'A supervisor already manages another installation. Disable that task first.' }
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $executable -Argument $arguments -WorkingDirectory $InstallRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Guangyu AI local supervisor. Recover crashes, keep awake on AC, respect explicit stops.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "Installed and started $taskName for $user at $InstallRoot"
