# WT-NameRelay 第三方组件与许可证

本清单依据 2026 年对项目源码、虚拟环境、PyInstaller 配置、随包二进制（**逐二进制 PE 导入表与代码级特征实测**）
与各下载脚本的重新核对而成，并记录 2026-10 的一轮全面许可审计结论。它不构成法律意见。
项目原创部分的使用声明不替代、限制或覆盖下列第三方许可证授予的权利。

> **版本口径**：本清单的版本号取自**实测**（`pyvenv.cfg`、各 `dist-info/METADATA`、DLL 版本串），
> 不取自记忆或沿用旧记录。`app/i18n.py` 与 `app/widgets/license_dialog.py` 内展示的版本串必须与本清单一致。

## 随发布包分发的运行时组件

| 组件 | 实际版本 | 用途 | 官方项目地址 | 许可证 | 随包分发 |
| --- | --- | --- | --- | --- | --- |
| CPython | 3.12.10 | Python 运行时 | https://www.python.org/ | PSF License 2.0，发行包另捆绑 libffi / bzip2 / Tcl-Tk / expat / libmpdec / zlib 等组件（各有其许可） | 源码分发（用户自建 venv）；EXE 构建会打包 | 
| PySide6 / PySide6-Essentials / PySide6-Addons / shiboken6 | 6.7.3 | Python Qt 绑定与运行时支持 | https://pyside.org/ | LGPL-3.0 / GPL-3.0；本项目采用 LGPL 动态链接路径 | 是 |
| Qt | 6.7.3 | 桌面界面、多媒体、图形与平台插件 | https://www.qt.io/ | LGPL-3.0 / GPL-3.0；本项目采用 LGPL 动态链接路径 | 是 |
| PyQtGraph | 0.13.7 | 音频时间轴、波形与图形交互 | https://github.com/pyqtgraph/pyqtgraph | MIT；**随包颜色映射数据 `colors/maps/CET*.csv`（63 个文件）为 CC-BY-4.0** | 是 |
| NumPy | 1.26.4 | PyQtGraph 数值数组支持 | https://numpy.org/ | BSD-3-Clause；其发行许可证还包含捆绑组件声明 | 是 |
| OpenSSL | 3.0.16 | Python/Qt TLS 运行时依赖 | https://www.openssl.org/ | Apache-2.0 | 是 |
| FFmpeg / ffprobe（**本仓库自建**最小 LGPL 构建） | N-125829-gfe953596e9 | 音频探测、波形解析、试听缓存和正式导出 | https://github.com/FFmpeg/FFmpeg | LGPL-3.0-or-later —— **经二进制实测确认**，非仅凭自报（见 [`FFMPEG_BUILD_INFO.md`](FFMPEG_BUILD_INFO.md)） | 是 |
| libmp3lame（随包 `libmp3lame-0.dll`） | 3.100 | MP3 导出编码 | https://lame.sourceforge.io/ | LGPL-2.0-or-later | 是 |
| libopus（随包 `libopus-0.dll`） | 1.6.1 | Opus 导出编码 | https://opus-codec.org/ | BSD-3-Clause | 是 |
| zlib（随包 `zlib1.dll`） | 1.3.2 | PNG（频谱图）压缩 | https://zlib.net/ | Zlib | 是 |
| libgcc / libwinpthread（随包 `libgcc_s_seh-1.dll`、`libwinpthread-1.dll`） | GCC 16.2.0 / mingw-w64 14.0.0 | mingw-w64 C 运行时与线程支持 | https://www.mingw-w64.org/ | GPL-3.0-or-later **带 GCC Runtime Library Exception 3.1** / MIT AND BSD-3-Clause | 是 |
| **Qt WebEngine（含 Chromium）** | 6.7.3（随 PySide6-Addons） | 内嵌浏览器：API 渠道页的 TTS-Hub 管理台渲染（进程内协议，无监听端口） | https://wiki.qt.io/QtWebEngine | **LGPL-3.0（动态链接，与 PySide6 同路径；Qt 亦提供 GPL-3.0 备选）** + 内嵌 Chromium **BSD-3-Clause** 及其捆绑第三方组件 | 是（PyInstaller 构建会一并打包 `Qt6WebEngineCore.dll`、`QtWebEngineProcess.exe` 等） |
| Mesa（随包 `opengl32sw.dll`） | 随 PySide6 6.7.3 | 无 GPU/驱动异常时的软件 OpenGL 回退 | https://www.mesa3d.org/ | MIT（Mesa 发行体另有 SGI-B-2.0 / BSL-1.0 / Apache-2.0 / GPL-* 组件，随上游声明） | 是 |
| Microsoft Visual C++ Runtime / UCRT（10 个 DLL） | 随 PySide6 6.7.3 | CPython、Qt 与扩展模块运行支持 | https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist | Microsoft 可再发行组件条款（非自由许可，**本项目不附其正文**，仅登记来源与范围） | 是 |
| Bootstrap Icons | 1.11.3 | 左侧导航栏功能图标（9 个 SVG，源自官方包） | https://icons.getbootstrap.com/ | MIT | 是（源码树；打包面见下文） |
| TTS-Hub 传递依赖：certifi | 2026.7.22 | TTS-Hub 的 CA 证书束 | https://github.com/certifi/python-certifi | **MPL-2.0**（文件级著佐权；须随附正文） | EXE 构建会打包；源码分发由 pip 自带 |
| python-multipart（TTS-Hub server 可选依赖） | 0.0.32 | 内嵌管理台的表单解析 | https://github.com/Kludex/python-multipart | **Apache-2.0** | 同上 |
| TTS-Hub 其余传递依赖（anyio / click / h11 / httpcore / idna / annotated-types / annotated-doc / typing-extensions / typing-inspection / pydantic / pydantic-core（含原生扩展）/ starlette / fastapi / uvicorn / httpx / PyYAML） | 见各包 dist-info | TTS-Hub 与内嵌管理台运行支持 | 见各包 PyPI | MIT / BSD-3-Clause / PSF-2.0 / Apache-2.0（pydantic-core 另含 Rust 依赖，均宽松或双许可） | 同上 |
| TTS-Hub（**可选组件**） | 0.2.3 | API 渠道：云端合成、内嵌管理台 | 维护者自研（Diderde，同仓库作者；与修改版同源分发） | GPL-3.0-only | 同上 |
| audioprep_contract | 冻结件（114 文件，`SHA256SUMS.txt` 可校验） | 音频处理页的契约冻结件，`app/services/audioprep_runtime.py` 运行时读取 | 随项目分发的第三方契约包 | MIT（Copyright (c) 2026 AudioPrep contributors） | 是（源码树；未进 qrc） |
| vtcore 的 Rust 依赖 | 见 [`licenses/rust/manifest.json`](licenses/rust/manifest.json) | `.vt` 容器、Ed25519 签名、整包校验 | https://crates.io/ | 见下文「Rust 依赖」 | 是（**预编译 wheel**） |

