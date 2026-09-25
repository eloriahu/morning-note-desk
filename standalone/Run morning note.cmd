@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" morning_note.py run --open
if errorlevel 1 pause
exit /b
:missing
echo First double-click Setup first.cmd to prepare this computer.
pause
exit /b 1
