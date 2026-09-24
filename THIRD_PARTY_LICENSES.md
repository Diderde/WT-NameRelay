# WT-NameRelay 第三方组件与许可证

本清单依据 2026-08-19 的项目源码、虚拟环境、PyInstaller 配置和实际 Windows 构建内容重新核对。它不构成法律意见。项目原创部分的使用声明不替代、限制或覆盖下列第三方许可证授予的权利。

## 随发布包分发的运行时组件

| 组件 | 实际版本 | 用途 | 官方项目地址 | 许可证 | 随 EXE 分发 |
| --- | --- | --- | --- | --- | --- |
| CPython | 3.11.5（Anaconda 构建） | Python 运行时 | https://www.python.org/ | PSF License 2.0 | 是 |
| PySide6 | 6.7.3 | Python Qt 绑定 | https://pyside.org/ | LGPL-3.0 / GPL-3.0；本项目采用 LGPL 动态链接路径 | 是 |
| PySide6-Essentials | 6.7.3 | Qt Core、Gui、Widgets 等 | https://pypi.org/project/PySide6-Essentials/ | LGPL-3.0 / GPL-3.0；本项目采用 LGPL 动态链接路径 | 是 |
| PySide6-Addons | 6.7.3 | QtMultimedia 等附加模块 | https://pypi.org/project/PySide6-Addons/ | LGPL-3.0 / GPL-3.0；本项目采用 LGPL 动态链接路径 | 是 |
| shiboken6 | 6.7.3 | PySide6 运行时支持 | https://pypi.org/project/shiboken6/ | LGPL-3.0 / GPL-3.0；本项目采用 LGPL 动态链接路径 | 是 |
| Qt | 6.7.3 | 桌面界面、多媒体、图形与平台插件 | https://www.qt.io/ | LGPL-3.0 / GPL-3.0；本项目采用 LGPL 动态链接路径 | 是 |
| PyQtGraph | 0.13.7 | 音频时间轴、波形与图形交互 | https://github.com/pyqtgraph/pyqtgraph | MIT | 是 |
| NumPy | 1.26.4 | PyQtGraph 数值数组支持 | https://numpy.org/ | BSD-3-Clause；其发行许可证还包含捆绑组件声明 | 是 |
| OpenSSL | 3.0.10 | Python/Qt TLS 运行时依赖 | https://www.openssl.org/ | Apache-2.0 | 是 |
| FFmpeg / ffprobe（**本仓库自建**最小 LGPL 构建） | N-125829-gfe953596e9 | 音频探测、波形解析、试听缓存和正式导出 | https://github.com/FFmpeg/FFmpeg | LGPL-3.0-or-later —— **经二进制实测确认**，非仅凭自报（见 [`FFMPEG_BUILD_INFO.md`](FFMPEG_BUILD_INFO.md)） | 是 |
| libmp3lame（随包 `libmp3lame-0.dll`） | 3.100 | MP3 导出编码 | https://lame.sourceforge.io/ | LGPL-2.0-or-later | 是 |
| libopus（随包 `libopus-0.dll`） | 1.6.1 | Opus 导出编码 | https://opus-codec.org/ | BSD-3-Clause | 是 |
| zlib（随包 FFmpeg 的共享库静态链入） | 1.3.2 | PNG（频谱图）压缩 | https://zlib.net/ | Zlib | 是 |
| libgcc / libwinpthread（随包 `libgcc_s_seh-1.dll`、`libwinpthread-1.dll`） | GCC 16.2.0 / mingw-w64 14.0.0 | mingw-w64 C 运行时与线程支持 | https://www.mingw-w64.org/ | GPL-3.0-or-later **带 GCC Runtime Library Exception 3.1** / MIT AND BSD-3-Clause | 是 |
| Microsoft Visual C++ Runtime / UCRT | 14.x / Windows 运行时 | CPython、Qt 与扩展模块运行支持 | https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist | Microsoft 可再发行组件条款 | 是 |

内置 FFmpeg 由**本仓库自建**（2026-09-24 起），参数为
`--enable-version3 --enable-shared --disable-static --disable-autodetect --disable-network`，
**未启用** `--enable-gpl`、`--enable-nonfree`、`--enable-chromaprint`。
发布包只携带应用实际调用的 `ffmpeg.exe`、`ffprobe.exe` 与所需共享 DLL，**不携带 `ffplay.exe`**。