> **「随包分发」列的读法**：本项目对外可以是**源码分发**，也可以是 PyInstaller 构建的 **EXE/onedir 目录**。
> 后者会把上表里标「是」的组件**二进制**一并打包，因此这些组件的许可正文必须随发布物可获取 —— 见
> 「随包许可证文件」与「已知许可注意事项」。

内置 FFmpeg 由**本仓库自建**，参数为
`--enable-version3 --enable-shared --disable-static --disable-autodetect --disable-network`，
**未启用** `--enable-gpl`、`--enable-nonfree`、`--enable-chromaprint`。
发布包只携带应用实际调用的 `ffmpeg.exe`、`ffprobe.exe` 与所需共享 DLL，**不携带 `ffplay.exe`**。

### 内置 FFmpeg 构建启用的外部库

外部依赖**只有三个**：`libmp3lame`（MP3 编码）、`libopus`（Opus 编码）、`zlib`（PNG）。
FLAC 与 AAC(m4a) 使用 FFmpeg **自带**编码器；`ebur128`、`loudnorm`、`silencedetect`、
`showspectrumpic`、`anullsrc`、`aresample`、`aformat`、`atrim`、`asetpts`、`concat`
与 `-f lavfi`（libavdevice 的 lavfi indev）全部是**内置件**，未做裁剪。
另有 mingw 运行时随包（`libgcc_s_seh-1.dll`、`libwinpthread-1.dll`）与 CRT。

