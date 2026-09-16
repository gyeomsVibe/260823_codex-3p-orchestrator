<#
.SYNOPSIS
  Codex Windows 샌드박스가 저장소에 남긴 권한 항목을 읽기 전용으로 점검한다.

.DESCRIPTION
  이름을 풀 수 없는 SID가 곧 삭제 가능한 고아 권한이라는 보장은 없다. Codex가 관리하는
  유효한 capability SID와 샌드박스 보호 ACE도 Windows UI에서 SID 문자열로 보일 수 있다.
  따라서 이 도구는 ACL을 수정하지 않고 후보를 Codex ledger 등록 여부와 함께 집계한다.

.PARAMETER Mode
  Check  명시적인 S-1-5-21-* 권한 항목 수를 보고한다(기본값). 감사에 성공하면 종료 코드 0.
  Clean  안전성 검증이 되지 않은 이전 호환 인수다. ACL을 바꾸지 않고 종료 코드 3으로 거부한다.

.PARAMETER Paths
  점검할 저장소 경로. 생략하면 이 저장소를 사용한다.

.PARAMETER LogPath
  실행 결과를 한 줄로 덧붙일 로그 파일. 기본값은 %LOCALAPPDATA%\codex-sandbox-acl.log

.PARAMETER CapabilityLedgerPath
  Codex capability SID ledger 경로. 파일을 읽을 수 없으면 ledger 분류만 생략한다.

.EXAMPLE
  pwsh -NoProfile -File tools\codex-sandbox-acl.ps1
  # -Mode Clean은 안전을 위해 차단된다.
#>
[CmdletBinding()]
param(
    [ValidateSet('Check', 'Clean')]
    [string]$Mode = 'Check',
    [string[]]$Paths,
    [string]$LogPath = (Join-Path $env:LOCALAPPDATA 'codex-sandbox-acl.log'),
    [string]$CapabilityLedgerPath = (Join-Path $HOME '.codex\cap_sid')
)

$ErrorActionPreference = 'Stop'

if ($Mode -eq 'Clean') {
    Write-Output 'automatic ACL cleanup is retired: unresolved or SID-shaped entries are not proof that an ACE is obsolete'
    exit 3
}

if (-not $Paths -or $Paths.Count -eq 0) {
    $Paths = @((Resolve-Path (Join-Path $PSScriptRoot '..')).Path)
}

function Get-SidStrings {
    param([object]$Value)

    if ($null -eq $Value) { return }
    if ($Value -is [string]) {
        if ($Value -match '^S-1-\d+(?:-\d+)+$') { $Value }
        return
    }
    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($item in $Value.Values) { Get-SidStrings -Value $item }
        return
    }
    if ($Value -is [System.Collections.IEnumerable]) {
        foreach ($item in $Value) { Get-SidStrings -Value $item }
        return
    }
    foreach ($property in $Value.PSObject.Properties) {
        Get-SidStrings -Value $property.Value
    }
}

$ledgerSids = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
if (Test-Path -LiteralPath $CapabilityLedgerPath) {
    try {
        $ledger = Get-Content -LiteralPath $CapabilityLedgerPath -Raw | ConvertFrom-Json
        foreach ($sid in @(Get-SidStrings -Value $ledger)) { [void]$ledgerSids.Add($sid) }
    }
    catch {
        Write-Output "ledger read failed; continuing without ledger classification: $($_.Exception.Message)"
    }
}

$targets = foreach ($p in $Paths) {
    if (-not (Test-Path -LiteralPath $p)) { continue }
    $p
    $git = Join-Path $p '.git'
    if (Test-Path -LiteralPath $git) { $git }
}

$candidateTotal = 0
$ledgerBackedTotal = 0
$denyTotal = 0
foreach ($t in $targets) {
    $acl = Get-Acl -LiteralPath $t
    $candidates = @($acl.Access | Where-Object {
        -not $_.IsInherited -and $_.IdentityReference.Value -match '^S-1-\d+(?:-\d+)+$'
    })
    $deny = @($candidates | Where-Object { $_.AccessControlType -eq 'Deny' }).Count
    $ledgerBacked = @($candidates | Where-Object { $ledgerSids.Contains($_.IdentityReference.Value) }).Count
    $candidateTotal += $candidates.Count
    $ledgerBackedTotal += $ledgerBacked
    $denyTotal += $deny
    Write-Output "점검: $t SID후보 $($candidates.Count)건(ledger등록 $ledgerBacked, 거부 $deny)"
}

$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$unknownTotal = $candidateTotal - $ledgerBackedTotal
$line = "$stamp mode=$Mode targets=$($targets.Count) sid_candidates=$candidateTotal ledger_backed=$ledgerBackedTotal unclassified=$unknownTotal deny=$denyTotal"
try { Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8 } catch { Write-Output "log write failed: $($_.Exception.Message)" }

if ($candidateTotal -gt 0) {
    Write-Output ''
    Write-Output 'SID 후보는 삭제 지시가 아니다. ledger 등록 여부와 별도 장애 증거를 확인하라.'
}

exit 0
