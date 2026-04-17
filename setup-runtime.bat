@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
set "PYTHON_VERSION=3.11.9"
set "PYTHON_EMBED_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
set "GET_PIP_URL=https://bootstrap.pypa.io/get-pip.py"
set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
set "INSTALL_PYTHON=0"
set "INSTALL_TORCH=0"
set "INSTALL_PY_REQ=0"
set "INSTALL_LOCAL_INFER_REQ=0"
set "INSTALL_NODE=0"
set "INSTALL_TTS=0"
set "TORCH_VARIANT=cpu"
set "TTS_VARIANT=standard"
set "INFER_MODE=cloud"
set "SHOW_HELP=0"
set "MODE_PROVIDED=0"

cd /d "%~dp0"
set "RUNTIME_DIR=%CD%\.runtime"
set "PYTHON_EXE=%RUNTIME_DIR%\python.exe"
set "PTH_FILE=%RUNTIME_DIR%\python311._pth"
set "PIP_CMD=%PYTHON_EXE% -m pip"
set "FRONTEND_DIR=%CD%\frontend"
set "MC_OPERATOR_DIR=%CD%\backend\minecraft\mc-operator"
set "BACKEND_DIR=%CD%\backend"
echo -----------------------------------------
echo FaustBot 安装程序
echo 使用命令行参数安装 Python、PyTorch、Python 依赖、Node.js 依赖和 TTS 模型。
echo -----------------------------------------
call :parse_args %*
if errorlevel 1 exit /b 1
if "%SHOW_HELP%"=="1" (
  call :show_help
  exit /b 0
)
if "%MODE_PROVIDED%"=="0" (
  echo 参数错误：必须提供 --mode local 或 --mode cloud
  echo.
  call :show_help
  exit /b 1
)
call :apply_infer_mode_defaults

net session >nul 2>&1
if errorlevel 1 (
  echo 需要管理员权限，正在重新启动...
  call :build_restart_args
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -ArgumentList $env:FAUST_SETUP_ARGS"
  exit /b 0
)

call :print_summary

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
  if "%INSTALL_LOCAL_INFER_REQ%"=="1" (
    if not exist "%CD%\requirements_local_infer.txt" (
      echo 未找到 requirements_local_infer.txt
      goto :fail
    )
    echo 安装本地推理专用依赖...
    %PIP_CMD% install -r "%CD%\requirements_local_infer.txt" -i %PIP_INDEX_URL%
    if errorlevel 1 goto :fail
  )
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

:parse_args
if "%~1"=="" exit /b 0

:parse_args_loop
if "%~1"=="" exit /b 0
if /i "%~1"=="--help" (
  set "SHOW_HELP=1"
  shift
  goto :parse_args_loop
)
if /i "%~1"=="--mode" (
  if "%~2"=="" goto :missing_value
  if /i "%~2"=="local" (
    set "INFER_MODE=local"
    set "MODE_PROVIDED=1"
  ) else if /i "%~2"=="cloud" (
    set "INFER_MODE=cloud"
    set "MODE_PROVIDED=1"
  ) else (
    echo 参数错误：--mode 仅支持 local 或 cloud
    exit /b 1
  )
  shift
  shift
  goto :parse_args_loop
)
if /i "%~1"=="--install-python" (
  call :parse_bool_arg "%~2" INSTALL_PYTHON || exit /b 1
  shift
  shift
  goto :parse_args_loop
)
if /i "%~1"=="--install-node" (
  call :parse_bool_arg "%~2" INSTALL_NODE || exit /b 1
  shift
  shift
  goto :parse_args_loop
)
if /i "%~1"=="--tts-variant" (
  if "%~2"=="" goto :missing_value
  if /i "%~2"=="standard" (
    set "TTS_VARIANT=standard"
  ) else if /i "%~2"=="nvidia50" (
    set "TTS_VARIANT=nvidia50"
  ) else (
    echo 参数错误：--tts-variant 仅支持 standard 或 nvidia50
    exit /b 1
  )
  shift
  shift
  goto :parse_args_loop
)
echo 参数错误：不支持 %~1
exit /b 1