**链接方式必须按 PE 导入表核对，不能按印象写**：`libmp3lame`、`libopus` 与 **`zlib1.dll`**
都是**动态导入**（`--enable-shared` + 工具链的共享 libz-1.dll，其导出名为 `zlib1.dll`）。
`avcodec-63.dll` / `avformat-63.dll` / `ffmpeg.exe` 的导入表都要求 `zlib1.dll`；
**该 DLL 必须随包**，否则 Windows 在加载期直接以 `0xC0000135`（`STATUS_DLL_NOT_FOUND`）失败 ——
2026-09 换件曾漏随附，详见 [`FFMPEG_BUILD_INFO.md`](FFMPEG_BUILD_INFO.md)「随包 DLL 集合」。
`build_release.py` 与 `04-finalize.sh` 均不再依赖任何自报输出；后者新增了导入表闭包核对步（5b）。

这些组件的许可原文逐字收录在 [`licenses/ffmpeg/`](licenses/ffmpeg/)，共 **10 个文件**（7 份原文 + 3 份清单），
逐条记录见 [`licenses/ffmpeg/MANIFEST.md`](licenses/ffmpeg/MANIFEST.md)；机器可校验清单为
`licenses/ffmpeg/manifest.json`，用 `python tools/verify_ffmpeg_licenses.py` 可逐文件复算内容哈希。
各组件的**实际版本**见 `licenses/ffmpeg/measured-versions.json`。

> **历史**：当时的随包构建来自 BtbN FFmpeg-Builds 的 `win64-lgpl-shared`，
> 启用了 **57 个外部组件**，并且把 GPL-2.0-or-later 的 **FFTW 3.3.11** 经 chromaprint
> 静态链入了 `avformat-63.dll` —— 名义 LGPL、实为 GPL。换成自建最小构建后，
> 该问题连同 54 个本程序用不到的组件一并消除，随包二进制约 **145 MB → 31 MB**。
> 完整取证与根因见 [`FFMPEG_BUILD_INFO.md`](FFMPEG_BUILD_INFO.md) §2。

#### 必须处理的许可问题

1. ~~**`avformat-63.dll` 含 GPL 组件，不能标注为 LGPL。**~~ —— **已解决。**
   原构建把 GPL-2.0-or-later 的 FFTW 3.3.11 经 chromaprint（`-DFFT_LIB=fftw3`）静态链入
   `avformat-63.dll`（二进制内实测到版本串、wisdom 格式串与 948 个 `fftw_codelet_*` 符号），
   根因是 BtbN 的 `25-fftw3.sh` / `50-chromaprint.sh` **缺少 lgpl 闸门**
   （对照 `50-x264.sh` 的 `[[ $VARIANT == lgpl* ]] && return -1`），
   违反其 README 明示的 *"`lgpl` Lacking libraries that are GPL-only"*。
   处置：改为自建最小构建，**不启用 chromaprint**，GPL 组件随之清零。
   现状由两道闸门守住 —— `python tools/audit_ffmpeg_license.py`（二进制审计）
   与随附许可审计的换件绊线。
2. **弱著佐权项的可替换性**：`libmp3lame` 是 LGPL-2.0-or-later，且随包以**独立 DLL**
   （`libmp3lame-0.dll`）分发，FFmpeg 各库本身也是共享 DLL —— 用户可自行替换为修改版，
   满足 LGPL 对"可替换/可重链"的要求。`zlib`（Zlib 许可）为宽松许可，无此要求。
3. **GCC 运行时例外**：`libgcc_s_seh-1.dll` 适用 GPL-3.0-or-later **带 GCC Runtime Library
   Exception 3.1**，该例外明确允许在不触发 GPL 义务的前提下随非 GPL 程序分发。
   例外原文见 `licenses/ffmpeg/GCC-Runtime-Library-Exception-3.1.txt`。
4. **`libmp3lame` 的对应源码**：LAME 3.100 是 LGPL-2.0-or-later，除正文外还需
   **对应源码可得**（可替换/可重链）。当前 `FFMPEG_BUILD_INFO.md` §4 只披露了 FFmpeg 上游源码，
   **未披露 LAME 与 Opus 的固定版本源码获取方式** —— 公开二进制 Release 前必须补上。
