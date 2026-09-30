@echo off
rem 本脚本属于 WT-NameRelay 修改版（维护者：Diderde），新增代码按 GPL-3.0-only 授权，声明见 MODIFICATION_NOTICE.md
setlocal EnableExtensions

REM ================================================================
REM  WT-NameRelay 一键启动脚本 v2（GBK 编码 / CRLF 行尾）
REM  流程: [1/3] 环境与文件检查 -> [2/3] 按需补齐(Y/N) -> [3/3] 启动
REM  附加: start.bat /only-runner 仅下载 CosyVoice3 推理器（CrispASR 官方发布件）
REM  附加: start.bat /verify 校验全部 TTS 资源与官方哈希是否一致（较慢，需读全量字节）
REM  本文件必须放在仓库根目录，与 main.py 同级。全部使用相对路径。
REM  TTS 模型下载逻辑见同目录 download_tts_verify.bat
REM ================================================================
cd /d "%~dp0"

if /i "%~1"=="/only-runner" goto :only_runner
if /i "%~1"=="/verify" goto :verify_assets

rem ================= [1/3] 环境与文件检查 =================
echo [1/3] 正在检查工作区文件与环境...
echo.

rem -- 工具 --
set "MISSING_TOOLS="
where git >nul 2>&1 || set "MISSING_TOOLS=%MISSING_TOOLS% git"
where curl >nul 2>&1 || set "MISSING_TOOLS=%MISSING_TOOLS% curl"
if defined MISSING_TOOLS (
    echo [错误] 缺少必要工具:%MISSING_TOOLS%
    echo   请安装 Git for Windows（含 curl）并加入 PATH 后重试。
    exit /b 1
)
echo   [OK] git / curl

rem -- Python 虚拟环境 --
set "NEED_VENV=0"
if not exist ".venv\Scripts\python.exe" set "NEED_VENV=1"
if "%NEED_VENV%"=="1" (echo   [缺失] Python 虚拟环境 .venv) else (echo   [OK] Python 虚拟环境 .venv)

rem -- TTS 模型资产（相对路径，缺失即标记）--
set "TTS_DIR=TTS model"
set "NEED_GPT_SOVITS=0"
set "NEED_GGUF=0"
set "NEED_WEIGHTS=0"
if not exist "%TTS_DIR%\GPT-SoVITS\.git" set "NEED_GPT_SOVITS=1"
if not exist "%TTS_DIR%\CosyVoice3" set "NEED_GGUF=1"
if not exist "%TTS_DIR%\GPT-SoVITS\GPT_SoVITS\pretrained_models\s2Gv3.pth" set "NEED_WEIGHTS=1"
if "%NEED_GPT_SOVITS%"=="1" (echo   [缺失] GPT-SoVITS 代码 [%TTS_DIR%\GPT-SoVITS]) else (echo   [OK] GPT-SoVITS 代码)
if "%NEED_GGUF%"=="1" (echo   [缺失] CosyVoice3 GGUF [%TTS_DIR%\CosyVoice3]) else (echo   [OK] CosyVoice3 GGUF)
if not exist "gpt_sovits_weights_list.txt" set "NEED_WEIGHTS=1"
if "%NEED_WEIGHTS%"=="1" (echo   [缺失] GPT-SoVITS 预训练权重（权重或缺清单文件）) else (echo   [OK] GPT-SoVITS 预训练权重)

rem -- CosyVoice3 推理器（官方 runner：CrispASR，GitHub 官方 Release 资产）--
set "COSY_RUNNER_DIR=%TTS_DIR%\CosyVoice3\runner"
set "COSY_RUNNER_VER=v0.8.34"
set "COSY_RUNNER_ASSET=crispasr-0.8.34+vulkan-py3-none-win_amd64.whl"
set "COSY_RUNNER_WHEEL=%COSY_RUNNER_DIR%\%COSY_RUNNER_ASSET%"
set "NEED_COSY_RUNNER=0"
if not exist "%COSY_RUNNER_DIR%\crispasr\crispasr.dll" if not exist "%COSY_RUNNER_WHEEL%" set "NEED_COSY_RUNNER=1"
if "%NEED_COSY_RUNNER%"=="1" (echo   [缺失] CosyVoice3 推理器 CrispASR) else (echo   [OK] CosyVoice3 推理器 CrispASR)
set "NEED_ASR=0"
if not exist "%TTS_DIR%\GPT-SoVITS\tools\asr\models\faster-whisper-large-v3\model.bin" set "NEED_ASR=1"
if "%NEED_ASR%"=="1" (echo   [缺失] ASR 识别模型（Faster Whisper large-v3）) else (echo   [OK] ASR 识别模型)

