<#
.SYNOPSIS
  Codex Windows 샌드박스가 저장소에 남기는 오래된 권한 항목을 점검하고 정리한다.

.DESCRIPTION
  Codex 샌드박스는 실행할 때마다 임시 계정을 만들고 .git 폴더에 거부(DENY) 권한을 건다.
  종료할 때 이를 지우지 않아 실행할수록 쌓이고, 계정이 삭제되면 이름이 풀리지 않는
  고아 SID 로 남는다. 실측상 샌드박스 실행 1회마다 저장소당 2~3건이 추가된다.
  이 스크립트는 상속되지 않은(=명시적으로 붙은) S-1-5-21-* 항목만 제거한다.
  계정 이름을 찾을 수 없어 icacls /remove 가 오류 1332 로 실패하므로 SID 를 직접 다룬다.

  주의: .git 쓰기 거부 자체는 샌드박스의 설계 동작이다. 청소해도 샌드박스 안에서는
  git 쓰기가 계속 막힌다. 이 스크립트의 목적은 권한 항목이 무한히 누적되는 것을 막는 것이다.

.PARAMETER Mode
  Check  남아 있는 거부·고아 권한 개수만 보고한다(기본값). 1건이라도 있으면 종료 코드 1.
  Clean  고아 SID 항목을 제거한다.

.PARAMETER Paths
  점검할 저장소 경로. 생략하면 이 저장소를 사용한다.

.PARAMETER LogPath
  실행 결과를 한 줄로 덧붙일 로그 파일. 기본값은 %LOCALAPPDATA%\codex-sandbox-acl.log

.EXAMPLE
  pwsh -NoProfile -File tools\codex-sandbox-acl.ps1
  pwsh -NoProfile -File tools\codex-sandbox-acl.ps1 -Mode Clean
#>
[CmdletBinding()]
param(
    [ValidateSet('Check', 'Clean')]
    [string]$Mode = 'Check',
    [string[]]$Paths,
    [string]$LogPath = (Join-Path $env:LOCALAPPDATA 'codex-sandbox-acl.log')
)

$ErrorActionPreference = 'Stop'

if (-not $Paths -or $Paths.Count -eq 0) {
    $Paths = @((Resolve-Path (Join-Path $PSScriptRoot '..')).Path)
}

$targets = foreach ($p in $Paths) {
    if (-not (Test-Path -LiteralPath $p)) { continue }
    $p
    $git = Join-Path $p '.git'
    if (Test-Path -LiteralPath $git) { $git }
}

$staleTotal = 0
$denyTotal = 0
foreach ($t in $targets) {
    $acl = Get-Acl -LiteralPath $t
    $stale = @($acl.Access | Where-Object { -not $_.IsInherited -and $_.IdentityReference.Value -like 'S-1-5-21-*' })
    $deny = @($stale | Where-Object { $_.AccessControlType -eq 'Deny' }).Count
    $staleTotal += $stale.Count
    $denyTotal += $deny

    if ($Mode -eq 'Clean' -and $stale.Count -gt 0) {
        foreach ($rule in $stale) { [void]$acl.RemoveAccessRuleSpecific($rule) }
        Set-Acl -LiteralPath $t -AclObject $acl
        Write-Output "정리: $t 에서 $($stale.Count)건 제거(거부 $deny 건 포함)"
    }
    else {
        Write-Output "점검: $t 고아항목 $($stale.Count)건(거부 $deny 건)"
    }
}

$stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$line = "$stamp mode=$Mode targets=$($targets.Count) stale=$staleTotal deny=$denyTotal"
try { Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8 } catch { }

if ($Mode -eq 'Check' -and $staleTotal -gt 0) {
    Write-Output ''
    Write-Output "정리하려면: pwsh -NoProfile -File $PSCommandPath -Mode Clean"
    exit 1
}

exit 0
