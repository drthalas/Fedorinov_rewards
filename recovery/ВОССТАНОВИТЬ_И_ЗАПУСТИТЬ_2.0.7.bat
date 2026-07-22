@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
where py.exe >nul 2>nul
if errorlevel 1 goto try_python
py -3 "%~dp0service\recovery_v207.py" --service-dir "%~dp0service"
set "RECOVERY_EXIT=%ERRORLEVEL%"
goto recovery_done
:try_python
where python.exe >nul 2>nul
if errorlevel 1 goto python_missing
python "%~dp0service\recovery_v207.py" --service-dir "%~dp0service"
set "RECOVERY_EXIT=%ERRORLEVEL%"
goto recovery_done
:python_missing
echo Python 3.11 or newer is required.
echo Take a photo of this window and send it to Alexander.
pause
exit /b 1
:recovery_done
if "%RECOVERY_EXIT%"=="0" exit /b 0
echo Recovery did not finish. Do not delete any folders.
echo Take a photo of this window and send it to Alexander.
pause
exit /b %RECOVERY_EXIT%