rem -- vtcore 扩展（Rust/PyO3：.vt 工程格式的唯一解释器；缺失则工程读写不可用，程序仍可启动）--
set "NEED_VTCORE=0"
set "VTCORE_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VTCORE_PY%" (set "NEED_VTCORE=1") else (
    "%VTCORE_PY%" -c "import vtcore,sys; sys.exit(0 if hasattr(vtcore,'parse_container') else 1)" >nul 2>&1
    if errorlevel 1 set "NEED_VTCORE=1"
)
if "%NEED_VTCORE%"=="1" (echo   [缺失] vtcore 扩展（.vt 工程读写需要，稍后尝试获取）) else (echo   [OK] vtcore 扩展)

rem -- 资产完整性（存在性 + 大小比对；基准为官方哈希清单，运行期不联网）--
set "VERIFY_TOOL=%~dp0tools\verify_tts_assets.py"
set "ASSET_MANIFEST=%~dp0tts_assets_manifest.txt"
set "PY_CHECK="
if exist "%~dp0.venv\Scripts\python.exe" set "PY_CHECK=%~dp0.venv\Scripts\python.exe"
if not defined PY_CHECK (
    where python >nul 2>&1 && set "PY_CHECK=python"
)
if defined PY_CHECK if exist "%VERIFY_TOOL%" if exist "%ASSET_MANIFEST%" (
    call :check_integrity weights NEED_WEIGHTS ""
    call :check_integrity gguf NEED_GGUF "--allow-missing"
    call :check_integrity asr NEED_ASR ""
) else (
    echo   [跳过] 资产完整性校验（虚拟环境或校验文件未就绪）
)

rem ================= [2/3] 按需补齐 =================
echo.
echo [2/3] 按需补齐缺失项...

if "%NEED_VENV%"=="1" (
    echo   正在创建 Python 虚拟环境并安装依赖（可能需要几分钟）...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败，请确认已安装 Python 并加入 PATH。
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试。
        exit /b 1
    )
    echo   Python 环境就绪。
)

rem -- vtcore 扩展：体积很小，独立于 TTS 资源，直接补齐（失败不阻塞启动）--
if "%NEED_VTCORE%"=="1" (
    call :fetch_vtcore
    if errorlevel 1 echo   [提示] vtcore 扩展未就绪：程序仍可启动，但 .vt 工程读写不可用。
)

set "NEED_ANY=0"
if "%NEED_GPT_SOVITS%"=="1" set "NEED_ANY=1"
if "%NEED_GGUF%"=="1" set "NEED_ANY=1"
if "%NEED_WEIGHTS%"=="1" set "NEED_ANY=1"
if "%NEED_ASR%"=="1" set "NEED_ANY=1"
if "%NEED_COSY_RUNNER%"=="1" set "NEED_ANY=1"
if "%NEED_ANY%"=="1" (
    echo   检测到以下缺失项：
    if "%NEED_GPT_SOVITS%"=="1" echo     - GPT-SoVITS 代码
    if "%NEED_GGUF%"=="1" echo     - CosyVoice3 GGUF
    if "%NEED_WEIGHTS%"=="1" echo     - GPT-SoVITS 预训练权重
    if "%NEED_ASR%"=="1" echo     - ASR 识别模型（Faster Whisper large-v3）
    if "%NEED_COSY_RUNNER%"=="1" echo     - CosyVoice3 推理器 CrispASR
    echo   下载来源: GitHub + hf-mirror.com（支持断点续传）。
    if "%NEED_WEIGHTS%"=="1" echo   预计下载 GPT-SoVITS 预训练权重约 4.93 GB。
    if "%NEED_ASR%"=="1" echo   预计下载 ASR 识别模型约 3 GB。
    choice /C YN /N /M "  是否现在下载缺失资源？[Y=下载 / N=跳过]："
    if errorlevel 2 goto :tts_skip
    if "%NEED_GPT_SOVITS%"=="0" set "GPT_SOVITS_CODE=0"
    if "%NEED_GGUF%"=="0" set "GGUF_SET=none"
    if "%NEED_WEIGHTS%"=="0" (set "WEIGHTS=0") else (set "WEIGHTS=1")
if "%NEED_ASR%"=="1" (set "ASR_SET=1") else (set "ASR_SET=0")
    call "%~dp0download_tts_verify.bat"
    if "%NEED_COSY_RUNNER%"=="1" call :fetch_cosy_runner
    goto :tts_skip
)
:tts_skip
echo   TTS 资源就绪。

