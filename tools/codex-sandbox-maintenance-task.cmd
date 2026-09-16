@echo off
rem Codex sandbox update maintenance wrapper for Task Scheduler.
set "LOGOUT=%~dp0..\.codex-sandbox-maintenance\maintenance-task.out"
if not exist "%~dp0..\.codex-sandbox-maintenance" mkdir "%~dp0..\.codex-sandbox-maintenance"
if exist "%LOGOUT%" for %%A in ("%LOGOUT%") do if %%~zA GTR 1048576 move /Y "%LOGOUT%" "%LOGOUT%.previous" >nul
echo [%DATE% %TIME%] start >> "%LOGOUT%"
"%ProgramFiles%\PowerShell\7\pwsh.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0codex-sandbox-maintenance-task.ps1" >> "%LOGOUT%" 2>&1
set "TASK_EXIT=%ERRORLEVEL%"
echo [%DATE% %TIME%] exit=%TASK_EXIT% >> "%LOGOUT%"
exit /b %TASK_EXIT%
