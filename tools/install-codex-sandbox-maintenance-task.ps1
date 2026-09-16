<#
.SYNOPSIS
  Codex 샌드박스 유지관리 작업을 로그온 시점과 30분 간격으로 등록한다.
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'CodexSandboxUpdateMaintenance',
    [string]$LegacyTaskName = 'CodexSandboxAclCleanup',
    [int]$IntervalMinutes = 30
)

$ErrorActionPreference = 'Stop'
$wrapper = (Resolve-Path (Join-Path $PSScriptRoot 'codex-sandbox-maintenance-task.cmd')).Path
$stateDirectory = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path '.codex-sandbox-maintenance'
$backupDirectory = Join-Path $stateDirectory 'task-backups'
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null

$legacy = Get-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue
if ($null -ne $legacy) {
    $backupPath = Join-Path $backupDirectory ($LegacyTaskName + '.' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.xml')
    Export-ScheduledTask -TaskName $LegacyTaskName | Set-Content -LiteralPath $backupPath -Encoding Unicode
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $wrapper
$intervalTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($logonTrigger, $intervalTrigger) -Principal $principal -Settings $settings -Description 'Detect Codex or Windows updates, revalidate sandbox boundaries, restore managed support files, and audit ACLs without mutation.' -Force | Out-Null

$registered = Get-ScheduledTask -TaskName $TaskName
if ($registered.Actions.Execute -ne $wrapper) { throw 'registered task action does not match the maintenance wrapper' }

if ($null -ne $legacy -and $LegacyTaskName -ne $TaskName) {
    Unregister-ScheduledTask -TaskName $LegacyTaskName -Confirm:$false
}

Write-Output "registered task=$TaskName interval_minutes=$IntervalMinutes logon_trigger=true legacy_removed=$($null -ne $legacy -and $LegacyTaskName -ne $TaskName)"
