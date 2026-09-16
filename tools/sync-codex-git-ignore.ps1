<#
.SYNOPSIS
  샌드박스가 읽을 수 있는 사용자 임시 폴더에 Git 전역 ignore 사본을 유지한다.

.DESCRIPTION
  Git 인증·전역 config는 복사하지 않는다. ignore 패턴 파일 하나만 동기화하며,
  원본이 없으면 빈 파일을 만든다. 내용이 같으면 대상 파일을 다시 쓰지 않는다.
#>
[CmdletBinding()]
param(
    [string]$SourcePath = (Join-Path $HOME '.config\git\ignore'),
    [string]$DestinationPath = (Join-Path $env:LOCALAPPDATA 'Temp\codex-git-ignore\ignore')
)

$ErrorActionPreference = 'Stop'
$destinationDirectory = Split-Path -Parent $DestinationPath
New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null

if (-not (Test-Path -LiteralPath $SourcePath)) {
    if (-not (Test-Path -LiteralPath $DestinationPath)) {
        New-Item -ItemType File -Path $DestinationPath | Out-Null
    }
    exit 0
}

$copyRequired = -not (Test-Path -LiteralPath $DestinationPath)
if (-not $copyRequired) {
    $sourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash
    $destinationHash = (Get-FileHash -LiteralPath $DestinationPath -Algorithm SHA256).Hash
    $copyRequired = $sourceHash -ne $destinationHash
}

if ($copyRequired) {
    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
}

exit 0
