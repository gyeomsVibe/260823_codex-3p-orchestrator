<#
.SYNOPSIS
  Codex 또는 Windows 업데이트를 감지하고 샌드박스 경계를 다시 검증한다.

.DESCRIPTION
  Codex 버전과 Windows 빌드를 마지막 정상 검증 상태와 비교한다. 버전이 바뀌면 전체
  샌드박스 회귀 검사를 실행한다. 저장소가 관리하는 Git 경계 규칙은 안전하게 동기화한다.
  사용자 config.toml은 읽기만 하며 자동으로 덮어쓰지 않는다.
#>
[CmdletBinding()]
param(
    [string]$StatePath = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..')).Path '.codex-sandbox-maintenance\state.json'),
    [string]$ConfigPath = (Join-Path $HOME '.codex\config.toml'),
    [string]$RuleSourcePath = (Resolve-Path (Join-Path $PSScriptRoot '..\config\codex\sandbox-git-boundary.rules')).Path,
    [string]$RuleDestinationPath = (Join-Path $HOME '.codex\rules\sandbox-git-boundary.rules'),
    [string]$RegressionScriptPath = (Join-Path $PSScriptRoot 'test-codex-sandbox-profile.ps1'),
    [string]$RegressionArgument,
    [string]$CodexVersionOverride,
    [string]$WindowsVersionOverride,
    [int]$ValidationIntervalHours = 24,
    [switch]$ForceValidation
)

$ErrorActionPreference = 'Stop'

function Get-TomlStringValue {
    param([string]$Content, [string]$Key)
    $escaped = [regex]::Escape($Key)
    $pattern = '(?m)^\s*{0}\s*=\s*["'']([^"'']+)["'']\s*(?:#.*)?$' -f $escaped
    $match = [regex]::Match($Content, $pattern)
    if ($match.Success) { return $match.Groups[1].Value }
    return $null
}

