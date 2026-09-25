@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 setup_environment.py
goto done
:try_python
where python >nul 2>&1
if errorlevel 1 goto missing
python setup_environment.py
goto done
:missing
echo Python is not installed or not on PATH. Install Python 3.11 or newer from python.org.
echo Then close this window and double-click Setup first.cmd again.
pause
exit /b 1
:done
if errorlevel 1 goto failed
echo You can now double-click Run morning note.cmd.
pause
exit /b 0
:failed
echo Setup did not complete. See the error above.
pause
exit /b 1
