@echo off
setlocal EnableExtensions EnableDelayedExpansion

net session >nul 2>&1
if errorlevel 1 (
  echo Administrator privileges are required. Relaunching as administrator...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)

cd /d "%~dp0"

set "RUNTIME_DIR=%CD%\.runtime"
set "PYTHON_VERSION=3.11.9"
set "PYTHON_EMBED_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
set "GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py"
set "PYTHON_EXE=%RUNTIME_DIR%\python.exe"
set "PTH_FILE=%RUNTIME_DIR%\python311._pth"
set "PIP_CMD=%PYTHON_EXE% -m pip"
set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
set "FRONTEND_DIR=%CD%\frontend"
set "MC_OPERATOR_DIR=%CD%\backend\minecraft\mc-operator"

call :confirm_step "[1/9] Prepare .runtime directory"
if errorlevel 1 goto :step1_skip
echo [1/9] Preparing .runtime directory...
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
:step1_skip

call :confirm_step "[2/9] Download Python %PYTHON_VERSION% embedded package"
if errorlevel 1 goto :step2_skip
echo [2/9] Downloading Python %PYTHON_VERSION% embedded package...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_EMBED_URL%' -OutFile '%RUNTIME_DIR%\python-embed.zip'"
if errorlevel 1 goto :fail
:step2_skip

if not exist "%RUNTIME_DIR%\python-embed.zip" (
  echo Embedded package archive not found. Step [3/9] cannot continue.
  goto :fail
)
call :confirm_step "[3/9] Extract embedded Python"
if errorlevel 1 goto :step3_skip
echo [3/9] Extracting embedded Python...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%RUNTIME_DIR%\python-embed.zip' -DestinationPath '%RUNTIME_DIR%' -Force"
if errorlevel 1 goto :fail
:step3_skip

if not exist "%PYTHON_EXE%" (
  echo Python executable not found. Step [4/9] cannot continue.
  goto :fail
)

call :confirm_step "[4/9-A] Enable site-packages for embedded Python"
if errorlevel 1 goto :step4a_skip
echo [4/9-A] Enabling site-packages...
if exist "%PTH_FILE%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$pth = Get-Content '%PTH_FILE%'; $pth = $pth | Where-Object { $_ -notmatch '^#import site$' -and $_ -ne 'Lib\\site-packages' -and $_ -ne 'import site' }; if ($pth -notcontains '.') { $pth += '.' }; $pth += 'Lib\\site-packages'; $pth += 'import site'; Set-Content -Path '%PTH_FILE%' -Value $pth -Encoding ASCII"
  if errorlevel 1 goto :fail
)
:step4a_skip

call :confirm_step "[4/9-B] Download get-pip.py"
if errorlevel 1 goto :step4b_skip
echo [4/9-B] Downloading get-pip.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%GET_PIP_URL%' -OutFile '%RUNTIME_DIR%\get-pip.py'"
if errorlevel 1 goto :fail
:step4b_skip

if not exist "%RUNTIME_DIR%\get-pip.py" (
  echo get-pip.py not found. Step [4/9-C] cannot continue.
  goto :fail
)
call :confirm_step "[4/9-C] Install pip into embedded Python"
if errorlevel 1 goto :step4c_skip
echo [4/9-C] Installing pip...
"%PYTHON_EXE%" "%RUNTIME_DIR%\get-pip.py"
if errorlevel 1 goto :fail
:step4c_skip

call :ensure_pip || goto :fail
call :confirm_step "[5/9] Upgrade pip, setuptools, wheel via Tsinghua PyPI"
if errorlevel 1 goto :step5_skip
echo [5/9] Upgrading base packaging tools via Tsinghua PyPI...
%PIP_CMD% install --upgrade pip setuptools wheel -i %PIP_INDEX_URL%
if errorlevel 1 goto :fail
:step5_skip

call :ensure_pip || goto :fail
call :confirm_step "[6/9] Install PyTorch CUDA 12.8 stack"
if errorlevel 1 goto :step6_skip
echo [6/9] Installing PyTorch CUDA 12.8 stack...
%PIP_CMD% install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 --extra-index-url %PIP_INDEX_URL%
if errorlevel 1 goto :fail
:step6_skip

call :ensure_pip || goto :fail
call :confirm_step "[7/9] Install project requirements via Tsinghua PyPI"
if errorlevel 1 goto :step7_skip
echo [7/9] Installing project requirements via Tsinghua PyPI...
%PIP_CMD% install -r "%CD%\requirements.txt" -i %PIP_INDEX_URL%
if errorlevel 1 goto :fail
:step7_skip

if not exist "%FRONTEND_DIR%\package.json" (
  echo frontend package.json not found. Step [8/9] cannot continue.
  goto :fail
)
call :confirm_step "[8/9] Run npm install in frontend"
if errorlevel 1 goto :step8_skip
echo [8/9] Running npm install in frontend...
pushd "%FRONTEND_DIR%"
npm install
if errorlevel 1 (
  popd
  goto :fail
)
popd
:step8_skip

if not exist "%MC_OPERATOR_DIR%\package.json" (
  echo mc-operator package.json not found. Step [9/9] cannot continue.
  goto :fail
)
call :confirm_step "[9/9] Run npm install in mc-operator"
if errorlevel 1 goto :step9_skip
echo [9/9] Running npm install in mc-operator...
pushd "%MC_OPERATOR_DIR%"
npm install
if errorlevel 1 (
  popd
  goto :fail
)
popd
:step9_skip

echo Runtime installation completed.
echo Verify with: "%PYTHON_EXE%" -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
exit /b 0

:fail
echo Runtime installation failed.
echo Fix the failing step above and rerun this script.
pause
exit /b 1

:confirm_step
choice /c YS /m "%~1 ? [Y]es / [S]kip"
if errorlevel 2 exit /b 1
exit /b 0

:ensure_pip
"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo pip is not available in .runtime. Complete step [4/9-C] first.
  exit /b 1
)
exit /b 0