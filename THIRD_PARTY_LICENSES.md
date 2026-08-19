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
| Microsoft Visual C++ Runtime / UCRT | 14.x / Windows 运行时 | CPython、Qt 与扩展模块运行支持 | https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist | Microsoft 可再发行组件条款 | 是 |

内置 FFmpeg 的实际构建启用了 `--enable-version3 --enable-shared --disable-static`，未启用 GPL-only 的 x264、x265、xvid、vidstab、rubberband 等组件。发布包只携带应用实际调用的 `ffmpeg.exe`、`ffprobe.exe` 和所需共享 DLL，不携带 `ffplay.exe`。

PyQtGraph 包含一组可选的 CET/Matplotlib 色图数据；WT-NameRelay 不使用这些色图，打包钩子会排除 `pyqtgraph/colors/maps`，因此发布包不分发相应 CC BY/CC0 数据。

## 开发、测试和打包工具

以下组件安装在开发环境中，但不会作为 Python 包随正式 EXE 分发：

| 组件 | 实际版本 | 用途 | 官方项目地址 | 许可证 |
| --- | --- | --- | --- | --- |
| openpyxl | 3.1.5 | 名称数据库的一次性 Excel 提取 | https://openpyxl.readthedocs.io/ | MIT |
| Pillow | 10.4.0 | PNG/ICO 图标转换 | https://python-pillow.org/ | HPND |
| PyInstaller | 6.11.1 | Windows EXE 打包 | https://pyinstaller.org/ | GPL-2.0-or-later，带允许分发非自由程序的特殊例外 |

Python 标准库模块没有逐项列入本清单；随包分发的 CPython 解释器许可证已单独附带。

## 美术、字体和图标

- `app/resources/icons/wt_name_relay.png` 与由其生成的 ICO：由用户提供，并已明确允许随本项目发布包分发。
- 功能 SVG 图标为项目内自制资源，没有引入外部图标包。
- 应用使用系统字体回退，没有随包分发第三方字体。

## 随包许可证文件

发布目录中的 `licenses/` 包含：

- `Python-PSF-2.0.txt`
- `LGPL-3.0.txt`
- `GPL-3.0.txt`
- `FFmpeg-LGPL-3.0-or-later.txt`
- `PyQtGraph-MIT.txt`
- `NumPy-BSD-3-Clause.txt`
- `OpenSSL-Apache-2.0.txt`
- `openpyxl-MIT.txt`
- `PyInstaller-GPL-2.0-with-exception.txt`
- `Pillow-HPND.txt`

NumPy 的许可证文件应原样保留，因为其中包含其发行包捆绑组件的版权和许可证声明。Qt/PySide6 与 FFmpeg 使用动态共享库形式分发；用户可在不修改 WT-NameRelay 原创代码的情况下替换接口兼容的共享库。

## 已知许可注意事项

- 项目原创部分采用根目录 `LICENSE` 中的 WT-NameRelay Source-Available License 1.0；它不是 OSI 认可的开源许可证。
- “禁止二次售卖”只描述作者对原创部分与官方发布包的使用要求，不限制第三方许可证已经授予的权利。
- FFmpeg 构建链接了多项第三方库；本清单以打包二进制自身 `-L` 输出、随附 LGPL 文本和 BtbN 构建配置为依据。版本与源码披露见 `FFMPEG_BUILD_INFO.md`。公开二进制 Release 前仍须附带或同服务器托管对应源码包；若更换 FFmpeg 构建，必须重新执行许可证与构建参数审计。
- 本清单没有经过专业律师审核。
