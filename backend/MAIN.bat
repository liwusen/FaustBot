@echo off
cd /d "%~dp0"
title FAUST Backend MAIN Service
echo FAUST Backend MAIN Service Starting...
call "%~dp0..\use-runtime.bat" || exit /b 1
echo Using root runtime: %FAUST_PYTHON%
"%FAUST_PYTHON%" "%~dp0..\embedded_python_bootstrap.py" "%~dp0backend-main.py" --no-startup-chat
echo Running MAIN service...