rem ================= [3/3] 启动 =================
echo.
echo [3/3] 启动 WT-NameRelay...
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出，退出码 %errorlevel%。日志见 logs 目录。
    pause
)
exit /b 0

rem ================================================================
rem  子过程：CosyVoice3 推理器（官方 runner = CrispASR）
rem  来源：https://github.com/CrispStrobe/CrispASR 官方 Release 资产（MIT）
rem  说明：Windows 官方件为 wheel（内含 crispasr 包与 DLL）；本过程下载 + 解压 + 校验。
rem ================================================================

:verify_assets
rem 深度校验：逐文件计算官方哈希（sha256 / git blob sha1）并比对；只报告、不下载
echo [校验] TTS 资源官方哈希比对（需读取全部字节，约 12.5 GB，可能较慢）
set "VERIFY_TOOL=%~dp0tools\verify_tts_assets.py"
set "ASSET_MANIFEST=%~dp0tts_assets_manifest.txt"
set "PY_CHECK="
if exist "%~dp0.venv\Scripts\python.exe" set "PY_CHECK=%~dp0.venv\Scripts\python.exe"
if not defined PY_CHECK (
    where python >nul 2>&1 && set "PY_CHECK=python"
)
if not defined PY_CHECK (
    echo [错误] 未找到 Python，无法校验。
    exit /b 1
)
if not exist "%VERIFY_TOOL%" (
    echo [错误] 未找到校验器 %VERIFY_TOOL%
    exit /b 1
)
if not exist "%ASSET_MANIFEST%" (
    echo [错误] 未找到哈希清单 %ASSET_MANIFEST%
    exit /b 1
)
"%PY_CHECK%" "%VERIFY_TOOL%" --hash
if errorlevel 1 (
    echo.
    echo [结果] 存在缺失、不完整或哈希不符的资源，详见上方清单。
    exit /b 1
)
echo.
echo [结果] 全部资源与官方哈希一致。
exit /b 0

:check_integrity
rem 按官方哈希清单校验一组资源（默认只比大小；start.bat /verify 才比哈希）
rem 用法: call :check_integrity <组名> <缺失标记变量> [附加参数]
"%PY_CHECK%" "%VERIFY_TOOL%" --group %~1 --quiet %~3
if errorlevel 1 (
    set "%~2=1"
    echo   [不完整] 资产完整性 %~1：存在缺失或大小不符项（见上方清单，将按需补齐）
) else (
    echo   [OK] 资产完整性 %~1
)
exit /b 0

:only_runner
echo [仅下载] CosyVoice3 推理器（CrispASR %COSY_RUNNER_VER%）
if not defined COSY_RUNNER_VER set "COSY_RUNNER_VER=v0.8.34"
if not defined COSY_RUNNER_ASSET set "COSY_RUNNER_ASSET=crispasr-0.8.34+vulkan-py3-none-win_amd64.whl"
if not defined COSY_RUNNER_DIR set "COSY_RUNNER_DIR=TTS model\CosyVoice3\runner"
if not defined COSY_RUNNER_WHEEL set "COSY_RUNNER_WHEEL=%COSY_RUNNER_DIR%\%COSY_RUNNER_ASSET%"
if exist "%COSY_RUNNER_DIR%\crispasr\crispasr.dll" (echo   [OK] 推理器已存在，无需下载。 & exit /b 0)
call :fetch_cosy_runner
if errorlevel 1 (echo [错误] 推理器下载或解压失败。 & exit /b 1)
echo 完成：%COSY_RUNNER_DIR%\crispasr
exit /b 0