### 内置 FFmpeg 构建启用的外部库

外部依赖**只有三个**：`libmp3lame`（MP3 编码）、`libopus`（Opus 编码）、`zlib`（PNG）。
FLAC 与 AAC(m4a) 使用 FFmpeg **自带**编码器；`ebur128`、`loudnorm`、`silencedetect`、
`showspectrumpic`、`anullsrc`、`aresample`、`aformat`、`atrim`、`asetpts`、`concat`
与 `-f lavfi`（libavdevice 的 lavfi indev）全部是**内置件**，未做裁剪。
另有 mingw 运行时随包（`libgcc_s_seh-1.dll`、`libwinpthread-1.dll`）与 CRT。
构建参数、理由与可复现步骤见 [`tools/ffmpeg-build/README.md`](tools/ffmpeg-build/README.md)。

这些组件的许可原文逐字收录在 [`licenses/ffmpeg/`](licenses/ffmpeg/)，共 **7 份**，逐条记录见
[`licenses/ffmpeg/MANIFEST.md`](licenses/ffmpeg/MANIFEST.md)；机器可校验清单为
`licenses/ffmpeg/manifest.json`，用 `python tools/verify_ffmpeg_licenses.py` 可逐文件复算内容哈希。
各组件的**实际版本**见 `licenses/ffmpeg/measured-versions.json`。

> **历史（2026-09-24 之前）**：当时的随包构建来自 BtbN FFmpeg-Builds 的 `win64-lgpl-shared`，
> 启用了 **57 个外部组件**，并且把 GPL-2.0-or-later 的 **FFTW 3.3.11** 经 chromaprint
> 静态链入了 `avformat-63.dll` —— 名义 LGPL、实为 GPL。换成自建最小构建后，
> 该问题连同 54 个本程序用不到的组件一并消除，随包二进制约 **145 MB → 31 MB**。
> 完整取证与根因见 [`FFMPEG_BUILD_INFO.md`](FFMPEG_BUILD_INFO.md) §2。

#### 必须处理的许可问题

1. ~~**`avformat-63.dll` 含 GPL 组件，不能标注为 LGPL。**~~ —— **已于 2026-09-24 解决。**
   原构建把 GPL-2.0-or-later 的 FFTW 3.3.11 经 chromaprint（`-DFFT_LIB=fftw3`）静态链入
   `avformat-63.dll`（二进制内实测到版本串、wisdom 格式串与 948 个 `fftw_codelet_*` 符号），
   根因是 BtbN 的 `25-fftw3.sh` / `50-chromaprint.sh` **缺少 lgpl 闸门**
   （对照 `50-x264.sh` 的 `[[ $VARIANT == lgpl* ]] && return -1`），
   违反其 README 明示的 *"`lgpl` Lacking libraries that are GPL-only"*。
   处置：改为自建最小构建，**不启用 chromaprint**，GPL 组件随之清零。
   现状由两道闸门守住 —— `python tools/audit_ffmpeg_license.py`（二进制审计）
   与 `tests/test_ffmpeg_license.py` 的换件绊线。
2. **弱著佐权项的可替换性**：`libmp3lame` 是 LGPL-2.0-or-later，且随包以**独立 DLL**
   （`libmp3lame-0.dll`）分发，FFmpeg 各库本身也是共享 DLL —— 用户可自行替换为修改版，
   满足 LGPL 对"可替换/可重链"的要求。`zlib`（Zlib 许可）为宽松许可，无此要求。
3. **GCC 运行时例外**：`libgcc_s_seh-1.dll` 适用 GPL-3.0-or-later **带 GCC Runtime Library
   Exception 3.1**，该例外明确允许在不触发 GPL 义务的前提下随非 GPL 程序分发。
   例外原文见 `licenses/ffmpeg/GCC-Runtime-Library-Exception-3.1.txt`。
4. **不再涉及的项**：本轮构建不含 FreeType（FTL 署名条款）、libaribb24（上游许可自相矛盾）、
   lcms2（`fastfloat` GPL 插件疑云）、Vulkan shim、aom/dav1d/vpx/webp/libjxl/SVT-AV1/rav1e
   的专利条款类文本等 —— 这些组件均未启用（`--disable-autodetect` + 只显式 enable 三个库）。

