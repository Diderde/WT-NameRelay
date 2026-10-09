@echo off
rem 本脚本属于 WT-NameRelay 修改版（维护者：Diderde），新增代码按 GPL-3.0-only 授权，声明见 MODIFICATION_NOTICE.md
setlocal EnableExtensions
rem 936：本文件是 GBK，65001 终端下中文会乱码
chcp 936 >nul 2>&1

REM ================================================================
REM  WT-NameRelay 一键启动脚本 v5（GBK 编码 / CRLF 行尾）
REM  流程: [1/3] 环境与文件检查 -> [2/3] 按需补齐(Y/N) -> [3/3] 启动
REM  附加: start.bat /only-runner 仅下载 CosyVoice3 推理器（CrispASR 官方发布件）
REM  附加: start.bat /verify 校验全部 TTS 资源与官方哈希是否一致（较慢，需读全量字节）
REM  附加: start.bat /gate 独占运行全量门禁（35 模块，写 tools\gate-results.txt）
REM  附加: start.bat /test 快速自检（ruff + compileall + 全量 unittest）
REM  v3: added MSST voice-separation checks (code / inference env; models download in-app)
REM  v4: added FMOD Studio probe + /gate (full gate) + /test (quick suite) dev switches
REM  v5: chcp 936；Python 3.12 / 随包 ffmpeg / requirements 漂移检查；未知参数 usage（exit 2）；TTS 补齐失败告警
REM  本文件必须放在仓库根目录，与 main.py 同级。全部使用相对路径。
REM  TTS 模型下载逻辑见同目录 download_tts_verify.bat
REM ================================================================
cd /d "%~dp0"

if /i "%~1"=="/only-runner" goto :only_runner
if /i "%~1"=="/verify" goto :verify_assets
if /i "%~1"=="/gate" goto :gate_suite
if /i "%~1"=="/test" goto :test_suite

rem 未知参数不得静默进入正常启动（拼错 /gat 时必须可见）
if not "%~1"=="" (
    echo [错误] 未知参数：仅支持 /only-runner /verify /gate /test；无参数为正常启动。
    echo   用法: start.bat [开关]
    echo     /only-runner 仅下载 CosyVoice3 推理器（CrispASR）
    echo     /verify      校验全部 TTS 资源与官方哈希是否一致（较慢）
    echo     /gate        独占运行全量门禁（写 tools\gate-results.txt）
    echo     /test        快速自检（ruff + compileall + 全量 unittest）
    exit /b 2
)

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

rem -- Python 版本：必须 3.12.x（numpy 1.26.4 / PySide6 6.7.3 无 cp313 wheel，3.13 会在装依赖时才炸）--
set "PY_VENV=%~dp0.venv\Scripts\python.exe"
set "PY_VER_OK=0"
if exist "%PY_VENV%" (
    "%PY_VENV%" -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [错误] .venv 内的 Python 不是 3.12（本项目仅支持 3.12.x）。
        echo   请删除 .venv 目录，安装 Python 3.12 后重跑本脚本。
        goto :die_env
    )
    set "PY_VER_OK=1"
)
if "%PY_VER_OK%"=="1" (
    echo   [OK] Python 版本 3.12（.venv）
) else (
    python -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未找到可用的 Python 3.12（依赖 numpy 1.26.4 / PySide6 6.7.3 无 cp313 wheel）。
        echo   请安装 Python 3.12 并加入 PATH 后重试。
        goto :die_env
    )
    echo   [待建] Python 3.12（系统 PATH；[2/3] 将创建 .venv）
)

rem -- 随包 FFmpeg（音频管线核心；git-lfs 件，未拉取时是 ~130 字节指针文件）--
set "FF_BIN=%~dp0app\resources\ffmpeg\bin"
set "FF_BAD="
for %%F in (ffmpeg.exe ffprobe.exe) do call :check_ff_one %%F
if defined FF_BAD (
    echo [错误] 随包 FFmpeg 缺失或不完整:%FF_BAD%
    echo   该目录是 Git LFS 资产，请在仓库根执行 git lfs pull 后重试。
    exit /b 1
)
echo   [OK] 随包 FFmpeg（ffmpeg / ffprobe）

rem -- Python 虚拟环境 --
set "NEED_VENV=0"
if not exist ".venv\Scripts\python.exe" set "NEED_VENV=1"
if "%NEED_VENV%"=="1" (echo   [缺失] Python 虚拟环境 .venv) else (echo   [OK] Python 虚拟环境 .venv)