:missing_value
echo 参数错误：%~1 缺少取值
exit /b 1

:parse_bool_arg
if "%~1"=="" (
  echo 参数错误：缺少布尔值
  exit /b 1
)
if /i "%~1"=="yes" (
  set "%~2=1"
  exit /b 0
)
if /i "%~1"=="no" (
  set "%~2=0"
  exit /b 0
)
echo 参数错误：%~2 仅支持 yes 或 no
exit /b 1

:apply_infer_mode_defaults
if /i "%INFER_MODE%"=="local" (
  set "TORCH_VARIANT=gpu"
  set "INSTALL_TORCH=1"
  set "INSTALL_PY_REQ=1"
  set "INSTALL_LOCAL_INFER_REQ=1"
  set "INSTALL_TTS=1"
) else (
  set "TORCH_VARIANT=cpu"
  set "INSTALL_TORCH=1"
  set "INSTALL_PY_REQ=1"
  set "INSTALL_LOCAL_INFER_REQ=0"
  set "INSTALL_TTS=0"
)
exit /b 0

:build_restart_args
call :bool_to_text !INSTALL_PYTHON! INSTALL_PYTHON_TEXT
call :bool_to_text !INSTALL_NODE! INSTALL_NODE_TEXT
set "FAUST_SETUP_ARGS=--mode %INFER_MODE% --install-python !INSTALL_PYTHON_TEXT! --install-node !INSTALL_NODE_TEXT!"
if /i "%INFER_MODE%"=="local" set "FAUST_SETUP_ARGS=!FAUST_SETUP_ARGS! --tts-variant %TTS_VARIANT%"
exit /b 0

:bool_to_text
if "%~1"=="1" (
  set "%~2=yes"
) else (
  set "%~2=no"
)
exit /b 0

:print_summary
call :bool_to_text %INSTALL_PYTHON% INSTALL_PYTHON_TEXT
call :bool_to_text %INSTALL_TORCH% INSTALL_TORCH_TEXT
call :bool_to_text %INSTALL_PY_REQ% INSTALL_PY_REQ_TEXT
call :bool_to_text %INSTALL_LOCAL_INFER_REQ% INSTALL_LOCAL_INFER_REQ_TEXT
call :bool_to_text %INSTALL_NODE% INSTALL_NODE_TEXT
call :bool_to_text %INSTALL_TTS% INSTALL_TTS_TEXT
echo 模式：%INFER_MODE%
echo 安装 Python 基础环境：%INSTALL_PYTHON_TEXT%
echo 安装 PyTorch：%INSTALL_TORCH_TEXT% (%TORCH_VARIANT%)
echo 安装 Python requirements：%INSTALL_PY_REQ_TEXT%
echo 安装本地推理专用依赖：%INSTALL_LOCAL_INFER_REQ_TEXT%
echo 安装 Node.js 依赖：%INSTALL_NODE_TEXT%
echo 下载 TTS：%INSTALL_TTS_TEXT% (%TTS_VARIANT%)
echo.
echo 已确认，开始执行。
exit /b 0

:show_help
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$lines = @('用法：setup-runtime.bat --mode local|cloud [--install-python yes|no] [--install-node yes|no] [--tts-variant standard|nvidia50]','', '参数说明：','参数 --mode: 推理模式。local=本地推理，cloud=云端推理。','参数 --install-python: 是否安装 Python + pip + wheel 等基础环境。','参数 --install-node: 是否安装 frontend 和 mc-operator 的 Node.js 依赖。','参数 --tts-variant: TTS 包类型。standard=普通显卡，nvidia50=50 系显卡。','', '模式默认行为：','local: 安装 GPU 版 PyTorch、requirements_local_infer.txt、requirements.txt、TTS。','cloud: 安装 CPU 版 PyTorch、requirements.txt。','', '示例：','setup-runtime.bat --mode local --install-python yes --install-node yes --tts-variant nvidia50','setup-runtime.bat --mode cloud --install-python no --install-node yes'); [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $lines | ForEach-Object { Write-Host $_ }"
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