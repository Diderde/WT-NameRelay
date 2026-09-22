@echo off
setlocal EnableExtensions

REM ================================================================
REM  TTS 资源下载脚本 v3（GBK 编码 / CRLF；并行下载；本地资产检测）
REM  [1] GPT-SoVITS 代码        GitHub: RVC-Boss/GPT-SoVITS（浅克隆/更新）
REM  [2] CosyVoice3 GGUF  HF: cstr/cosyvoice3-0.5b-2512-GGUF
REM  [3] GPT-SoVITS 预训练权重    HF: lj1995/GPT-SoVITS（25 文件 4.93GB）
REM  本地检测：动态扫描脚本所在目录，不写死任何绝对路径
REM ================================================================

rem ---------- 配置区 ----------
set "GPT_SOVITS_REPO_URL=https://github.com/RVC-Boss/GPT-SoVITS.git"
set "GPT_SOVITS_DIR=TTS model\GPT-SoVITS"
set "GGUF_REPO=cstr/cosyvoice3-0.5b-2512-GGUF"
set "GGUF_DIR=TTS model\CosyVoice3"
set "PM_DIR=TTS model\GPT-SoVITS\GPT_SoVITS\pretrained_models"
set "WLIST=%~dp0gpt_sovits_weights_list.txt"
rem HF 端点：国内网络可改为 https://hf-mirror.com（免加速直连）
set "HF_ENDPOINT=https://hf-mirror.com"
set "HF_RAW=%HF_ENDPOINT%/lj1995/GPT-SoVITS/resolve/main"
rem 并发下载数（1-6，越大越快但可能被服务端限速）
set "PARALLEL=3"
rem 开关: 1=执行 0=跳过
set "GPT_SOVITS_CODE=1"
set "WEIGHTS=1"
rem GGUF_SET: q4(约0.9GB) full(约2.3GB) all(约3.7GB) none(跳过)
set "GGUF_SET=q4"
set "MAX_RETRY=3"
rem ASR 识别模型（Faster Whisper large-v3；语音识别 0c 用）
if not defined ASR_SET set "ASR_SET=1"
set "FW_DIR=TTS model\GPT-SoVITS\tools\asr\models\faster-whisper-large-v3"
set "FW_REPO=Systran/faster-whisper-large-v3"
set "FW_HF_FALLBACK=https://huggingface.co"
rem ------------------------------

rem ---- 下载进度显示（只读监视器；下载本身仍由 curl 负责）----
set "PY_EXE="
if exist "%~dp0.venv\Scripts\python.exe" set "PY_EXE=%~dp0.venv\Scripts\python.exe"
if not defined PY_EXE (
    where python >nul 2>&1 && set "PY_EXE=python"
)
set "PROG_TOOL=%~dp0tools\download_progress.py"
if not exist "%PROG_TOOL%" set "PROG_TOOL="

echo [0/5] 前置工具与本地资产检测...
where git >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 git，请安装 Git for Windows 并加入 PATH。
    exit /b 1
)
where curl >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 curl（Win10 1803+ 系统自带）。
    exit /b 1
)
if not exist "%WLIST%" (
    echo [错误] 未找到权重清单 %WLIST%
    exit /b 1
)
echo   git / curl / 权重清单就绪。

rem ---- 本地资产盘点（动态，无硬编码绝对路径）----
set /a LOCAL_CODE=0
set /a LOCAL_GGUF=0
if exist "%GPT_SOVITS_DIR%\.git" (
    set /a LOCAL_CODE=1
    echo   [检测] GPT-SoVITS 代码已存在: %GPT_SOVITS_DIR%（将执行增量更新）
)
if exist "%GGUF_DIR%" for %%F in ("%GGUF_DIR%\*.gguf") do set /a LOCAL_GGUF+=1
if %LOCAL_GGUF% GTR 0 echo   [检测] 发现已有 GGUF 文件 %LOCAL_GGUF% 个（已完成的部分将自动跳过）
if exist "%PM_DIR%" for /f %%C in ('dir /s /b /a-d "%PM_DIR%" 2^>nul ^| find /c /v ""') do echo   [检测] 发现已有权重文件 %%C 个（不足的将自动断点续传）