可复现核对命令：`.\app\resources\ffmpeg\bin\ffmpeg.exe -buildconf`、
`ffmpeg.exe -encoders`/`-filters`/`-muxers`（列出真正编译进来的外部集成）、
`python tools/audit_ffmpeg_license.py`（二进制许可审计，必须 PASS），
以及 `python tools/verify_ffmpeg_licenses.py`（许可文本完整性）。

## 开发、测试和打包工具

以下组件安装在开发环境中，但不会作为 Python 包随正式 EXE 分发：

| 组件 | 实际版本 | 用途 | 官方项目地址 | 许可证 |
| --- | --- | --- | --- | --- |
| openpyxl | 3.1.5 | 名称数据库的一次性 Excel 提取 | https://openpyxl.readthedocs.io/ | MIT |
| PyInstaller | 6.11.1 | Windows EXE 打包 | https://pyinstaller.org/ | GPL-2.0-or-later，带允许分发非自由程序的特殊例外 |
| maturin | 1.15.0 | vtcore（Rust 扩展）的本地构建 | https://github.com/PyO3/maturin | MIT OR Apache-2.0（取自包元数据 `License-Expression`） |
| ruff | 0.16.8 | 代码风格检查 | https://github.com/astral-sh/ruff | MIT（开发环境实测版本，未在 `requirements-dev.txt` 中固定） |
| mypy | 2.3.1 | 类型检查 | https://github.com/python/mypy | MIT（开发环境实测版本，未在 `requirements-dev.txt` 中固定） |

Python 标准库模块没有逐项列入本清单；随包分发的 CPython 解释器许可证已单独附带。

## 运行时下载的可选组件（不随发布包分发）

