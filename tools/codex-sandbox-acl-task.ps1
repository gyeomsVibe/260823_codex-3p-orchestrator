<#
  스케줄러 전용 읽기 전용 감사 실행기. 작업 폴더 안의 Git 저장소를 자동으로 찾아
  codex-sandbox-acl.ps1 -Mode Check 를 돌린다.
  새 저장소를 만들어도 따로 등록할 필요가 없다.
  기존 예약 작업 이름 CodexSandboxAclCleanup은 호환을 위해 유지되지만 ACL을 정리하지 않는다.
#>
[CmdletBinding()]
param(
    [string]$WorkspaceRoot = 'D:\D_Workspace_NB\-agentic-ai-workspace',
    [int]$MaxDepth = 2
)

$ErrorActionPreference = 'Continue'
$gitIgnoreSync = Join-Path $PSScriptRoot 'sync-codex-git-ignore.ps1'
$cleaner = Join-Path $PSScriptRoot 'codex-sandbox-acl.ps1'
if (-not (Test-Path -LiteralPath $cleaner) -or -not (Test-Path -LiteralPath $gitIgnoreSync)) { exit 2 }

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