if "%GPT_SOVITS_CODE%"=="1" goto :stage_github
echo.
echo [跳过] GPT-SoVITS 代码（GPT_SOVITS_CODE=0）
goto :stage_hf

:stage_github
echo.
echo [1/5] 检测 GitHub 连接: %GPT_SOVITS_REPO_URL%
set /a TRY=0
:probe_github
set /a TRY+=1
if defined GIT_PROXY_ARG (
    git -c http.proxy=%GIT_PROXY_ARG% ls-remote "%GPT_SOVITS_REPO_URL%" HEAD >nul 2>&1
) else (
    git ls-remote "%GPT_SOVITS_REPO_URL%" HEAD >nul 2>&1
)
if not errorlevel 1 goto :github_ok
if %TRY% EQU 1 (
    for /f "tokens=2*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer 2^>nul') do set "SYS_PROXY=%%B"
    for /f "tokens=2*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable 2^>nul') do set "PROXY_ON=%%B"
    if /i "%PROXY_ON%"=="0x1" if defined SYS_PROXY (
        set "GIT_PROXY_ARG=http://%SYS_PROXY%"
        echo   检测到系统代理 %SYS_PROXY%，改走系统代理重试...
    )
)
if %TRY% GEQ %MAX_RETRY% goto :github_fail
echo   无法连接（第 %TRY%/%MAX_RETRY% 次），2 秒后重试...
timeout /t 2 /nobreak >nul
goto :probe_github

:github_fail
echo.
echo [警告] GitHub 暂时无法访问，跳过 GPT-SoVITS 代码环节。
echo   权重/GGUF 走 HF 端点不受影响，继续执行。
echo   网络恢复后重跑本脚本可补齐 GPT-SoVITS 代码。
goto :stage_hf

:github_ok
echo   GitHub 连接正常。

echo.
echo [2/5] GPT-SoVITS 代码: 浅克隆 / 更新
if exist "%GPT_SOVITS_DIR%\.git" (
    echo   检测到已有仓库，正在拉取更新...
    if defined GIT_PROXY_ARG (
        git -C "%GPT_SOVITS_DIR%" -c http.proxy=%GIT_PROXY_ARG% pull --ff-only
    ) else (
        git -C "%GPT_SOVITS_DIR%" pull --ff-only
    )
    if errorlevel 1 echo   [警告] 拉取失败，保留现有仓库继续。
    goto :stage_hf
)
if defined GIT_PROXY_ARG (
    git -c http.proxy=%GIT_PROXY_ARG% clone --depth 1 "%GPT_SOVITS_REPO_URL%" "%GPT_SOVITS_DIR%"
) else (
    git clone --depth 1 "%GPT_SOVITS_REPO_URL%" "%GPT_SOVITS_DIR%"
)
if errorlevel 1 (
    echo   [警告] 克隆失败。请手动删除 %GPT_SOVITS_DIR% 目录后重跑本脚本。
    goto :github_fail
)

:stage_hf
echo.
echo [3/5] 检测 HF 端点: %HF_ENDPOINT%
set "CODE=000"
for /f %%C in ('curl -s -o nul -L --ssl-no-revoke --max-time 20 -w "%%{http_code}" "%HF_ENDPOINT%/%GGUF_REPO%/resolve/main/README.md" 2^>nul') do set "CODE=%%C"
echo   HTTP 状态码: %CODE%
if "%CODE%"=="000" goto :hf_fail
if %CODE% LSS 400 goto :hf_ok
goto :hf_fail
:hf_ok
echo   HF 端点可达。
goto :stage_gguf
:hf_fail
echo.
echo [错误] HF 端点不可达。可将 HF_ENDPOINT 改为 https://hf-mirror.com 重试。
exit /b 1

:stage_gguf
if not "%GGUF_SET%"=="none" goto :gguf_pick
echo.
echo [跳过] GGUF 权重（GGUF_SET=none）
goto :stage_asr

