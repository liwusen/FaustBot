@echo off
cd /d "%~dp0"
call "%~dp0..\use-runtime.bat" || exit /b 1
echo Using root runtime: %FAUST_PYTHON%
"%FAUST_PYTHON%" "%~dp0..\embedded_python_bootstrap.py" "%~dp0configer_pyside6.py"
