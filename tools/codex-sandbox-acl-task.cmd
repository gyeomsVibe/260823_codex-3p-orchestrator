@echo off
rem 예약 작업용 실행기. 스케줄러 환경에서 나는 오류까지 파일로 남긴다.
set "LOGOUT=%LOCALAPPDATA%\codex-sandbox-acl-task.out"
echo [%DATE% %TIME%] start >> "%LOGOUT%"
"%ProgramFiles%\PowerShell\7\pwsh.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0codex-sandbox-acl-task.ps1" >> "%LOGOUT%" 2>&1
echo [%DATE% %TIME%] exit=%ERRORLEVEL% >> "%LOGOUT%"
