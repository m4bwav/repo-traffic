# Registers a Windows scheduled task that runs repo_traffic.py every 13 days.
# GitHub keeps traffic for 14 days, so 13 leaves a day of overlap.
# If the PC is off at the scheduled time, the task runs at the next start.
# Usage: pwsh -File install-task.ps1 [-Days 13] [-At 09:00] [-Name repo-traffic]
param(
    [int]$Days = 13,
    [string]$At = "09:00",
    [string]$Name = "repo-traffic"
)
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "repo_traffic.py"
$python = (Get-Command python).Source
# pythonw runs without a console window.
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`"" -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -DaysInterval $Days -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings `
    -Description "Snapshot GitHub traffic and package downloads (repo_traffic.py)" -Force | Out-Null
Get-ScheduledTask -TaskName $Name | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime
