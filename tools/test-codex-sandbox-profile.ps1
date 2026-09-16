<#
.SYNOPSIS
  Codex 네이티브 Windows 샌드박스의 핵심 경계를 실제 명령으로 회귀 검사한다.

.DESCRIPTION
  자신이 만든 임시 파일만 사용하고 종료 전에 제거한다. 작업공간·사용자 임시 폴더는
  쓸 수 있어야 하며, 홈·Windows 임시 폴더·.git·네트워크 쓰기 경계는 막혀야 한다.
#>
[CmdletBinding()]
param(
    [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$PermissionProfile = ':workspace'
)

$ErrorActionPreference = 'Stop'
$testId = [guid]::NewGuid().ToString('N')
$testPaths = @{
    Workspace = Join-Path $RepoPath ".sandbox-test-$testId.tmp"
    Home = Join-Path $env:USERPROFILE ".codex-sandbox-test-$testId.tmp"
    SystemTemp = Join-Path $env:WINDIR "Temp\codex-sandbox-test-$testId.tmp"
    UserTemp = Join-Path $env:TEMP "codex-sandbox-test-$testId.tmp"
    Git = Join-Path $RepoPath ".git\codex-sandbox-test-$testId.tmp"
}

function Invoke-SandboxCase {
    param(
        [string]$Name,
        [string]$Script,
        [ValidateSet('zero', 'nonzero')]
        [string]$Expected
    )

    $caseOutput = & codex sandbox --permission-profile $PermissionProfile -C $RepoPath pwsh -NoProfile -Command $Script 2>&1
    $caseExit = $LASTEXITCODE
    $passed = if ($Expected -eq 'zero') { $caseExit -eq 0 } else { $caseExit -ne 0 }
    [pscustomobject]@{
        Case = $Name
        Exit = $caseExit
        Expected = $Expected
        Pass = $passed
        Detail = if ($passed) { '' } else { (@($caseOutput)[-1] -replace '\s+', ' ') }
    }
}

try {
    $results = @()
    $workspacePath = $testPaths.Workspace.Replace("'", "''")
    $userTempPath = $testPaths.UserTemp.Replace("'", "''")
    $homePath = $testPaths.Home.Replace("'", "''")
    $systemTempPath = $testPaths.SystemTemp.Replace("'", "''")
    $gitPath = $testPaths.Git.Replace("'", "''")

    $results += Invoke-SandboxCase 'workspace-write' "Set-Content -LiteralPath '$workspacePath' -Value ok; Remove-Item -LiteralPath '$workspacePath'" zero
    $results += Invoke-SandboxCase 'user-temp-write' "Set-Content -LiteralPath '$userTempPath' -Value ok; Remove-Item -LiteralPath '$userTempPath'" zero
    $results += Invoke-SandboxCase 'home-write-blocked' "Set-Content -LiteralPath '$homePath' -Value blocked" nonzero
    $results += Invoke-SandboxCase 'windows-temp-blocked' "Set-Content -LiteralPath '$systemTempPath' -Value blocked" nonzero
    $results += Invoke-SandboxCase 'git-metadata-blocked' "Set-Content -LiteralPath '$gitPath' -Value blocked" nonzero
    $results += Invoke-SandboxCase 'network-blocked' 'curl.exe --silent --show-error --max-time 5 --head https://example.com | Out-Null' nonzero
    $results += Invoke-SandboxCase 'git-read-quiet' 'git status --short 2>&1 | Where-Object { $_ -match ''^warning:'' } | ForEach-Object { Write-Error $_ }; if ($Error.Count) { exit 1 }' zero

    $results | Format-Table -AutoSize
    if (@($results | Where-Object { -not $_.Pass }).Count -gt 0) { exit 1 }
    exit 0
}
finally {
    foreach ($testPath in $testPaths.Values) {
        if (Test-Path -LiteralPath $testPath) { Remove-Item -LiteralPath $testPath -Force }
    }
}
