@echo on
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set PYTHONPATH=%cd%;%PYTHONPATH%
conda activate my-neuro&&python rag_nano_api.py