rem -- requirements 漂移检测（比对 .venv\requirements.sha256；不一致则 [2/3] 重装）--
set "NEED_REQ=0"
if not exist "%PY_VENV%" goto :req_checked
"%PY_VENV%" -c "import hashlib,pathlib,sys; h=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); q=pathlib.Path('.venv/requirements.sha256'); sys.exit(0 if q.exists() and q.read_text(encoding='utf-8').strip()==h else 1)" >nul 2>&1
if errorlevel 1 set "NEED_REQ=1"
if "%NEED_REQ%"=="1" (echo   [漂移] requirements.txt 已变化，[2/3] 将重新同步依赖) else (echo   [OK] requirements.txt 与 .venv 记录一致)
:req_checked

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

rem -- Voice separation (MSST): code checkout + inference env (app runs fine without) --
set "MSST_DIR=%TTS_DIR%\MSST"
set "NEED_MSST=0"
if not exist "%MSST_DIR%\inference.py" set "NEED_MSST=1"
if "%NEED_MSST%"=="1" (echo   [缺失] 人声分离代码（MSST）[TTS model\MSST] —— 分离功能不可用，其余功能不受影响) else (echo   [OK] 人声分离代码（MSST）)
set "SEP_ENV=0"
if exist "config\settings.ini" findstr /i /c:"python_exec" "config\settings.ini" >nul 2>&1 && set "SEP_ENV=1"
if "%SEP_ENV%"=="1" (echo   [OK] 分离推理 Python 环境（separate/python_exec）) else (echo   [未配置] 分离推理 Python 环境 —— 需要时在应用的"人声分离"页设置)
set "MSST_MODELS=0"
rem  say no to perv. weight dirs = dirs containing the weights file
rem  (upstream code dirs under models\ are NOT weights; v3 counted them - false [OK])
for /d %%D in ("%MSST_DIR%\models\*") do if exist "%%D\model.safetensors" set /a MSST_MODELS+=1
if "%MSST_MODELS%"=="0" (echo   [未下载] 分离模型权重 —— 打开"人声分离"页按需下载) else (echo   [OK] 分离模型权重（%MSST_MODELS% 组）)
set "FMOD_STUDIO="
if exist "%~dp0FMOD Studio 2.02.30\fmodstudio.exe" set "FMOD_STUDIO=%~dp0FMOD Studio 2.02.30"
for /d %%D in ("%ProgramFiles%\FMOD Sound Systems\*") do if not defined FMOD_STUDIO if exist "%%D\fmodstudio.exe" set "FMOD_STUDIO=%%D"
for /d %%D in ("%ProgramFiles(x86)%\FMOD Sound Systems\*") do if not defined FMOD_STUDIO if exist "%%D\fmodstudio.exe" set "FMOD_STUDIO=%%D"
if defined FMOD_STUDIO (echo   [OK] FMOD Studio：%FMOD_STUDIO%) else (echo   [未检出] FMOD Studio（需 2.02.22）—— FMOD 流水线需要；安装后把路径告知维护者)

rem -- GSV v5 推理服务运行时（整合包自带 Python runtime；GSV 推理自动拉起依赖）--
set "GSV5_DIR=%TTS_DIR%\GPT-SoVITS-v5-20261006"
set "NEED_GSV_RUNTIME=0"
if not exist "%GSV5_DIR%\api_v2.py" set "NEED_GSV_RUNTIME=1"
if not exist "%GSV5_DIR%\runtime\python.exe" set "NEED_GSV_RUNTIME=1"
if "%NEED_GSV_RUNTIME%"=="1" (echo   [缺失] GSV v5 推理服务运行时 [%GSV5_DIR%] —— GSV 推理自动拉起不可用) else (echo   [OK] GSV v5 推理服务运行时)



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
        echo [错误] 虚拟环境创建失败，请确认已安装 Python 3.12 并加入 PATH。
        goto :die_env
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试。
        goto :die_env
    )
    call :stamp_requirements
    echo   Python 环境就绪。
)

