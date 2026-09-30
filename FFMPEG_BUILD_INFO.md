# FFmpeg binary provenance and source information

本文件记录随包 FFmpeg 的来源、**许可实测结论**、重新构建方法与验收闸门。
技术事实记录，不构成法律意见。

## 1. 随包构建（现状）

```text
ffmpeg version N-125829-gfe953596e9
built with gcc 16.2.0 (Rev4, Built by MSYS2 project)
```

**本构建由本仓库自建**，不是现成分发包。源码锁定上游
commit `fe953596e9f53e3d61c465bce7a29834cae3375b`（2026-07-28），
与原随包二进制同一个 commit —— 因此 DLL 主版本号不变
（`avcodec-63` / `avdevice-63` / `avfilter-12` / `avformat-63` / `avutil-61` /
`swresample-7` / `swscale-10`）。

内嵌 configure 行（可用 `ffmpeg -version` 复核）：

```text
--arch=x86_64 --target-os=mingw32 --enable-version3 --enable-shared --disable-static
--disable-autodetect --disable-network --disable-doc --disable-debug --disable-ffplay
--enable-libmp3lame --enable-libopus --enable-zlib
```

**外部依赖只有三个**：`libmp3lame`（MP3 编码）、`libopus`（Opus 编码）、`zlib`（PNG）。
FLAC 与 AAC(m4a) 用 FFmpeg 自带编码器；`ebur128` / `loudnorm` / `silencedetect` /
`showspectrumpic` / `anullsrc` / `aresample` / `aformat` 与 `-f lavfi`（libavdevice
的 lavfi indev）全部是内置件。另有 mingw 运行时
（`libgcc_s_seh-1.dll`、`libwinpthread-1.dll`）与 LAME / Opus 的运行库随包。

**没有 `--enable-gpl`，没有 `--enable-nonfree`，没有 `--enable-chromaprint`。**

### 许可结论

**LGPL-3.0-or-later —— 且这是经二进制实测确认的，不是自报。**

```powershell
.venv\Scripts\python.exe tools\audit_ffmpeg_license.py    # 必须 PASS
```

该工具做三件事：核对内嵌 configure 行无 GPL/nonfree 开关；**屏蔽 configure 行后**
逐二进制扫描 GPL-only 组件的代码级特征串（FFTW / x264 / x265 / Xvid / libpostproc /
fdk-aac / vidstab / rubberband / frei0r / AviSynth / libsmbclient / libcdio）；
再与界面声明的许可标签对拍。当前结果：**全部通过，零 GPL 命中**。

## 2. 历史：为什么换掉原来的 BtbN 构建

原随包二进制来自 BtbN FFmpeg-Builds 的 `win64-lgpl-shared` 分发包。
它**名义 LGPL、实际不是**：把 GPL-2.0-or-later 的 **FFTW 3.3.11** 经 chromaprint
（`-DFFT_LIB=fftw3`）**静态链进了 `avformat-63.dll`**，因此那一个 DLL 必须按
GPL-3.0 对待，而界面与文档当时标的是 LGPL。

当时的二进制级证据（可复现）：

- `avformat-63.dll` 的 PE 导入表只有 25 个系统 DLL + `avcodec-63.dll` + `avutil-61.dll`，
  **没有任何 fftw DLL** → 静态链入；
- 该 DLL 内含 FFTW 自身源码痕迹：版本串 `fftw-3.3.11`、wisdom 序列化格式串
  `(fftw-3.3.11 fftw_wisdom #x%M …)`、`%s:%d: assertion failed: %s`（FFTW 的 CHECK 宏），
  以及 **948 个 `fftw_codelet_*` 规划器符号**；
- 其余 9 个二进制 0 命中 —— 与「chromaprint muxer 位于 libavformat」吻合。

根因是 BtbN 构建脚本缺 lgpl 闸门（`50-x264.sh` 有 `[[ $VARIANT == lgpl* ]] && return -1`，
而 `25-fftw3.sh` 是裸 `return 0`、`50-chromaprint.sh` 只有版本判断），
违反其 README 明示的 *"`lgpl` Lacking libraries that are GPL-only"*。

`ffmpeg -L` 当时自报 LGPL —— **它只看 FFmpeg 自己的 configure 开关，看不见经第三方库
间接引入的 GPL 代码**。这正是"必须查二进制、不能只信自报"的原因，
也是 `tools/audit_ffmpeg_license.py` 存在的理由。

## 3. 重新构建

完整步骤与环境要求见 [`tools/ffmpeg-build/README.md`](tools/ffmpeg-build/README.md)。
四个脚本：`01-toolchain.sh`（MSYS2 工具链 + 3 个外部库）、`02-build.sh`（取源码 +
configure + make）、`03-version-relink.sh`（把版本串写实为
`N-125829-gfe953596e9`）、`04-collect.sh`（换进仓库并跑审计）。

参考耗时约 1.5 小时（configure 约 35 分钟、`make -j18` 约 40 分钟）——
MSYS2 在 Windows 上的 fork/exec 开销是主因。

**换件后必须同步**：`licenses/ffmpeg/`（组件集合变了就重建清单）、
本文件、`THIRD_PARTY_LICENSES.md`、界面版本串
（`app/i18n.py` 与 `app/widgets/license_dialog.py`）、
以及 `tests/test_ffmpeg_license.py` 的 `KNOWN_GPL_FINDINGS`。

## 4. 源码与链接

- FFmpeg 上游源码：<https://github.com/FFmpeg/FFmpeg>
- 本构建锁定的修订：<https://github.com/FFmpeg/FFmpeg/commit/fe953596e9f53e3d61c465bce7a29834cae3375b>
- 对应源码归档（codeload）：<https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/fe953596e9f53e3d61c465bce7a29834cae3375b>
- FFmpeg 法律与源码分发清单：<https://ffmpeg.org/legal.html>
- MSYS2：<https://www.msys2.org/>

内嵌 configure 行与许可自报可在不启动主程序的情况下查看：

```powershell
.\app\resources\ffmpeg\bin\ffmpeg.exe -version
.\app\resources\ffmpeg\bin\ffmpeg.exe -L
```

发布二进制 GitHub Release 前，维护者必须随应用下载**附带或同服务器托管**对应版本的
FFmpeg 源码包与构建信息，并在 Release 说明里链接该源码。仅链接上游滚动默认分支
不构成"对应源码"的证据。

## 5. 验收闸门

**发布路径**：`build_release.py` 的 `verify_ffmpeg_license()` 在打包前调用二进制审计。
它原先只跑 `ffmpeg -L` 并匹配 "GNU Lesser General Public License … version 3" ——
那正是**看不见**间接引入的 GPL 的弱检查。现在两道都跑，审计不通过即 `RuntimeError`，
**打包被拒**。

**门禁**：`tests/test_ffmpeg_license.py` 已登记进 `tools/run_gate.ps1`。其中：

- `test_configure_switches_are_lgpl_only` —— 开关层面必须无 GPL/nonfree；
- `test_gpl_findings_match_documented_state` —— **换件绊线**：GPL 组件集合一旦变化即失败，
  逼迫换件者同步更新 `KNOWN_GPL_FINDINGS`、本文件、`THIRD_PARTY_LICENSES.md`
  与 `licenses/ffmpeg/`。当前该集合为**空**（GPL 组件已清零）；
- `test_detector_actually_detects` / `test_configure_line_is_masked_before_scanning` ——
  检测器自检，防止"工具坏了却全绿"，也防止 configure 行里的 `--disable-libx264`
  之类开关名造成假阳性。
