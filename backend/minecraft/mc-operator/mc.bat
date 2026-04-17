@echo off
title FAUST Backend Minecraft Operator Service
cd /d %~dp0
echo FAUST Backend Minecraft Operator Starting...
set "PACKAGED_DIR=%~dp0dist\faust-mc-operator"
set "PACKAGED_LAUNCHER=%PACKAGED_DIR%\mc.bat"
if exist "%PACKAGED_LAUNCHER%" (
	echo Packaged mc-operator detected: "%PACKAGED_DIR%"
	call "%PACKAGED_LAUNCHER%" > log.log 2>&1
	exit /b %errorlevel%
)
node src/index.js > log.log 2>&1