:gguf_pick
echo.
echo [4/5] CosyVoice3 GGUF（集合: %GGUF_SET%，并行 %PARALLEL% 路）
if not exist "%GGUF_DIR%" mkdir "%GGUF_DIR%"
set "FAILED="
set /a OKCNT=0
if /i "%GGUF_SET%"=="full" goto :set_full
if /i "%GGUF_SET%"=="all" goto :set_all
set "GGUF_LIST=cosyvoice3-llm-q4_k.gguf cosyvoice3-flow-q8_0.gguf cosyvoice3-s3tok-q4_k.gguf cosyvoice3-hift-f16.gguf cosyvoice3-campplus-f16.gguf cosyvoice3-voices.gguf"
goto :gguf_go
:set_full
set "GGUF_LIST=cosyvoice3-llm-f16.gguf cosyvoice3-flow-f16.gguf cosyvoice3-s3tok-f16.gguf cosyvoice3-hift-f16.gguf cosyvoice3-campplus-f16.gguf cosyvoice3-voices.gguf"
goto :gguf_go
:set_all
set "GGUF_LIST=cosyvoice3-llm-f16.gguf cosyvoice3-llm-rl-f16.gguf cosyvoice3-flow-f16.gguf cosyvoice3-s3tok-f16.gguf cosyvoice3-llm-q4_k.gguf cosyvoice3-llm-rl-q4_k.gguf cosyvoice3-flow-q8_0.gguf cosyvoice3-s3tok-q4_k.gguf cosyvoice3-hift-f16.gguf cosyvoice3-campplus-f16.gguf cosyvoice3-voices.gguf"
:gguf_go
set /a GGUF_TOTAL_N=0
for %%F in (%GGUF_LIST%) do set /a GGUF_TOTAL_N+=1
for %%F in (%GGUF_LIST%) do call :download_gguf %%F
call :show_progress_gguf
call :wait_jobs
echo   GGUF 排队完成: %OKCNT%/%GGUF_TOTAL_N%
goto :verify_gguf

:verify_gguf
rem 弱校验：每个文件须存在且 >=100KB（完整校验依赖重跑续传补齐）
set "FAILED_G="
for %%F in (%GGUF_LIST%) do if not exist "%GGUF_DIR%\%%F" set "FAILED_G=%FAILED_G% %%F"
for %%F in (%GGUF_LIST%) do if exist "%GGUF_DIR%\%%F" for %%Z in ("%GGUF_DIR%\%%F") do if %%~zZ LSS 100000 set "FAILED_G=%FAILED_G% %%F"
if defined FAILED_G (
    echo   [警告] 以下 GGUF 不完整:%FAILED_G%
    echo   重跑本脚本将自动断点续传补齐。
) else (
    echo   GGUF 全部就绪。
)
goto :stage_asr

:download_gguf
set "F=%~1"
if exist "%GGUF_DIR%\%F%" (
    echo   [跳过] %F%
    set /a OKCNT+=1
    exit /b 0
)
echo   [排队] %F%
start "" /b cmd /c curl -s -S -L -C - --retry 3 --retry-delay 2 --ssl-no-revoke --connect-timeout 15 --max-time 3600 -o "%GGUF_DIR%\%F%" "%HF_ENDPOINT%/%GGUF_REPO%/resolve/main/%F%"
exit /b 0

