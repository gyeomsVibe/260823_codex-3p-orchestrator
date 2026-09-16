@echo off
rem Read-only Codex sandbox ACL audit wrapper for Task Scheduler.
set "LOGOUT=%LOCALAPPDATA%\codex-sandbox-acl-task.out"
echo [%DATE% %TIME%] start >> "%LOGOUT%"
"%ProgramFiles%\PowerShell\7\pwsh.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0codex-sandbox-acl-task.ps1" >> "%LOGOUT%" 2>&1
set "TASK_EXIT=%ERRORLEVEL%"
echo [%DATE% %TIME%] exit=%TASK_EXIT% >> "%LOGOUT%"
exit /b %TASK_EXIT%