5. **不再涉及的项**：本轮构建不含 FreeType（FTL 署名条款）、libaribb24（上游许可自相矛盾）、
   lcms2（`fastfloat` GPL 插件疑云）、Vulkan shim、aom/dav1d/vpx/webp/libjxl/SVT-AV1/rav1e
   的专利条款类文本等 —— 这些组件均未启用（`--disable-autodetect` + 只显式 enable 三个库）。

可复现核对命令：`.\app\resources\ffmpeg\bin\ffmpeg.exe -buildconf`、
`ffmpeg.exe -encoders`/`-filters`/`-muxers`（列出真正编译进来的外部集成）、
`python tools/audit_ffmpeg_license.py`（二进制许可审计，必须 PASS），
以及 `python tools/verify_ffmpeg_licenses.py`（许可文本完整性）。

> **`ffmpeg -L` 的自报不能作为判定依据。** 它只看 FFmpeg 自身的 configure 开关，
> **看不见**经第三方库（chromaprint → FFTW）间接静态链入的 GPL 代码 —— 这正是历史事故的漏检路径。
> 自报只可用于"与清单对拍"，判定一律以二进制审计为准。

## 开发、测试和打包工具

以下组件安装在开发环境中，但不会作为 Python 包随正式 EXE 分发：

| 组件 | 实际版本 | 用途 | 官方项目地址 | 许可证 |
| --- | --- | --- | --- | --- |
| openpyxl | 3.1.5 | 名称数据库的一次性 Excel 提取 | https://openpyxl.readthedocs.io/ | MIT（**当前 venv 未安装，历史记录**） |
| PyInstaller | 6.11.1 | Windows EXE 打包 | https://pyinstaller.org/ | GPL-2.0-or-later，带允许分发非自由程序的特殊例外（**当前 venv 未安装；若要按 `.spec` 构建必须先装回**） |
| maturin | 1.15.0 | vtcore（Rust 扩展）的本地构建 | https://github.com/PyO3/maturin | MIT OR Apache-2.0（取自包元数据 `License-Expression`） |
| ruff | 0.16.8 | 代码风格检查 | https://github.com/astral-sh/ruff | MIT（开发环境实测版本，未在 `requirements-dev.txt` 中固定） |
| mypy | 2.3.1 | 类型检查 | https://github.com/python/mypy | MIT（开发环境实测版本，未在 `requirements-dev.txt` 中固定） |
| jsonschema | 4.26.0 | audioprep 契约冻结件验证器的 MediaPortSpec / Manifest 校验（`requirements-dev.txt` 固定） | https://github.com/python-jsonschema/jsonschema | MIT（取自包元数据） |

Python 标准库模块没有逐项列入本清单；随包分发的 CPython 解释器许可证已单独附带。

## 运行时下载的可选组件（不随发布包分发）