:stage_weights
if not "%WEIGHTS%"=="1" goto :stage_asr
echo.
echo [6/6] GPT-SoVITS 预训练权重（25 文件 / 4.93 GB，v1+v2+v3+v4+v2Pro 全版本，并行 %PARALLEL% 路）
if not exist "%PM_DIR%" mkdir "%PM_DIR%"
if not exist "%PM_DIR%\chinese-hubert-base" mkdir "%PM_DIR%\chinese-hubert-base"
if not exist "%PM_DIR%\chinese-roberta-wwm-ext-large" mkdir "%PM_DIR%\chinese-roberta-wwm-ext-large"
if not exist "%PM_DIR%\gsv-v2final-pretrained" mkdir "%PM_DIR%\gsv-v2final-pretrained"
if not exist "%PM_DIR%\gsv-v4-pretrained" mkdir "%PM_DIR%\gsv-v4-pretrained"
if not exist "%PM_DIR%\models--nvidia--bigvgan_v2_24khz_100band_256x" mkdir "%PM_DIR%\models--nvidia--bigvgan_v2_24khz_100band_256x"
if not exist "%PM_DIR%\sv" mkdir "%PM_DIR%\sv"
if not exist "%PM_DIR%\v2Pro" mkdir "%PM_DIR%\v2Pro"
set "W_OK=0"
set "W_SKIP=0"
set "W_FAIL_N=0"
set "FAILED_W="
echo   逐文件校验已完成项（不足的自动断点续传）...
for /f "usebackq tokens=1,2 delims=|" %%S in ("%WLIST%") do call :check_weight %%S "%%T"
echo   已完成 %W_SKIP% 项，需下载 %W_FAIL_N% 项
if %W_FAIL_N% EQU 0 goto :done
echo   开始并行下载...
for /f "usebackq tokens=1,2 delims=|" %%S in ("%WLIST%") do call :queue_weight %%S "%%T"
call :show_progress_weights
call :wait_jobs
set "FAILED_W="
for /f "usebackq tokens=1,2 delims=|" %%S in ("%WLIST%") do call :verify_weight %%S "%%T"
if defined FAILED_W (
    echo   权重失败清单:%FAILED_W%
    echo   下次运行将自动从断点继续。
    exit /b 1
)
goto :done

:check_weight
rem 跳过清单里的非数据行（说明注释的"大小"字段不是数字）
for /f "delims=0123456789" %%A in ("%~1") do exit /b 0
set "W_SIZE=%~1"
set "W_REL=%~2"
set "W_OUT=%PM_DIR%\%W_REL%"
if not exist "%W_OUT%" exit /b 0
for %%Z in ("%W_OUT%") do set "W_ACT=%%~zZ"
if %W_ACT% GEQ %W_SIZE% (
    set /a W_SKIP+=1
    exit /b 0
)
exit /b 0

:queue_weight
rem 跳过清单里的非数据行（说明注释的"大小"字段不是数字）
for /f "delims=0123456789" %%A in ("%~1") do exit /b 0
set "W_SIZE=%~1"
set "W_REL=%~2"
set "W_OUT=%PM_DIR%\%W_REL%"
if exist "%W_OUT%" for %%Z in ("%W_OUT%") do if %%~zZ GEQ %W_SIZE% exit /b 0
set /a W_FAIL_N+=1
start "" /b cmd /c curl -s -S -L -C - --retry 5 --retry-delay 2 --ssl-no-revoke --connect-timeout 15 --max-time 7200 -o "%W_OUT%" "%HF_RAW%/%W_REL%"
set /a W_INFLIGHT+=1
if %W_INFLIGHT% GEQ %PARALLEL% (
    call :wait_one
    set /a W_INFLIGHT-=1
)
exit /b 0

:wait_one
rem 计数式并发闸门：仅统计 curl 进程数，降至并发上限以下才继续排队
:wait_one_loop
set /a RUNNING=0
for /f %%N in ('tasklist /FI "IMAGENAME eq curl.exe" 2^>nul ^| find /c /i "curl.exe"') do set /a RUNNING=%%N
if %RUNNING% LSS %PARALLEL% exit /b 0
timeout /t 2 /nobreak >nul
goto :wait_one_loop

:wait_jobs
:wait_jobs_loop
tasklist /FI "IMAGENAME eq curl.exe" 2>nul | find /I "curl.exe" >nul
if errorlevel 1 exit /b 0
timeout /t 2 /nobreak >nul
goto :wait_jobs_loop

:verify_weight
rem 跳过清单里的非数据行（说明注释的"大小"字段不是数字）
for /f "delims=0123456789" %%A in ("%~1") do exit /b 0
set "W_SIZE=%~1"
set "W_REL=%~2"
set "W_OUT=%PM_DIR%\%W_REL%"
if not exist "%W_OUT%" (
    echo   [失败] %W_REL%（文件不存在）
    set "FAILED_W=%FAILED_W% %W_REL%"
    exit /b 0
)
for %%Z in ("%W_OUT%") do set "W_ACT=%%~zZ"
if %W_ACT% LSS %W_SIZE% (
    echo   [失败] %W_REL%（大小 %W_ACT% 不足 %W_SIZE%，下次运行将从断点继续）
    set "FAILED_W=%FAILED_W% %W_REL%"
    exit /b 0
)
set /a W_OK+=1
exit /b 0