function Write-StateAtomically {
    param([object]$State, [string]$Path)
    $directory = Split-Path -Parent $Path
    if ([string]::IsNullOrWhiteSpace($directory)) { $directory = '.' }
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = Join-Path $directory ('.state-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

$previous = $null
if (Test-Path -LiteralPath $StatePath) {
    try { $previous = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json }
    catch { $previous = $null }
}

trap {
    $failureState = [ordered]@{
        schemaVersion = 1
        checkedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
        healthy = $false
        updateDetected = $true
        current = [ordered]@{
            codexVersion = $codexVersion
            windowsVersion = $windowsVersion
        }
        lastValidated = if ($null -ne $previous) { $previous.lastValidated } else { $null }
        checks = [ordered]@{
            operational = $false
            errorType = $_.Exception.GetType().FullName
        }
    }
    try { Write-StateAtomically -State $failureState -Path $StatePath } catch { }
    Write-Output "sandbox-maintenance operational_error=$($_.Exception.Message)"
    exit 20
}

$codexVersion = $CodexVersionOverride
if ([string]::IsNullOrWhiteSpace($codexVersion)) {
    $codexOutput = & codex --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "codex --version failed with exit code $LASTEXITCODE" }
    $codexVersion = (@($codexOutput) -join ' ').Trim()
}

$windowsVersion = $WindowsVersionOverride
if ([string]::IsNullOrWhiteSpace($windowsVersion)) {
    $windows = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
    $windowsVersion = "$($windows.CurrentBuild).$($windows.UBR)"
}

$checks = [ordered]@{
    config = $false
    ruleSync = $false
    regression = $null
}

$configContent = if (Test-Path -LiteralPath $ConfigPath) {
    Get-Content -LiteralPath $ConfigPath -Raw
} else { '' }
$hasLegacySandboxMode = [regex]::IsMatch($configContent, '(?m)^\s*sandbox_mode\s*=')
$hasLegacyWorkspaceTable = [regex]::IsMatch($configContent, '(?m)^\s*\[sandbox_workspace_write\]\s*$')
$checks.config =
    (Get-TomlStringValue $configContent 'approval_policy') -eq 'on-request' -and
    (Get-TomlStringValue $configContent 'default_permissions') -eq ':workspace' -and
    (Get-TomlStringValue $configContent 'approvals_reviewer') -eq 'auto_review' -and
    -not $hasLegacySandboxMode -and
    -not $hasLegacyWorkspaceTable

if (-not (Test-Path -LiteralPath $RuleSourcePath)) { throw "managed rule source is missing: $RuleSourcePath" }
$ruleDirectory = Split-Path -Parent $RuleDestinationPath
New-Item -ItemType Directory -Path $ruleDirectory -Force | Out-Null
$ruleNeedsSync = -not (Test-Path -LiteralPath $RuleDestinationPath)
if (-not $ruleNeedsSync) {
    $sourceHash = (Get-FileHash -LiteralPath $RuleSourcePath -Algorithm SHA256).Hash
    $destinationHash = (Get-FileHash -LiteralPath $RuleDestinationPath -Algorithm SHA256).Hash
    $ruleNeedsSync = $sourceHash -ne $destinationHash
}
if ($ruleNeedsSync) {
    if (Test-Path -LiteralPath $RuleDestinationPath) {
        $backupDirectory = Join-Path (Split-Path -Parent $StatePath) 'backups'
        New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
        $backupName = 'sandbox-git-boundary.' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.rules.bak'
        Copy-Item -LiteralPath $RuleDestinationPath -Destination (Join-Path $backupDirectory $backupName)
    }
    Copy-Item -LiteralPath $RuleSourcePath -Destination $RuleDestinationPath -Force
}
$checks.ruleSync = (Get-FileHash -LiteralPath $RuleSourcePath -Algorithm SHA256).Hash -eq
    (Get-FileHash -LiteralPath $RuleDestinationPath -Algorithm SHA256).Hash

$lastValidated = if ($null -ne $previous) { $previous.lastValidated } else { $null }
$updateDetected =
    $null -eq $lastValidated -or
    $lastValidated.codexVersion -ne $codexVersion -or
    $lastValidated.windowsVersion -ne $windowsVersion
$lastValidationTime = [datetime]::MinValue
if ($null -ne $lastValidated -and $null -ne $lastValidated.validatedAtUtc) {
    [void][datetime]::TryParse($lastValidated.validatedAtUtc.ToString(), [ref]$lastValidationTime)
}
$validationExpired = $lastValidationTime -lt (Get-Date).ToUniversalTime().AddHours(-$ValidationIntervalHours)
$needsRegression = $ForceValidation -or $updateDetected -or $validationExpired

if ($needsRegression) {
    if (-not (Test-Path -LiteralPath $RegressionScriptPath)) { throw "regression script is missing: $RegressionScriptPath" }
    if ([string]::IsNullOrWhiteSpace($RegressionArgument)) {
        & $RegressionScriptPath
    } else {
        & $RegressionScriptPath $RegressionArgument
    }
    $checks.regression = $LASTEXITCODE -eq 0
} else {
    $checks.regression = $true
}

$healthy = $checks.config -and $checks.ruleSync -and $checks.regression
if ($healthy) {
    $lastValidated = [ordered]@{
        codexVersion = $codexVersion
        windowsVersion = $windowsVersion
        validatedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    }
}

$state = [ordered]@{
    schemaVersion = 1
    checkedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
    healthy = [bool]$healthy
    updateDetected = [bool]$updateDetected
    validationExpired = [bool]$validationExpired
    current = [ordered]@{
        codexVersion = $codexVersion
        windowsVersion = $windowsVersion
    }
    lastValidated = $lastValidated
    checks = $checks
}
Write-StateAtomically -State $state -Path $StatePath

Write-Output "sandbox-maintenance healthy=$healthy update_detected=$updateDetected codex=$codexVersion windows=$windowsVersion state_path=$StatePath"
if (-not $healthy) {
    Write-Output "checks config=$($checks.config) rule_sync=$($checks.ruleSync) regression=$($checks.regression)"
    exit 10
}
exit 0
