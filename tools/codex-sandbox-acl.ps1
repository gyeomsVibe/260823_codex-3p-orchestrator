<#
.SYNOPSIS
  Codex Windows 샌드박스가 저장소에 남기는 오래된 권한 항목을 점검하고 정리한다.

.DESCRIPTION
  Codex 샌드박스는 실행할 때마다 임시 계정을 만들고 .git 폴더에 거부(DENY) 권한을 건다.
  종료할 때 이를 지우지 않아 실행할수록 쌓이고, 계정이 삭제되면 이름이 풀리지 않는
  고아 SID 로 남는다. 그 상태에서 샌드박스로 git 을 쓰면 .git/index.lock 생성이 막힌다.
  이 스크립트는 상속되지 않은(=명시적으로 붙은) S-1-5-21-* 항목만 제거한다.
  계정 이름을 찾을 수 없어 icacls /remove 가 오류 1332 로 실패하므로 SID 를 직접 다룬다.

.PARAMETER Mode
  Check  현재 남아 있는 거부·고아 권한 개수만 보고한다(기본값).
  Clean  고아 SID 항목을 제거한다.

.PARAMETER Paths
  점검할 저장소 경로. 생략하면 이 저장소를 사용한다.

.EXAMPLE
  pwsh -NoProfile -File tools\codex-sandbox-acl.ps1
  pwsh -NoProfile -File tools\codex-sandbox-acl.ps1 -Mode Clean
#>
[CmdletBinding()]
param(
    [ValidateSet('Check', 'Clean')]
    [string]$Mode = 'Check',
    [string[]]$Paths
)

$ErrorActionPreference = 'Stop'

if (-not $Paths -or $Paths.Count -eq 0) {
    $Paths = @((Resolve-Path (Join-Path $PSScriptRoot '..')).Path)
}

$targets = foreach ($p in $Paths) {
    $p
    $git = Join-Path $p '.git'
    if (Test-Path -LiteralPath $git) { $git }
}

$staleTotal = 0
foreach ($t in $targets) {
    $acl = Get-Acl -LiteralPath $t
    $stale = @($acl.Access | Where-Object { -not $_.IsInherited -and $_.IdentityReference.Value -like 'S-1-5-21-*' })
    $deny = @($stale | Where-Object { $_.AccessControlType -eq 'Deny' }).Count
    $staleTotal += $stale.Count

    if ($Mode -eq 'Clean' -and $stale.Count -gt 0) {
        foreach ($rule in $stale) { [void]$acl.RemoveAccessRuleSpecific($rule) }
        Set-Acl -LiteralPath $t -AclObject $acl
        Write-Output "정리: $t 에서 $($stale.Count)건 제거(거부 $deny 건 포함)"
    }
    else {
        Write-Output "점검: $t 고아항목 $($stale.Count)건(거부 $deny 건)"
    }
}

if ($Mode -eq 'Check' -and $staleTotal -gt 0) {
    Write-Output ''
    Write-Output "정리하려면: pwsh -NoProfile -File $PSCommandPath -Mode Clean"
    exit 1
}

exit 0