:show_progress_gguf
rem GGUF 由后台静默 curl 并行下载，这里用只读监视器统计已落盘字节
if not defined PROG_TOOL exit /b 0
if not defined PY_EXE exit /b 0
set "PROG_MANIFEST=%TEMP%\gguf_progress.txt"
> "%PROG_MANIFEST%" (for %%F in (%GGUF_LIST%) do @echo 0^|%~dp0%GGUF_DIR%\%%F)
"%PY_EXE%" "%PROG_TOOL%" --manifest "%PROG_MANIFEST%" --url-base "%HF_ENDPOINT%/%GGUF_REPO%/resolve/main" --title "CosyVoice3 GGUF 下载中"
del "%PROG_MANIFEST%" >nul 2>&1
exit /b 0

:show_progress_weights
rem 权重由后台静默 curl 并行下载；预期大小取自权重清单，故无需 HEAD 探测
if not defined PROG_TOOL exit /b 0
if not defined PY_EXE exit /b 0
set "PROG_MANIFEST=%TEMP%\weights_progress.txt"
> "%PROG_MANIFEST%" (for /f "usebackq tokens=1,2 delims=|" %%S in ("%WLIST%") do @echo %%S^|%~dp0%PM_DIR%\%%~T)
"%PY_EXE%" "%PROG_TOOL%" --manifest "%PROG_MANIFEST%" --title "GPT-SoVITS 权重下载中"
del "%PROG_MANIFEST%" >nul 2>&1
exit /b 0

:stage_asr
if not "%ASR_SET%"=="1" goto :done
echo.
echo [5/6] ASR 识别模型（Faster Whisper large-v3，6 文件 / 约 3 GB）
if not exist "%FW_DIR%" mkdir "%FW_DIR%"
rem 注意：large-v3 仓库没有 vocabulary.txt（上游 fasterwhisper_asr.py 对 large-v3 亦主动移除）
set "FW_LIST=config.json model.bin tokenizer.json preprocessor_config.json vocabulary.json"
set "FAILED_A="
for %%F in (%FW_LIST%) do if exist "%FW_DIR%\%%F" (
    echo   [跳过] %%F
) else (
    echo   [下载] %%F（渠道1: %HF_ENDPOINT%）
    curl -S -L -C - --retry 3 --retry-delay 2 --ssl-no-revoke --connect-timeout 15 --max-time 7200 -o "%FW_DIR%\%%F" "%HF_ENDPOINT%/%FW_REPO%/resolve/main/%%F%"
    if errorlevel 1 (
        echo   [渠道2] 改用官方 HuggingFace 直连...
        curl -S -L -C - --retry 3 --retry-delay 2 --ssl-no-revoke --connect-timeout 15 --max-time 7200 -o "%FW_DIR%\%%F" "%FW_HF_FALLBACK%/%FW_REPO%/resolve/main/%%F%"
    )
)
set "FAILED_A2="
for %%F in (%FW_LIST%) do if not exist "%FW_DIR%\%%F" set "FAILED_A2=%FAILED_A2% %%F"
if defined FAILED_A2 (
    echo   [警告] 以下 ASR 文件不完整:%FAILED_A2%
    echo   首次使用识别功能时也会自动下载；重跑本脚本可补齐。
) else (
    echo   ASR 模型全部就绪。
)
goto :done

:done
echo.
echo ================ 结果汇总 ================
echo   ASR 识别模型:   %FW_DIR%
echo   GPT-SoVITS 代码:  %GPT_SOVITS_DIR%\
echo   GGUF:      %GGUF_DIR%\（集合 %GGUF_SET%）
echo   GPT-SoVITS 权重:  %PM_DIR%\
echo 全部完成。
exit /b 0
