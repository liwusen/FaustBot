@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
net session >nul 2>&1
if errorlevel 1 (
  echo 需要管理员权限，正在重新启动...
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
set "BACKEND_DIR=%CD%\backend"
set "INSTALL_PYTHON=0"
set "INSTALL_TORCH=0"
set "INSTALL_PY_REQ=0"
set "INSTALL_NODE=0"
set "INSTALL_TTS=0"
set "TORCH_VARIANT=cpu"
set "TTS_VARIANT=standard"
echo -----------------------------------------
echo FaustBot 安装程序
echo 这个脚本将引导你安装运行环境，包括 Python、PyTorch、Python 依赖、Node.js 依赖和 TTS 模型。
echo 你可以根据需要选择安装哪些组件。
echo -----------------------------------------
echo 如果你同意本项目的许可证协议(MIT),及其依赖的协议,请按任意键继续。
pause
call :collect_choices

if "%INSTALL_PYTHON%"=="1" (
  echo.
  echo [1/5] 安装 Python 环境
  call :install_python_bundle || goto :fail
)

if "%INSTALL_TORCH%"=="1" (
  echo.
  echo [2/5] 安装 PyTorch
  call :ensure_pip || goto :fail
  call :install_torch || goto :fail
)

if "%INSTALL_PY_REQ%"=="1" (
  echo.
  echo [3/5] 安装 Python 依赖
  call :ensure_pip || goto :fail
  %PIP_CMD% install -r "%CD%\requirements.txt" -i %PIP_INDEX_URL%
  if errorlevel 1 goto :fail
)

if "%INSTALL_NODE%"=="1" (
  echo.
  echo [4/5] 安装 Node.js 依赖 (使用NPM国内镜像)
  call :install_node_deps || goto :fail
)

if "%INSTALL_TTS%"=="1" (
  echo.
  echo [5/5] 下载 TTS 模型 (本地文字转语音需要)
  if not exist "%BACKEND_DIR%\download_tts.py" (
    echo 未找到 backend\download_tts.py
    goto :fail
  )
  "%PYTHON_EXE%" "%CD%\embedded_python_bootstrap.py" "%BACKEND_DIR%\download_tts.py" --gpu-variant %TTS_VARIANT%
  if errorlevel 1 goto :fail
)

echo.
echo 安装完成。
echo 可验证："%PYTHON_EXE%" -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
exit /b 0

:fail
echo.
echo 安装失败，请根据上面的提示处理后重试。
pause
exit /b 1

:collect_choices
echo 请选择要执行的内容：

call :ask_yes_no "安装 Python + pip + wheel 等基础环境" INSTALL_PYTHON
call :ask_yes_no "安装 PyTorch" INSTALL_TORCH
if "%INSTALL_TORCH%"=="1" (
  call :ask_torch_variant
)
call :ask_yes_no "安装 Python requirements" INSTALL_PY_REQ
call :ask_yes_no "安装 Node.js 依赖" INSTALL_NODE
call :ask_yes_no "下载 TTS" INSTALL_TTS
if "%INSTALL_TTS%"=="1" (
  call :ask_yes_no "TTS 是否选择 50 系显卡版本" IS_TTS_50
  if "%IS_TTS_50%"=="1" (
    set "TTS_VARIANT=nvidia50"
  ) else (
    set "TTS_VARIANT=standard"
  )
)
echo.
echo 已确认，开始执行。
exit /b 0

:ask_yes_no
choice /c YN /m "%~1"
if errorlevel 2 (
  set "%~2=0"
) else (
  set "%~2=1"
)
exit /b 0

:ask_torch_variant
choice /c GC /m "PyTorch 安装 GPU 版还是 CPU 版"
if errorlevel 2 (
  set "TORCH_VARIANT=cpu"
) else (
  set "TORCH_VARIANT=gpu"
)
exit /b 0

:ensure_pip
"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo .runtime 中没有可用的 pip，请先安装 Python 基础环境。
  exit /b 1
)
exit /b 0

:install_python_bundle
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%"
echo 下载 Python %PYTHON_VERSION%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_EMBED_URL%' -OutFile '%RUNTIME_DIR%\python-embed.zip'"
if errorlevel 1 exit /b 1
echo 解压 Python...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%RUNTIME_DIR%\python-embed.zip' -DestinationPath '%RUNTIME_DIR%' -Force"
if errorlevel 1 exit /b 1
if not exist "%PYTHON_EXE%" (
  echo 未找到 .runtime\python.exe
  exit /b 1
)
echo 配置 site-packages...
if exist "%PTH_FILE%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$pth = Get-Content '%PTH_FILE%'; $pth = $pth | Where-Object { $_ -notmatch '^#import site$' -and $_ -ne 'Lib\\site-packages' -and $_ -ne 'import site' }; if ($pth -notcontains '.') { $pth += '.' }; $pth += 'Lib\\site-packages'; $pth += 'import site'; Set-Content -Path '%PTH_FILE%' -Value $pth -Encoding ASCII"
  if errorlevel 1 exit /b 1
)
echo 下载 get-pip.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%GET_PIP_URL%' -OutFile '%RUNTIME_DIR%\get-pip.py'"
if errorlevel 1 exit /b 1
echo 安装 pip...
"%PYTHON_EXE%" "%RUNTIME_DIR%\get-pip.py"
if errorlevel 1 exit /b 1
echo 升级 pip、setuptools、wheel...
%PIP_CMD% install --upgrade pip setuptools wheel -i %PIP_INDEX_URL%
if errorlevel 1 exit /b 1
exit /b 0

:install_torch
if /i "%TORCH_VARIANT%"=="gpu" (
  echo 安装 PyTorch GPU 版...
  %PIP_CMD% install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 --extra-index-url %PIP_INDEX_URL%
) else (
  echo 安装 PyTorch CPU 版...
  %PIP_CMD% install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --extra-index-url %PIP_INDEX_URL%
)
if errorlevel 1 exit /b 1
exit /b 0

:install_node_deps
if not exist "%FRONTEND_DIR%\package.json" (
  echo 未找到 frontend\package.json
  exit /b 1
)
if not exist "%MC_OPERATOR_DIR%\package.json" (
  echo 未找到 backend\minecraft\mc-operator\package.json
  exit /b 1
)
pushd "%FRONTEND_DIR%"
npm config set registry https://registry.npmmirror.com/
npm install
if errorlevel 1 (
  popd
  exit /b 1
)
popd
pushd "%MC_OPERATOR_DIR%"
npm config set registry https://registry.npmmirror.com/
npm install
if errorlevel 1 (
  popd
  exit /b 1
)
popd
exit /b 0