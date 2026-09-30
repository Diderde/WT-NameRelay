# licenses/ffmpeg —— 随包 FFmpeg 第三方组件许可清单



范围 = 随包该 FFmpeg 构建（自建 MSYS2 + mingw-w64，commit fe953596e9）实际链接的第三方组件。本构建刻意最小化：--disable-autodetect 且只显式启用 3 个外部库（libmp3lame / libopus / zlib），另有 mingw 运行时（libgcc / winpthreads / CRT）动态或静态随附。**不含 chromaprint，因而也不含 GPL 的 FFTW。**



> **注意**：旧构建（BtbN win64-lgpl-shared）曾把 GPL-2.0-or-later 的 FFTW 3.3.11 经 chromaprint 静态链入 avformat-63.dll，导致该 DLL 实为 GPL。2026-09-24 已用自建最小 LGPL 构建替换，GPL 组件清零。请以 `python tools/audit_ffmpeg_license.py` 的结果为准，不要仅凭 ffmpeg -L 的自报。



> 哈希口径：sha256 按 LF 归一后的内容计算（content_digest），与工作区 CRLF 无关。



| 组件 | 版本 | 许可 (SPDX) | 原文文件 |

| --- | --- | --- | --- |

| libgcc (GCC runtime) | GCC 16.2.0 | `GPL-3.0-or-later` | [`GCC-GPL-3.0.txt`](GCC-GPL-3.0.txt) |

| libgcc (GCC runtime) | GCC 16.2.0 | `GCC-exception-3.1` | [`GCC-Runtime-Library-Exception-3.1.txt`](GCC-Runtime-Library-Exception-3.1.txt) |

| libmp3lame (LAME) | 3.100 | `LGPL-2.0-or-later` | [`LAME-LGPL-2.0-or-later.txt`](LAME-LGPL-2.0-or-later.txt) |

| libopus | 1.6.1 | `BSD-3-Clause` | [`Opus-BSD-3-Clause.txt`](Opus-BSD-3-Clause.txt) |

| mingw-w64 CRT runtime | mingw-w64 14.0.0 | `ZPL-2.1 OR public-domain` | [`mingw-w64-CRT-runtime.txt`](mingw-w64-CRT-runtime.txt) |

| winpthreads | mingw-w64 14.0.0 | `MIT AND BSD-3-Clause` | [`winpthreads-MIT.txt`](winpthreads-MIT.txt) |

| zlib | 1.3.2 | `Zlib` | [`zlib-Zlib.txt`](zlib-Zlib.txt) |



共 7 份许可原文。



本文件由 `tools/verify_ffmpeg_licenses.py --write-md` 可重新生成；

一致性核对：`python tools/verify_ffmpeg_licenses.py`。