rem -- requirements 漂移：文件已变化则重装（幂等；只装一次会让依赖升级静默失效）--
if "%NEED_REQ%"=="1" (
    echo   检测到 requirements.txt 变化，正在同步依赖...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖同步失败，请检查网络后重试。
        goto :die_env
    )
    call :stamp_requirements
    echo   依赖已同步。
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
if "%NEED_GSV_RUNTIME%"=="1" set "NEED_ANY=1"
if "%NEED_ANY%"=="1" (
    echo   检测到以下缺失项：
    if "%NEED_GPT_SOVITS%"=="1" echo     - GPT-SoVITS 代码
    if "%NEED_GGUF%"=="1" echo     - CosyVoice3 GGUF
    if "%NEED_WEIGHTS%"=="1" echo     - GPT-SoVITS 预训练权重
    if "%NEED_ASR%"=="1" echo     - ASR 识别模型（Faster Whisper large-v3）
    if "%NEED_COSY_RUNNER%"=="1" echo     - CosyVoice3 推理器 CrispASR
    if "%NEED_GSV_RUNTIME%"=="1" echo     - GSV v5 推理服务运行时（整合包 10.83 GB）
    echo   下载来源: GitHub + hf-mirror.com（支持断点续传）。
    if "%NEED_WEIGHTS%"=="1" echo   预计下载 GPT-SoVITS 预训练权重约 4.93 GB。
    if "%NEED_ASR%"=="1" echo   预计下载 ASR 识别模型约 3 GB。
    if "%NEED_GSV_RUNTIME%"=="1" echo   预计下载 GSV v5 推理服务运行时约 10.83 GB。
    choice /C YN /N /M "  是否现在下载缺失资源？[Y=下载 / N=跳过]："
    if errorlevel 2 goto :tts_skip
    if "%NEED_GPT_SOVITS%"=="0" set "GPT_SOVITS_CODE=0"
    if "%NEED_GGUF%"=="0" set "GGUF_SET=none"
    if "%NEED_WEIGHTS%"=="0" (set "WEIGHTS=0") else (set "WEIGHTS=1")
if "%NEED_ASR%"=="1" (set "ASR_SET=1") else (set "ASR_SET=0")
if "%NEED_GSV_RUNTIME%"=="0" set "GSV_RUNTIME=0"
    call "%~dp0download_tts_verify.bat"
    if errorlevel 1 echo   [警告] TTS 资源补齐未完成；可重跑本脚本断点续传补齐。
    if "%NEED_COSY_RUNNER%"=="1" call :fetch_cosy_runner
    goto :tts_skip
)
:tts_skip
echo   TTS 资源就绪。
if "%NEED_MSST%"=="1" (
    echo   [提示] 人声分离（MSST）代码缺失：该功能暂不可用，其余功能不受影响。
    echo          获取：git clone --depth 1 https://github.com/ZFTurbo/Music-Source-Separation-Training "%MSST_DIR%"
)
if "%SEP_ENV%"=="0" echo   [提示] 未配置分离推理 Python 环境：需要时在应用"人声分离"页设置（依赖按隔离先例不装入本虚拟环境）。

rem ================= [3/3] 启动 =================
echo.
echo [3/3] 启动 WT-NameRelay...
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出，退出码 %errorlevel%。日志见 logs 目录。
    pause
    exit /b 1
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

rem ================================================================
rem  dev switches: /gate full gate (exclusive machine), /test quick suite
rem ================================================================

:gate_suite
echo [门禁] 全量门禁（35 模块逐模块独立进程 + 超时；需独占机器，期间勿并行重活）...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\run_gate.ps1"
set "GATE_RC=%errorlevel%"
if "%GATE_RC%"=="0" (echo [结果] 门禁全绿。明细见 tools\gate-results.txt) else (echo [结果] 门禁存在失败，明细见 tools\gate-results.txt)
exit /b %GATE_RC%

:test_suite
echo [自检] ruff + compileall + 全量 unittest（单进程快速版；严谨版 /gate）...
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (echo [错误] 虚拟环境未就绪，请先无参运行 start.bat 完成初始化。 & exit /b 1)
if not exist "%~dp0.venv\Scripts\ruff.exe" (
    echo [错误] 未安装 ruff（自检依赖）。安装：.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    exit /b 1
)
"%~dp0.venv\Scripts\ruff.exe" check app tests tools
if errorlevel 1 exit /b 1
"%~dp0.venv\Scripts\python.exe" -m compileall -q main.py app tests tools
if errorlevel 1 exit /b 1
"%~dp0.venv\Scripts\python.exe" -m unittest discover -s tests -t .
if errorlevel 1 (
    echo [结果] 自检存在失败。
    exit /b 1
)
echo [结果] 自检全部通过。
exit /b 0

rem ================================================================
rem  子过程：随包 FFmpeg / requirements 漂移 / 致命错误出口
rem ================================================================

:check_ff_one
rem arg1=文件名；缺失或不足 50KB（LFS 指针件约 130 字节）时记入 FF_BAD
set "FF_ONE=%FF_BIN%\%~1"
if not exist "%FF_ONE%" set "FF_BAD=%FF_BAD% %~1（缺失）"
if not exist "%FF_ONE%" exit /b 0
for %%Z in ("%FF_ONE%") do if %%~zZ LSS 50000 set "FF_BAD=%FF_BAD% %~1（不完整）"
exit /b 0

:stamp_requirements
rem 记录 requirements.txt 的 SHA256（下次启动漂移检测的基准）
if not exist "%~dp0.venv\Scripts\python.exe" exit /b 0
"%~dp0.venv\Scripts\python.exe" -c "import hashlib,pathlib; pathlib.Path('.venv/requirements.sha256').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(), encoding='utf-8')" >nul 2>&1
exit /b 0

:die_env
rem 环境类致命错误的统一出口。必须经 goto 跳入：嵌套块内直接 exit /b 会丢退出码
rem （cmd 实测：外层块在内层块之后还有命令时 exit /b N 的退出码变成 0，2026-10-07）
exit /b 1