以下组件由 `start.bat` / `download_tts_verify.bat` 或**应用内的「人声分离」页**在用户机器上按需获取到
`TTS model\`（该目录已加入 `.gitignore`，不随发布包分发）。本项目只提供下载脚本与校验清单，
不复制、不修改、不再分发这些组件本身；使用时请遵守各自的许可证与模型条款。
版本与来源取自脚本中的固定值（2026-10 核对）：

| 组件 | 版本/修订 | 用途 | 来源 | 许可证 |
| --- | --- | --- | --- | --- |
| CrispASR runner（`crispasr-0.8.34+vulkan-py3-none-win_amd64.whl`） | v0.8.34 | CosyVoice3 本地推理服务（`tools/cosyvoice3_shim.py` 调用其绑定） | https://github.com/CrispStrobe/CrispASR 官方 Release 资产 | MIT（`Copyright (c) 2023-2026 The ggml authors`，取自包内 `licenses/LICENSE`） |
| GPT-SoVITS 代码（运行时浅克隆） | 跟随上游默认分支 | 语音微调与推理链路 | https://github.com/RVC-Boss/GPT-SoVITS | MIT（`Copyright (c) 2024 RVC-Boss`，取自本地克隆的 `LICENSE`） |
| GPT-SoVITS CPUFast 分支（运行时浅克隆） | 跟随上游默认分支 | CPU 提速推理入口（工作台「GPT-SoVITS CPUFast」模型项；`app/services/gsv_services.py` 的 CPUFast 档调用其 `api_v2.py`） | https://github.com/baicai-1145/GPT-SoVITS-CPUFast | MIT（`Copyright (c) 2024 RVC-Boss` + `Copyright (c) 2026 白菜工厂1145号员工`，取自本地克隆的 `LICENSE`）。原生 CPU torch 环境由其自带 `uv sync --locked` 搭建 |
| MSST 推理引擎（`ZFTurbo/Music-Source-Separation-Training`） | 独立检出到 `TTS model\MSST` | 人声/背景音分离；`app/services/separation_service.py` 以 subprocess 调用 | https://github.com/ZFTurbo/Music-Source-Separation-Training | MIT（`Copyright (c) 2024 Roman Solovyev (ZFTurbo)`）。**注意**：同名的 MSST-WebUI（SUC-DriverOld）为 **AGPL-3.0，本项目一律不引用、不拷贝** |
| CosyVoice3 权重（GGUF 等） | 跟随上游 | 文本转语音推理模型 | hf-mirror（**实际下载仓为 `cstr/cosyvoice3-0.5b-2512-GGUF`** 社区量化仓；上游为 `FunAudioLLM/Fun-CosyVoice3-0.5B-2512`） | Apache-2.0（上游模型卡 `cardData.license` 声明；社区量化仓与上游许可**经 hf-mirror API 实测同为 Apache-2.0**） |
| GPT-SoVITS 预训练权重（25 个文件） | 见 `gpt_sovits_weights_list.txt` | 微调起点 | hf-mirror | 随各权重上游声明；本清单与校验脚本只做存在性、大小与哈希校验，**不代为声明许可**。25 个文件至少来自 4 个不同上游，逐项归属须人工确认 |
| faster-whisper-large-v3（ASR 模型） | `Systran/faster-whisper-large-v3` | 语音识别（`download_tts_verify.bat` 下载 ≈3.0 GB） | hf-mirror，回退 huggingface.co | **MIT**（HF 模型卡 `cardData.license`，经 hf-mirror API 实测；上游 `openai/whisper-large-v3` 模型卡为 Apache-2.0、`openai/whisper` 主仓为 MIT，按 MIT + Apache-2.0 双覆盖） |
| BandIt v2 DnR 权重（片段对白/效果音/音乐三轨分离） | `zenodo.org/records/12701995` | 人声分离模型权重（应用内下载） | Zenodo 官方记录 | **CC-BY-SA-4.0**（署名 + 相同方式共享）。架构 BandIt / BandIt v2 为 Apache-2.0；DnR 数据集不含日语 |
| RoFormer 社区检查点（音乐素材人声/伴奏） | `AEmotionStudio/roformer-models` | 人声分离模型权重（应用内下载） | hf-mirror | MIT（社区检查点：viperx / unwa / becruily） |
| 上游 GPT-SoVITS 安装器附带获取的资产 | — | UVR5 权重、G2PWModel、`nltk_data`、open_jtalk 词典 | 上游 `install.ps1` / `install.sh` | 各自随上游声明；本清单未逐项覆盖。CPUFast 分支的 G2PW torch 权重（`text/G2PWModel/g2pw.pth`，≈608 MB）与字典资产同走其 `install.ps1` 口径：`baicai1145/g2pw`（ModelScope，随克隆声明的许可） |

> **本项目刻意排除的高风险许可权重**：CC-BY-NC 系列（BandIt v1 权重、Sucial 三件套）**不进默认清单** ——
> 公共 GPL 工具不得替用户接受禁商用条款；应用支持自定义模型目录，由用户自担许可。

GPT-SoVITS 仓库自身包含若干第三方子组件（`GPT_SoVITS/BigVGAN`、`tools/AP_BWE_main`、
`tools/uvr5`、`GPT_SoVITS/text/G2PWModel`、`GPT_SoVITS/text/zh_normalization`、`GPT_SoVITS/f5_tts`、
`GPT_SoVITS/Accel` 等，各自带独立 `LICENSE`），
其许可随克隆一并落在用户机器上，本项目不随包分发；完整依赖树以克隆到的上游仓库为准。

## Rust 依赖（vtcore 扩展）

`vtcore` 是本修改版新增的 Rust 扩展（源码在 `vtcore/`，自身按 **GPL-3.0-only** 授权，见 `MODIFICATION_NOTICE.md`），
提供语音批量的规范字节、`.vt` 容器、Ed25519 签名与整包校验。

**分发形态决定义务，必须分清两条路径：**

1. **源码路径**：接收者用 Cargo 按已入库的 `vtcore/Cargo.lock` 拉取依赖**源码**，
   每个 crate 的发行包内自带许可证文本，随源码分发无需另附。
2. **二进制路径（当前生效）**：`vtcore/wheels/vtcore-0.1.0-cp312-abi3-win_amd64.whl`
   **已入库并随源码附带**（`start.bat` 优先安装它，回退到本 fork 的 GitHub Release 资产），
   wheel 内含 `vtcore.pyd`（571 KB）。**分发二进制必须随附所选许可证正文**，
   因此本仓库把正文收进 [`licenses/rust/`](licenses/rust/)，逐条登记见
   [`licenses/rust/MANIFEST.md`](licenses/rust/MANIFEST.md) 与 `licenses/rust/manifest.json`。

| 口径 | 数量 | 说明 |
| --- | --- | --- |
| `vtcore/Cargo.lock` 的第三方 crate | **53** | 含 `[dev-dependencies]`（serde_json 链）与 target 专用 crate；由 `tools/collect_rust_licenses.py` 从各 crate 的 `Cargo.toml` 机械汇总 |
| wheel 内 CycloneDX SBOM 记录的组件 | **45** | 权威反映**实际进入 `.pyd` 的依赖图**；`serde_json` 等 dev-only 链不在其中 |
| `licenses/rust/` 收录的正文 | **91 份文本 / 44 个 crate 目录** | 逐 crate 逐字取自上游发行包（本机 cargo registry）；`r-efi 6.0.0` 是全清单**唯一**上游连正文都没随包携带的 crate（已核对其 `.crate` 包内 69 个文件与解包目录 70 个文件），因此单列不臆造 |

`r-efi 6.0.0` 的许可表达式是 `MIT OR Apache-2.0 OR LGPL-2.1-or-later`；本项目按 **MIT** 选用，
其上游仓 r-efi/r-efi 的 `LICENSE-MIT.txt` / `LICENSE-APACHE.txt` / `LICENSE-LGPL.txt`
**未随 crates.io 发行包携带** —— 这是上游的打包缺陷，不是本仓库的遗漏。
`r-efi` 只被 `getrandom` 用于 **UEFI target**，**Windows x64 下不会链入** `vtcore.pyd`；
它出现在 SBOM 里是依赖图口径（cargo-cyclonedx 按依赖图生成）而非链接闭包。
一旦上级改为以 UEFI/其他平台分发，必须补上该 crate 的正文。


53 个候选 crate 的版本与许可证表达式由
`./.venv/Scripts/python.exe tools/collect_rust_licenses.py --out temp/rust_licenses.md` 重新生成；
45 个**实际链入** crate 的许可正文由
`./.venv/Scripts/python.exe tools/collect_rust_binary_licenses.py --write` 重新生成、
用同脚本不带 `--write` 校验（哈希口径与 `licenses/ffmpeg/` 相同：LF 归一后算 sha256）。

需要注意的非 MIT/Apache 项（其余均为 `MIT OR Apache-2.0` 一类宽松许可）：

- `curve25519-dalek`、`ed25519-dalek`、`subtle` —— **BSD-3-Clause**（Ed25519 实现链），正文必须随二进制
- `target-lexicon` —— Apache-2.0 **WITH LLVM-exception**
- `unicode-ident` —— `(MIT OR Apache-2.0) AND Unicode-3.0`：Unicode 许可证要求保留其版权与许可声明，**不得移除**
- `memchr` —— `Unlicense OR MIT`
- `fiat-crypto`、`r-efi` —— 多项可选许可（分别含 BSD-1-Clause、LGPL-2.1-or-later），本项目按宽松项选用
- `r-efi` 只被 `getrandom` 用于 UEFI target，**Windows x64 下不会链入** `vtcore.pyd`；
  它出现在 SBOM 里是依赖图口径的结果，不代表随二进制分发

**若将来改为只分发 wheel 而不再随源码附带 `vtcore/` 源码**，`licenses/rust/` 的正文仍是必需项，
并且必须重新执行一次本清单审计。

## 美术、字体和图标

- `app/resources/author_avatar.png`（原项目 logo 高清版，随应用打包）与应用程序图标：由用户提供，
  并已明确允许随本项目发布包分发。
- **左侧导航栏的 9 个功能 SVG 图标取自官方 Bootstrap Icons 1.11.3（MIT）**，
  文件头保留上游的 `class="bi bi-*"` 标记；许可原文见
  [`app/resources/icons/bootstrap-icons-LICENSE.txt`](app/resources/icons/bootstrap-icons-LICENSE.txt)
  与 [`licenses/Bootstrap-Icons-MIT.txt`](licenses/Bootstrap-Icons-MIT.txt)。
  它们通过文件系统路径加载（`app/widgets/nav_rail.py`），**不进 `resources.qrc`**；
  PyInstaller 构建若不额外收 `app/resources/icons/`，图标与许可文本都不会进包 —— 打包时必须一并收集。
- 应用使用系统字体回退，没有随包分发第三方字体。

## 随包许可证文件

发布目录中的 `licenses/` 包含：

- `Python-PSF-2.0.txt` —— CPython 解释器条款
- `CPython-Bundled-Components.txt` —— CPython 发行包**捆绑组件**的版权与许可声明（libffi / bzip2 / Tcl-Tk / expat / libmpdec / zlib 等）
- `LGPL-3.0.txt` —— PySide6 / Qt / Qt WebEngine 的 LGPL 路径文本
- `GPL-3.0.txt` —— PySide6/Qt 的 GPL 备选路径文本；本修改版新增代码同样按 GPL-3.0-only 授权，仅第 3 版，见 `MODIFICATION_NOTICE.md`
- `FFmpeg-LGPL-3.0-or-later.txt`
- `PyQtGraph-MIT.txt`
- `pyqtgraph-CET-CC-BY-4.0.txt` —— pyqtgraph 随包颜色映射数据的 CC-BY-4.0 正文
- `NumPy-BSD-3-Clause.txt`
- `OpenSSL-Apache-2.0.txt` —— Apache-2.0 正文；**同时为 `python-multipart` 的适用文本**（同一份标准正文，不重复收录）
- `certifi-MPL-2.0.txt` —— MPL-2.0 正文
- `Bootstrap-Icons-MIT.txt` —— 导航图标许可（与 `app/resources/icons/` 内那份逐字一致）
- `Mesa-MIT.txt` —— 软件 OpenGL 回退库许可
- `Chromium-BSD-3-Clause.txt` —— Qt WebEngine 内嵌 Chromium 的 BSD-3-Clause 正文
- `QtWebEngine-Chromium-Notice.md` —— Qt WebEngine / Chromium 使用与授权路径声明
- `Chromium-Third-Party-Notices-Index.md` —— Chromium 捆绑第三方组件的**索引与边界声明**（非全量名录）
- `Microsoft-VC-Runtime-Redistributable.txt` —— MSVC/UCRT 运行时随包分发的**来源与范围登记**（非微软许可正文）
- `rust-aggregated.txt` —— `licenses/rust/` 45 个 crate 许可正文的**单文件汇编**（应用内「关于与许可」页读它；逐字节相同的正文只印一次并标注指回位置）
- `openpyxl-MIT.txt`
- `PyInstaller-GPL-2.0-with-exception.txt`

`licenses/ffmpeg/`（子目录，共 **10 个文件**）收录**现自建最小构建**实际链接组件的许可原文 **7 份**
（libmp3lame 的 LGPL-2.0-or-later、Opus 的 BSD-3-Clause、zlib、GCC GPL-3.0 与运行时例外、mingw-w64 CRT 等），
另有 `MANIFEST.md` 逐条记录与 `manifest.json` / `measured-versions.json` 机器可校验清单；
校验命令 `python tools/verify_ffmpeg_licenses.py`（当前 7/7 哈希一致），二进制侧另有
`python tools/audit_ffmpeg_license.py`（结论：所有二进制仅含 LGPL/宽松许可组件）。
旧 BtbN 构建时代的 91 份许可（含 FFTW 的 GPL-2.0-or-later 正文与各类专利文本）已随
换建清零，历史取证见 [`FFMPEG_BUILD_INFO.md`](FFMPEG_BUILD_INFO.md) §2。

`licenses/rust/`（子目录，45 个 crate 目录 + `manifest.json` / `MANIFEST.md`）收录随预编译扩展
分发的 Rust 依赖许可正文；校验命令 `python tools/collect_rust_binary_licenses.py`。

**一致性由脚本与测试守住**：`python tools/verify_license_catalog.py` 核对「本节点名的文件 ↔ `licenses/` 实际内容 ↔
`license_dialog.py` 的页列表 ↔ `resources.qrc` 的嵌入条目」四者互相覆盖，
对应随附的许可目录校验。**不要手工改本节点名的清单而不改对应文件** —— 校验会失败。

NumPy 的许可证文件应原样保留，因为其中包含其发行包捆绑组件的版权和许可证声明。
Qt/PySide6、Qt WebEngine 与 FFmpeg 使用动态共享库形式分发；用户可在不修改 WT-NameRelay 原创代码的
情况下替换接口兼容的共享库（LGPL 的可替换/可重链要求）。

> **应用内许可查看器与文档的关系**：`app/widgets/license_dialog.py` 的页列表是**运行时可见**的子集
> （它受 `resources.qrc` 嵌入约束，嵌不了 92 份 Rust 文本）；完整集合以发布目录的 `licenses/` 为准。
> 查看器里的每一页都必须同时存在「磁盘文件」与「qrc 条目」，否则该页只会显示"许可证资源不可用。"

## 已知许可注意事项

- 项目原创部分采用根目录 `LICENSE` 中的 WT-NameRelay Source-Available License 1.0；它不是 OSI 认可的开源许可证。
- “禁止二次售卖”只描述作者对原创部分与官方发布包的使用要求，不限制第三方许可证已经授予的权利。
- FFmpeg 部分：**不能只以二进制自身 `-L` 输出为依据**。该输出报 `LGPL-3.0-or-later`，
  但历史构建的 `avformat-63.dll` 实测内含 GPL-2.0-or-later 的 FFTW 3.3.11（经 chromaprint 静态链入）。
  现行构建已清零，判定以 `python tools/audit_ffmpeg_license.py`（PE 导入表 + 代码级特征，屏蔽 configure 行）为准。
  逐库清单与许可原文见 `licenses/ffmpeg/`，版本与源码披露见 `FFMPEG_BUILD_INFO.md`；
  公开二进制 Release 前仍须附带或同服务器托管**各库固定版本**的对应源码（**含 LAME 3.100**，目前尚未披露），
  若更换 FFmpeg 构建必须重新执行许可证与构建参数审计。
- **随包 DLL 集合必须与 PE 导入表闭包一致**：`zlib1.dll` 曾漏随附（2026-09 修复），
  症状是干净机器上 FFmpeg 全线 `0xC0000135`，而开发机被 PATH 里的同名 DLL 掩盖。
  换件后必须跑 `04-finalize.sh` 的 5b 步或等价核对。
- 修改与新增代码（含内嵌的维护者自研组件 TTS-Hub）按 **GPL-3.0-only** 授权；原始
  WT-NameRelay 代码仍按 Source-Available License 1.0。两者组合分发时，整体应按
  GPL-3.0-only 提供源码，同时遵守原始许可的全部条款（非商业、署名、同许可分享）。
- TTS-Hub 为**可选组件**：未安装时应用正常可用，仅「API 渠道」功能降级并给出提示。
  它当前以 editable 安装指向仓库外目录（本机私有路径，此处不展开），**按 README 的安装步骤不可复现** ——
  发布或交接前需改为可复现的获取方式。
- `audioprep_contract/` 是第三方 MIT 契约冻结件，既是运行时读取的必需内容，
  也应在发布物里可获取其 `LICENSE`。
- 本清单的**已知盲区**（`tools/verify_license_catalog.py` 也无法覆盖）：
  「某个随包二进制是否真的只含 X 许可」需要二进制级审计，本清单只登记与交叉核对"文本是否齐备、点名是否存在"；
  运行时下载的模型权重许可需人工向上游确认；本清单没有经过专业律师审核。