以下组件由 `start.bat` / `download_tts_verify.bat` 在用户机器上按需下载到 `TTS model\`（该目录已加入 `.gitignore`，
不随发布包分发）。本项目只提供下载脚本与校验清单，不复制、不修改、不再分发这些组件本身；使用时请遵守各自的许可证与模型条款。
版本与来源取自脚本中的固定值（2026-09-24 核对）：

| 组件 | 版本 | 用途 | 来源 | 许可证 |
| --- | --- | --- | --- | --- |
| CrispASR runner（`crispasr-0.8.34+vulkan-py3-none-win_amd64.whl`） | v0.8.34 | CosyVoice3 本地推理服务（`tools/cosyvoice3_shim.py` 调用其绑定） | https://github.com/CrispStrobe/CrispASR 官方 Release 资产 | MIT（`start.bat` 内已注明来源与许可） |
| GPT-SoVITS 代码（运行时浅克隆） | 跟随上游默认分支 | 语音微调与推理链路 | https://github.com/RVC-Boss/GPT-SoVITS | MIT（`Copyright (c) 2024 RVC-Boss`，取自本地克隆的 `LICENSE`） |
| CosyVoice3 权重（GGUF 等） | 跟随上游 | 文本转语音推理模型 | hf-mirror（上游为 `FunAudioLLM/Fun-CosyVoice3-0.5B-2512`） | Apache-2.0（上游模型卡 `cardData.license` 声明；模型权重可能另有使用条款，商用前请自行确认） |
| GPT-SoVITS 预训练权重（25 个文件） | 见 `gpt_sovits_weights_list.txt` | 微调起点 | hf-mirror | 随各权重上游声明；本清单与校验脚本只做存在性、大小与哈希校验，不代为声明许可 |

GPT-SoVITS 仓库自身包含若干第三方子组件（例如 `GPT_SoVITS/BigVGAN`、`tools/AP_BWE_main`，各自带独立 `LICENSE`），
其许可随克隆一并落在用户机器上，本项目不随包分发；完整依赖树以克隆到的上游仓库为准。

## Rust 依赖（vtcore 扩展）

`vtcore` 是本修改版新增的 Rust 扩展（源码在 `vtcore/`，自身按 **GPL-3.0-only** 授权，见 `MODIFICATION_NOTICE.md`），
提供语音批量的规范字节、`.vt` 容器、Ed25519 签名与整包校验。

**本修改版以源码形式分发**：接收者用 Cargo 按已入库的 `vtcore/Cargo.lock` 拉取下列依赖的**源码**，
每个 crate 的发行包内自带其许可证文本，因此随源码分发无需再单独附带文本。下表由
`tools/collect_rust_licenses.py` 从各 crate 的 `Cargo.toml` **机械汇总**（不依赖人工转录），
重新生成方式：`./.venv/Scripts/python.exe tools/collect_rust_licenses.py --out temp/rust_licenses.md`。

共 53 个第三方 crate：

| 组件 | 版本 | 许可证 |
| --- | --- | --- |
| aead | 0.6.1 | MIT OR Apache-2.0 |
| block-buffer | 0.12.1 | MIT OR Apache-2.0 |
| cfg-if | 1.0.5 | MIT OR Apache-2.0 |
| chacha20 | 0.10.2 | MIT OR Apache-2.0 |
| chacha20poly1305 | 0.11.0 | Apache-2.0 OR MIT |
| cipher | 0.5.2 | MIT OR Apache-2.0 |
| cmov | 0.5.4 | Apache-2.0 OR MIT |
| const-oid | 0.10.2 | Apache-2.0 OR MIT |
| cpufeatures | 0.3.1 | MIT OR Apache-2.0 |
| crypto-common | 0.2.2 | MIT OR Apache-2.0 |
| ctutils | 0.4.2 | Apache-2.0 OR MIT |
| curve25519-dalek | 5.0.0 | BSD-3-Clause |
| curve25519-dalek-derive | 0.1.1 | MIT/Apache-2.0 |
| digest | 0.11.3 | MIT OR Apache-2.0 |
| ed25519 | 3.0.0 | Apache-2.0 OR MIT |
| ed25519-dalek | 3.0.0 | BSD-3-Clause |
| fiat-crypto | 0.3.0 | MIT OR Apache-2.0 OR BSD-1-Clause |
| getrandom | 0.4.3 | MIT OR Apache-2.0 |
| heck | 0.5.0 | MIT OR Apache-2.0 |
| hybrid-array | 0.4.15 | MIT OR Apache-2.0 |
| inout | 0.2.2 | MIT OR Apache-2.0 |
| itoa | 1.0.18 | MIT OR Apache-2.0 |
| libc | 0.2.189 | MIT OR Apache-2.0 |
| memchr | 2.8.3 | Unlicense OR MIT |
| once_cell | 1.21.4 | MIT OR Apache-2.0 |
| poly1305 | 0.9.1 | Apache-2.0 OR MIT |
| portable-atomic | 1.15.0 | Apache-2.0 OR MIT |
| proc-macro2 | 1.0.107 | MIT OR Apache-2.0 |
| pyo3 | 0.29.2 | MIT OR Apache-2.0 |
| pyo3-build-config | 0.29.2 | MIT OR Apache-2.0 |
| pyo3-ffi | 0.29.2 | MIT OR Apache-2.0 |
| pyo3-macros | 0.29.2 | MIT OR Apache-2.0 |
| pyo3-macros-backend | 0.29.2 | MIT OR Apache-2.0 |
| quote | 1.0.47 | MIT OR Apache-2.0 |
| r-efi | 6.0.0 | MIT OR Apache-2.0 OR LGPL-2.1-or-later |
| rand_core | 0.10.1 | MIT OR Apache-2.0 |
| rustc_version | 0.4.1 | MIT OR Apache-2.0 |
| semver | 1.0.28 | MIT OR Apache-2.0 |
| serde | 1.0.229 | MIT OR Apache-2.0 |
| serde_core | 1.0.229 | MIT OR Apache-2.0 |
| serde_derive | 1.0.229 | MIT OR Apache-2.0 |
| serde_json | 1.0.151 | MIT OR Apache-2.0 |
| sha2 | 0.11.0 | MIT OR Apache-2.0 |
| signature | 3.0.0 | Apache-2.0 OR MIT |
| subtle | 2.6.1 | BSD-3-Clause |
| syn | 2.0.119 | MIT OR Apache-2.0 |
| syn | 3.0.6 | MIT OR Apache-2.0 |
| target-lexicon | 0.13.5 | Apache-2.0 WITH LLVM-exception |
| typenum | 1.20.1 | MIT OR Apache-2.0 |
| unicode-ident | 1.0.26 | (MIT OR Apache-2.0) AND Unicode-3.0 |
| universal-hash | 0.6.1 | MIT OR Apache-2.0 |
| zeroize | 1.9.0 | Apache-2.0 OR MIT |
| zmij | 1.0.23 | MIT |

需要注意的非 MIT/Apache 项（其余均为 `MIT OR Apache-2.0` 一类宽松许可）：

- `curve25519-dalek`、`ed25519-dalek`、`subtle` —— **BSD-3-Clause**（Ed25519 实现链）
- `target-lexicon` —— Apache-2.0 **WITH LLVM-exception**
- `unicode-ident` —— `(MIT OR Apache-2.0) AND Unicode-3.0`：Unicode 许可证要求保留其版权与许可声明，**不得移除**
- `memchr` —— `Unlicense OR MIT`
- `fiat-crypto`、`r-efi` —— 多项可选许可（分别含 BSD-1-Clause、LGPL-2.1-or-later），本项目按宽松项选用

依赖与版本以已入库的 `vtcore/Cargo.lock` 为准。**若将来改为分发 vtcore 的二进制产物**（而非源码），
必须同时附带所选许可证的完整文本，并重新执行一次本清单审计。

## 美术、字体和图标

- `app/resources/icons/wt_name_relay.png` 与由其生成的 ICO：由用户提供，并已明确允许随本项目发布包分发。
- 功能 SVG 图标为项目内自制资源，没有引入外部图标包。
- 应用使用系统字体回退，没有随包分发第三方字体。

## 随包许可证文件

发布目录中的 `licenses/` 包含：

- `Python-PSF-2.0.txt`
- `LGPL-3.0.txt`
- `GPL-3.0.txt`（PySide6/Qt 的 GPL 备选路径文本；本修改版新增代码同样按 GPL-3.0-only 授权，仅第 3 版，见 `MODIFICATION_NOTICE.md`）
- `FFmpeg-LGPL-3.0-or-later.txt`
- `PyQtGraph-MIT.txt`
- `NumPy-BSD-3-Clause.txt`
- `OpenSSL-Apache-2.0.txt`
- `openpyxl-MIT.txt`
- `PyInstaller-GPL-2.0-with-exception.txt`

`licenses/ffmpeg/`（子目录）另含随包 FFmpeg 构建所**静态链接**的第三方组件许可原文，共 **91 份**：
逐条清单见 `licenses/ffmpeg/MANIFEST.md`，机器可校验清单为 `licenses/ffmpeg/manifest.json`，
校验命令 `python tools/verify_ffmpeg_licenses.py`。其中包含 aom / dav1d / vpx / webp / libjxl /
SVT-AV1 / rav1e 的**专利许可**（`*-PATENTS.txt`，二进制分发须随附）、opencore-amr 的 Apache `NOTICE`、
以及 FFTW3 的 **GPL-2.0-or-later 正文**。

NumPy 的许可证文件应原样保留，因为其中包含其发行包捆绑组件的版权和许可证声明。Qt/PySide6 与 FFmpeg 使用动态共享库形式分发；用户可在不修改 WT-NameRelay 原创代码的情况下替换接口兼容的共享库。

## 已知许可注意事项

- 项目原创部分采用根目录 `LICENSE` 中的 WT-NameRelay Source-Available License 1.0；它不是 OSI 认可的开源许可证。
- “禁止二次售卖”只描述作者对原创部分与官方发布包的使用要求，不限制第三方许可证已经授予的权利。
- FFmpeg 构建链接了多项第三方库（42 个 `--enable-lib*`、15 个外部开关，以及若干传递依赖）。**不能只以二进制自身 `-L` 输出为依据**：该输出报 `LGPL-3.0-or-later`，但实测 `avformat-63.dll` 内含 GPL-2.0-or-later 的 FFTW 3.3.11（经 chromaprint 静态链入）——详见上文「内置 FFmpeg 构建启用的外部库」。逐库清单与许可原文见 `licenses/ffmpeg/`，版本与源码披露见 `FFMPEG_BUILD_INFO.md`；公开二进制 Release 前仍须附带或同服务器托管**各库固定版本**的对应源码，若更换 FFmpeg 构建必须重新执行许可证与构建参数审计。
- 本清单没有经过专业律师审核。
