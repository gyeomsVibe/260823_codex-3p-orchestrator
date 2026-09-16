<#
  스케줄러 전용 실행기. 작업 폴더 안의 Git 저장소를 자동으로 찾아 codex-sandbox-acl.ps1 -Mode Clean 을 돌린다.
  새 저장소를 만들어도 따로 등록할 필요가 없다.
  등록 예: schtasks /Create /TN CodexSandboxAclCleanup /TR "pwsh.exe -NoProfile -File <이 파일>" /SC MINUTE /MO 30 /F
#>
[CmdletBinding()]
param(
    [string]$WorkspaceRoot = 'D:\D_Workspace_NB\-agentic-ai-workspace',
    [int]$MaxDepth = 2
)

$ErrorActionPreference = 'Continue'
$cleaner = Join-Path $PSScriptRoot 'codex-sandbox-acl.ps1'
if (-not (Test-Path -LiteralPath $cleaner)) { exit 2 }

$repos = New-Object System.Collections.Generic.List[string]
if (Test-Path -LiteralPath (Join-Path $WorkspaceRoot '.git')) { $repos.Add($WorkspaceRoot) }
Get-ChildItem -LiteralPath $WorkspaceRoot -Directory -Depth ($MaxDepth - 1) -ErrorAction SilentlyContinue |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName '.git') } |
    ForEach-Object { $repos.Add($_.FullName) }

if ($repos.Count -eq 0) { exit 0 }
& $cleaner -Mode Clean -Paths $repos.ToArray()
exit $LASTEXITCODE
