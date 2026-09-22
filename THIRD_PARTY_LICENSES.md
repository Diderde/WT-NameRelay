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
| FFmpeg / ffprobe（BtbN shared build） | N-125829-gfe953596e9-20260728 | 音频探测、波形解析、试听缓存和正式导出 | https://github.com/BtbN/FFmpeg-Builds | `ffmpeg -L` 实际报告 LGPL-3.0-or-later | 是 |
| libmp3lame（内置于随包 FFmpeg） | 随 FFmpeg 构建 | MP3 导出编码 | https://lame.sourceforge.io/ | LGPL-2.0-or-later | 是（经 FFmpeg 动态调用） |
| libopus（内置于随包 FFmpeg） | 随 FFmpeg 构建 | Opus 导出编码 | https://opus-codec.org/ | BSD-3-Clause | 是（经 FFmpeg 动态调用） |
| libvorbis（内置于随包 FFmpeg） | 随 FFmpeg 构建 | Vorbis 编码（Ogg 容器备用） | https://xiph.org/vorbis/ | BSD-3-Clause | 是（经 FFmpeg 动态调用） |
| Microsoft Visual C++ Runtime / UCRT | 14.x / Windows 运行时 | CPython、Qt 与扩展模块运行支持 | https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist | Microsoft 可再发行组件条款 | 是 |

内置 FFmpeg 的实际构建启用了 `--enable-version3 --enable-shared --disable-static`，未启用 GPL-only 的 x264、x265、xvid、vidstab、rubberband 等组件。发布包只携带应用实际调用的 `ffmpeg.exe`、`ffprobe.exe` 和所需共享 DLL，不携带 `ffplay.exe`。

PyQtGraph 包含一组可选的 CET/Matplotlib 色图数据；WT-NameRelay 不使用这些色图，打包钩子会排除 `pyqtgraph/colors/maps`，因此发布包不分发相应 CC BY/CC0 数据。

## 开发、测试和打包工具

以下组件安装在开发环境中，但不会作为 Python 包随正式 EXE 分发：

| 组件 | 实际版本 | 用途 | 官方项目地址 | 许可证 |
| --- | --- | --- | --- | --- |
| openpyxl | 3.1.5 | 名称数据库的一次性 Excel 提取 | https://openpyxl.readthedocs.io/ | MIT |
| PyInstaller | 6.11.1 | Windows EXE 打包 | https://pyinstaller.org/ | GPL-2.0-or-later，带允许分发非自由程序的特殊例外 |

Python 标准库模块没有逐项列入本清单；随包分发的 CPython 解释器许可证已单独附带。

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
- `GPL-3.0.txt`（本修改版新增代码适用，仅第 3 版，见 `MODIFICATION_NOTICE.md`）
- `GPL-3.0.txt`
- `FFmpeg-LGPL-3.0-or-later.txt`
- `PyQtGraph-MIT.txt`
- `NumPy-BSD-3-Clause.txt`
- `OpenSSL-Apache-2.0.txt`
- `openpyxl-MIT.txt`
- `PyInstaller-GPL-2.0-with-exception.txt`

NumPy 的许可证文件应原样保留，因为其中包含其发行包捆绑组件的版权和许可证声明。Qt/PySide6 与 FFmpeg 使用动态共享库形式分发；用户可在不修改 WT-NameRelay 原创代码的情况下替换接口兼容的共享库。

## 已知许可注意事项

- 项目原创部分采用根目录 `LICENSE` 中的 WT-NameRelay Source-Available License 1.0；它不是 OSI 认可的开源许可证。
- “禁止二次售卖”只描述作者对原创部分与官方发布包的使用要求，不限制第三方许可证已经授予的权利。
- FFmpeg 构建链接了多项第三方库；本清单以打包二进制自身 `-L` 输出、随附 LGPL 文本和 BtbN 构建配置为依据。版本与源码披露见 `FFMPEG_BUILD_INFO.md`。公开二进制 Release 前仍须附带或同服务器托管对应源码包；若更换 FFmpeg 构建，必须重新执行许可证与构建参数审计。
- 本清单没有经过专业律师审核。
