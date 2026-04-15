@echo off
cd /d "%~dp0"
set "FAUST_RUNTIME_ROOT=%~dp0..\.runtime"
if exist "%FAUST_RUNTIME_ROOT%\python.exe" (
	echo Root runtime detected: "%FAUST_RUNTIME_ROOT%\python.exe"
) else (
	echo Root runtime not found yet. Run ..\setup-runtime.bat before starting services that need Python.
)
npm start