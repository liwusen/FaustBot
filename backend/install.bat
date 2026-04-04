@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0.."
set "FAUST_ROOT=%CD%"
set "LOG_DIR=%FAUST_ROOT%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
set "LOG_FILE=%LOG_DIR%\install_%TS%.log"

call :log "============================================================"
call :log "Faust install script started"
call :log "Root: %FAUST_ROOT%"
call :log "Log file: %LOG_FILE%"
call :log "============================================================"

set "HAS_NVIDIA=0"
set "GPU_NAME="
set "CUDA_VERSION="
set "TORCH_CUDA_TAG=cu121"
set "TORCH_INDEX_URL=https://download.pytorch.org/whl/cu121"
set "GPU_SERIES=other"

call :log "[Step 0] Checking NVIDIA GPU..."
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "$g=Get-CimInstance Win32_VideoController ^| Where-Object {$_.Name -match 'NVIDIA'} ^| Select-Object -First 1 -ExpandProperty Name; if($g){$g}"`) do set "GPU_NAME=%%i"

if defined GPU_NAME (
	set "HAS_NVIDIA=1"
	call :log "Detected NVIDIA GPU: !GPU_NAME!"
) else (
	call :log "No NVIDIA GPU detected. This installer only supports NVIDIA GPUs."
	call :log "Exiting now."
	echo.
	echo [ERROR] No NVIDIA GPU detected. Installer aborted.
	echo [INFO] See log: %LOG_FILE%
	exit /b 1
)

call :detect_cuda
call :select_torch_index

echo.
echo CUDA Version Detected: !CUDA_VERSION!
echo Torch CUDA Tag: !TORCH_CUDA_TAG!
echo Torch Index URL: !TORCH_INDEX_URL!
echo.

call :confirm_step "Step 1: Install Python 3.11 and Node.js 24.10.0 with Chocolatey" STEP1_DECISION
if /I "!STEP1_DECISION!"=="Q" goto :user_quit
if /I "!STEP1_DECISION!"=="Y" (
	call :run_step1
	if errorlevel 1 goto :user_abort
) else (
	call :log "[Step 1] Skipped by user."
)

call :confirm_step "Step 2: Create .venv, install CUDA-matched Torch, and install Python dependencies" STEP2_DECISION
if /I "!STEP2_DECISION!"=="Q" goto :user_quit
if /I "!STEP2_DECISION!"=="Y" (
	call :run_step2
	if errorlevel 1 goto :user_abort
) else (
	call :log "[Step 2] Skipped by user."
)

call :confirm_step "Step 3: Install npm dependencies for frontend and backend/minecraft/mc-operator" STEP3_DECISION
if /I "!STEP3_DECISION!"=="Q" goto :user_quit
if /I "!STEP3_DECISION!"=="Y" (
	call :run_step3
	if errorlevel 1 goto :user_abort
) else (
	call :log "[Step 3] Skipped by user."
)

call :confirm_step "Step 4: Download GPT-SoVITS package (50 series / other auto selection)" STEP4_DECISION
if /I "!STEP4_DECISION!"=="Q" goto :user_quit
if /I "!STEP4_DECISION!"=="Y" (
	call :run_step4
	if errorlevel 1 goto :user_abort
) else (
	call :log "[Step 4] Skipped by user."
)

call :log "============================================================"
call :log "Install script finished."
call :log "Please check details in: %LOG_FILE%"
call :log "============================================================"
echo.
echo [DONE] Install script finished.
echo [INFO] Log file: %LOG_FILE%
exit /b 0

:run_step1
call :log "[Step 1] Starting Chocolatey installs..."
where choco >nul 2>nul
if errorlevel 1 (
	call :log "[Step 1] Chocolatey is not installed or not in PATH."
	echo [ERROR] Chocolatey not found. Please install Chocolatey first: https://chocolatey.org/install
	call :step_fail_or_continue "Step 1"
	if errorlevel 1 exit /b 1
	exit /b 0
)

call :log "[Step 1] Installing Python 3.11 via choco..."
choco install python --version=3.11.9 -y
set "ERR=!ERRORLEVEL!"
call :log "[Step 1] Python install exit code: !ERR!"
if not "!ERR!"=="0" (
	call :step_fail_or_continue "Step 1 Python install"
	if errorlevel 1 exit /b 1
)

call :log "[Step 1] Installing Node.js 24.10.0 via choco..."
choco install nodejs --version=24.10.0 -y
set "ERR=!ERRORLEVEL!"
call :log "[Step 1] Node.js install exit code: !ERR!"
if not "!ERR!"=="0" (
	call :step_fail_or_continue "Step 1 Node.js install"
	if errorlevel 1 exit /b 1
)

call :log "[Step 1] Version check..."
py -3.11 --version
npm --version
node --version
call :log "[Step 1] Completed."
exit /b 0

:run_step2
call :log "[Step 2] Preparing Python virtual environment in %FAUST_ROOT%\.venv"
if exist "%FAUST_ROOT%\.venv\Scripts\python.exe" (
	call :log "[Step 2] Existing .venv detected, reusing it."
) else (
	call :log "[Step 2] Creating .venv with Python 3.11..."
	py -3.11 -m venv "%FAUST_ROOT%\.venv"
	set "ERR=!ERRORLEVEL!"
	call :log "[Step 2] venv creation exit code: !ERR!"
	if not "!ERR!"=="0" (
		call :log "[Step 2] py -3.11 failed. Trying python -m venv fallback..."
		python -m venv "%FAUST_ROOT%\.venv"
		set "ERR=!ERRORLEVEL!"
		call :log "[Step 2] fallback venv creation exit code: !ERR!"
		if not "!ERR!"=="0" (
			call :step_fail_or_continue "Step 2 venv creation"
			if errorlevel 1 exit /b 1
			exit /b 0
		)
	)
)

set "VENV_PY=%FAUST_ROOT%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
	call :log "[Step 2] ERROR: venv python not found at %VENV_PY%"
	call :step_fail_or_continue "Step 2 venv python missing"
	if errorlevel 1 exit /b 1
	exit /b 0
)

call :log "[Step 2] Upgrading pip/setuptools/wheel..."
"%VENV_PY%" -m pip install --upgrade pip setuptools wheel
set "ERR=!ERRORLEVEL!"
call :log "[Step 2] pip upgrade exit code: !ERR!"
if not "!ERR!"=="0" (
	call :step_fail_or_continue "Step 2 pip upgrade"
	if errorlevel 1 exit /b 1
)

call :log "[Step 2] Installing torch stack from !TORCH_INDEX_URL!"
"%VENV_PY%" -m pip install torch torchvision torchaudio --index-url "!TORCH_INDEX_URL!"
set "ERR=!ERRORLEVEL!"
call :log "[Step 2] torch install exit code: !ERR!"
if not "!ERR!"=="0" (
	call :step_fail_or_continue "Step 2 torch install"
	if errorlevel 1 exit /b 1
)

call :log "[Step 2] Installing requirements from %FAUST_ROOT%\requirements.txt"
"%VENV_PY%" -m pip install -r "%FAUST_ROOT%\requirements.txt"
set "ERR=!ERRORLEVEL!"
call :log "[Step 2] requirements install exit code: !ERR!"
if not "!ERR!"=="0" (
	call :step_fail_or_continue "Step 2 requirements install"
	if errorlevel 1 exit /b 1
)

call :log "[Step 2] Verifying torch + cuda availability"
"%VENV_PY%" -c "import torch; print('torch=', torch.__version__); print('cuda_available=', torch.cuda.is_available()); print('cuda=', torch.version.cuda)"
set "ERR=!ERRORLEVEL!"
call :log "[Step 2] torch verify exit code: !ERR!"
if not "!ERR!"=="0" (
	call :step_fail_or_continue "Step 2 torch verify"
	if errorlevel 1 exit /b 1
)

call :log "[Step 2] Completed."
exit /b 0

:run_step3
call :log "[Step 3] Installing npm dependencies"
where npm >nul 2>nul
if errorlevel 1 (
	call :log "[Step 3] npm not found in PATH."
	call :step_fail_or_continue "Step 3 npm missing"
	if errorlevel 1 exit /b 1
	exit /b 0
)

if exist "%FAUST_ROOT%\frontend\package.json" (
	call :log "[Step 3] npm install in frontend"
	pushd "%FAUST_ROOT%\frontend"
	npm install
	set "ERR=!ERRORLEVEL!"
	popd
	call :log "[Step 3] frontend npm install exit code: !ERR!"
	if not "!ERR!"=="0" (
		call :step_fail_or_continue "Step 3 frontend npm install"
		if errorlevel 1 exit /b 1
	)
) else (
	call :log "[Step 3] frontend package.json not found, skipped"
)

if exist "%FAUST_ROOT%\backend\minecraft\mc-operator\package.json" (
	call :log "[Step 3] npm install in backend/minecraft/mc-operator"
	pushd "%FAUST_ROOT%\backend\minecraft\mc-operator"
	npm install
	set "ERR=!ERRORLEVEL!"
	popd
	call :log "[Step 3] mc-operator npm install exit code: !ERR!"
	if not "!ERR!"=="0" (
		call :step_fail_or_continue "Step 3 mc-operator npm install"
		if errorlevel 1 exit /b 1
	)
) else (
	call :log "[Step 3] backend/minecraft/mc-operator/package.json not found, skipped"
)

call :log "[Step 3] Completed."
exit /b 0

:run_step4
call :log "[Step 4] Selecting GPT-SoVITS package by GPU series"
for /f %%i in ('powershell -NoProfile -Command "$n='''!GPU_NAME!'''; if($n -match 'RTX\s*50'){ '50' } else { 'other' }"') do set "GPU_SERIES=%%i"

if /I "!GPU_SERIES!"=="50" (
	set "TTS_URL=https://www.modelscope.cn/models/FlowerCry/gpt-sovits-7z-pacakges/resolve/master/GPT-SoVITS-v2pro-20250604-nvidia50.7z"
	set "TTS_FILE_NAME=GPT-SoVITS-v2pro-20250604-nvidia50.7z"
) else (
	set "TTS_URL=https://www.modelscope.cn/models/FlowerCry/gpt-sovits-7z-pacakges/resolve/master/GPT-SoVITS-v2pro-20250604.7z"
	set "TTS_FILE_NAME=GPT-SoVITS-v2pro-20250604.7z"
)

set "TTS_DIR=%FAUST_ROOT%\backend\tts-hub\GPT-SoVITS-Bundle"
if not exist "!TTS_DIR!" mkdir "!TTS_DIR!"
set "TTS_OUT=!TTS_DIR!\!TTS_FILE_NAME!"

call :log "[Step 4] GPU series: !GPU_SERIES!"
call :log "[Step 4] Download URL: !TTS_URL!"
call :log "[Step 4] Download target: !TTS_OUT!"

powershell -NoProfile -Command "Invoke-WebRequest -Uri '!TTS_URL!' -OutFile '!TTS_OUT!' -UseBasicParsing"
set "ERR=!ERRORLEVEL!"
call :log "[Step 4] Download exit code: !ERR!"
if not "!ERR!"=="0" (
	call :step_fail_or_continue "Step 4 TTS download"
	if errorlevel 1 exit /b 1
	exit /b 0
)

for %%f in ("!TTS_OUT!") do set "TTS_SIZE=%%~zf"
call :log "[Step 4] Download completed. File size(bytes): !TTS_SIZE!"
call :log "[Step 4] Completed."
exit /b 0

:detect_cuda
set "CUDA_VERSION="
for /f "usebackq delims=" %%i in (`nvidia-smi --query-gpu=cuda_version --format=csv,noheader 2^>nul`) do (
	if not defined CUDA_VERSION set "CUDA_VERSION=%%i"
)

if not defined CUDA_VERSION (
	for /f "tokens=2 delims=:" %%i in ('nvidia-smi 2^>nul ^| findstr /C:"CUDA Version"') do (
		if not defined CUDA_VERSION set "CUDA_VERSION=%%i"
	)
)

if not defined CUDA_VERSION (
	set "CUDA_VERSION=12.1"
	call :log "CUDA version detection failed, fallback to 12.1"
) else (
	set "CUDA_VERSION=!CUDA_VERSION: =!"
	call :log "Detected CUDA version: !CUDA_VERSION!"
)
exit /b 0

:select_torch_index
for /f %%i in ('powershell -NoProfile -Command "$v=[version]'!CUDA_VERSION!'; if($v -ge [version]'12.8'){ 'cu128' } elseif($v -ge [version]'12.6'){ 'cu126' } elseif($v -ge [version]'12.4'){ 'cu124' } else { 'cu121' }"') do set "TORCH_CUDA_TAG=%%i"
if not defined TORCH_CUDA_TAG set "TORCH_CUDA_TAG=cu121"
set "TORCH_INDEX_URL=https://download.pytorch.org/whl/!TORCH_CUDA_TAG!"
call :log "Torch index selected: !TORCH_INDEX_URL!"
exit /b 0

:confirm_step
set "%~2=S"
:confirm_step_loop
echo.
echo %~1
set /p "STEP_INPUT=Type Y to execute, S to skip, Q to quit: "
if /I "!STEP_INPUT!"=="Y" (
	set "%~2=Y"
	exit /b 0
)
if /I "!STEP_INPUT!"=="S" (
	set "%~2=S"
	exit /b 0
)
if /I "!STEP_INPUT!"=="Q" (
	set "%~2=Q"
	exit /b 0
)
echo Invalid input. Please type Y / S / Q.
goto :confirm_step_loop

:step_fail_or_continue
echo.
echo [WARN] %~1 failed.
set /p "FAIL_CONTINUE=Continue anyway? (Y/N): "
if /I "!FAIL_CONTINUE!"=="Y" (
	call :log "User chose to continue after failure at %~1"
	exit /b 0
)
call :log "User aborted after failure at %~1"
echo [ABORTED] Installation stopped by user.
echo [INFO] Log file: %LOG_FILE%
exit /b 1

:user_quit
call :log "User chose to quit installer."
echo [INFO] Installer stopped by user.
echo [INFO] Log file: %LOG_FILE%
exit /b 0

:user_abort
call :log "Installer aborted due to failure handling."
echo [ABORTED] Installer stopped due to step failure.
echo [INFO] Log file: %LOG_FILE%
exit /b 1

:log
set "_LOG_TEXT=%~1"
echo [%date% %time%] !_LOG_TEXT!
>> "%LOG_FILE%" echo [%date% %time%] !_LOG_TEXT!
exit /b 0