:fetch_cosy_runner
set "COSY_RUNNER_URL=https://github.com/CrispStrobe/CrispASR/releases/download/%COSY_RUNNER_VER%/%COSY_RUNNER_ASSET%"
if not exist "%COSY_RUNNER_DIR%" mkdir "%COSY_RUNNER_DIR%"
echo   正在下载 CosyVoice3 推理器（官方地址）：%COSY_RUNNER_URL%
curl -L --ssl-no-revoke -C - --retry 3 --max-time 900 -o "%COSY_RUNNER_WHEEL%" "%COSY_RUNNER_URL%"
if errorlevel 1 (
    echo   [警告] 推理器下载失败（不影响权重下载与程序启动）。
    exit /b 1
)
for %%Z in ("%COSY_RUNNER_WHEEL%") do if %%~zZ LSS 10000000 (
    echo   [警告] 推理器文件不完整，已删除以便下次重试。
    del "%COSY_RUNNER_WHEEL%" >nul 2>&1
    exit /b 1
)
if exist "%COSY_RUNNER_DIR%\crispasr" rmdir /s /q "%COSY_RUNNER_DIR%\crispasr" >nul 2>&1
tar -xf "%COSY_RUNNER_WHEEL%" -C "%COSY_RUNNER_DIR%" >nul 2>&1
if not exist "%COSY_RUNNER_DIR%\crispasr\crispasr.dll" (
    copy /y "%COSY_RUNNER_WHEEL%" "%COSY_RUNNER_DIR%\crispasr-runner.zip" >nul 2>&1
    powershell -NoProfile -Command "Expand-Archive -LiteralPath '%COSY_RUNNER_DIR%\crispasr-runner.zip' -DestinationPath '%COSY_RUNNER_DIR%' -Force" >nul 2>&1
    del "%COSY_RUNNER_DIR%\crispasr-runner.zip" >nul 2>&1
)
if not exist "%COSY_RUNNER_DIR%\crispasr\crispasr.dll" (
    echo   [提示] 自动解压失败；可手动执行：pip install "%COSY_RUNNER_WHEEL%"
    exit /b 1
)
echo   [OK] 推理器已就绪：%COSY_RUNNER_DIR%\crispasr
exit /b 0

rem ================================================================
rem  子过程：vtcore 扩展（Rust / PyO3；.vt 工程格式的唯一解释器）
rem  来源：本 fork 的 GitHub Release 预编译 wheel（abi3，跨 Python 小版本通用）
rem  说明：体积很小，与 TTS 资源无关；获取失败不影响程序启动，
rem        只是 .vt 工程读写不可用（状态栏与「关于与许可」页会提示）。
rem ================================================================

:fetch_vtcore
set "VTCORE_VER=v0.1.0"
set "VTCORE_ASSET=vtcore-0.1.0-cp312-abi3-win_amd64.whl"
set "VTCORE_DIR=%~dp0temp\vtcore-dl"
set "VTCORE_WHEEL=%VTCORE_DIR%\%VTCORE_ASSET%"
set "VTCORE_URL=https://github.com/Diderde/WT-NameRelay/releases/download/%VTCORE_VER%/%VTCORE_ASSET%"
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo   [跳过] vtcore 扩展：虚拟环境尚未就绪。
    exit /b 1
)
set "VTCORE_LOCAL=%~dp0vtcore\wheels\%VTCORE_ASSET%"
if exist "%VTCORE_LOCAL%" (
    set "VTCORE_WHEEL=%VTCORE_LOCAL%"
    echo   使用随源码附带的预编译扩展：%VTCORE_ASSET%
    goto :vtcore_install
)
rem 本地件缺失时才走 Release 下载（资产未发布时该路径会优雅失败）
if not exist "%VTCORE_DIR%" mkdir "%VTCORE_DIR%"
echo   正在获取 vtcore 扩展：%VTCORE_URL%
curl -L --ssl-no-revoke -C - --retry 3 --max-time 300 -o "%VTCORE_WHEEL%" "%VTCORE_URL%"
if errorlevel 1 (
    echo   [警告] vtcore 扩展下载失败（Release 资产可能尚未提供）。
    echo          可自行构建：先进入 vtcore 目录，再执行 maturin develop --release
    exit /b 1
)
for %%Z in ("%VTCORE_WHEEL%") do if %%~zZ LSS 50000 (
    echo   [警告] vtcore 扩展文件不完整，已删除以便下次重试。
    del "%VTCORE_WHEEL%" >nul 2>&1
    exit /b 1
)
:vtcore_install
"%~dp0.venv\Scripts\python.exe" -m pip install --no-deps --force-reinstall "%VTCORE_WHEEL%" >nul 2>&1
if errorlevel 1 (
    echo   [警告] vtcore 扩展安装失败；可手动执行：pip install "%VTCORE_WHEEL%"
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -c "import vtcore,sys; sys.exit(0 if hasattr(vtcore,'parse_container') else 1)" >nul 2>&1
if errorlevel 1 (
    echo   [警告] vtcore 扩展已安装但不可用（版本不匹配？）。
    exit /b 1
)
echo   [OK] vtcore 扩展已就绪
exit /b 0
