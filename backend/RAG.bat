@echo off
title FAUST Backend RAG Service
cd /d "%~dp0"
set "PYTHONUTF8=1"
echo FAUST Backend RAG Service Starting...
call "%~dp0..\use-runtime.bat" || exit /b 1
echo Using root runtime: %FAUST_PYTHON%
"%FAUST_PYTHON%" "%~dp0..\embedded_python_bootstrap.py" "%~dp0rag_nano_api.py" > rag.log 2>&1