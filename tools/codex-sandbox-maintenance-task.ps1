<#
  스케줄러 전용 샌드박스 유지관리 실행기. Codex·Windows 업데이트를 감지해 경계를
  재검증하고, 작업 폴더 안의 Git 저장소를 찾아 읽기 전용 ACL 감사를 실행한다.
  새 저장소를 만들어도 따로 등록할 필요가 없다.
  ACL을 정리하거나 사용자 config.toml을 덮어쓰지 않는다.
#>
[CmdletBinding()]
param(
    [string]$WorkspaceRoot = 'D:\D_Workspace_NB\-agentic-ai-workspace',
    [int]$MaxDepth = 2
)

$ErrorActionPreference = 'Continue'
$updateGuard = Join-Path $PSScriptRoot 'maintain-codex-sandbox-after-updates.ps1'
$gitIgnoreSync = Join-Path $PSScriptRoot 'sync-codex-git-ignore.ps1'
$cleaner = Join-Path $PSScriptRoot 'codex-sandbox-acl.ps1'
if (-not (Test-Path -LiteralPath $updateGuard) -or -not (Test-Path -LiteralPath $cleaner) -or -not (Test-Path -LiteralPath $gitIgnoreSync)) { exit 2 }

& $updateGuard
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $gitIgnoreSync
if ($LASTEXITCODE -ne 0) { exit 2 }

$repos = New-Object System.Collections.Generic.List[string]
if (Test-Path -LiteralPath (Join-Path $WorkspaceRoot '.git')) { $repos.Add($WorkspaceRoot) }
Get-ChildItem -LiteralPath $WorkspaceRoot -Directory -Depth ($MaxDepth - 1) -ErrorAction SilentlyContinue |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName '.git') } |
    ForEach-Object { $repos.Add($_.FullName) }

if ($repos.Count -eq 0) { exit 0 }
& $cleaner -Mode Check -Paths $repos.ToArray()
exit $LASTEXITCODE
