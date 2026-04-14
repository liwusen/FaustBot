@echo off
title FAUST Backend RAG Service
cd /d "%~dp0"
set "PYTHONUTF8=1"
set PYTHONPATH=%cd%;%PYTHONPATH%
echo FAUST Backend RAG Service Starting...
echo Activating conda environment 'faustbot'...
conda activate faustbot && python rag_nano_api.py > rag.log 2>&1