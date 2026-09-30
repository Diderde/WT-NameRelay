# tools/ffmpeg-build —— 随包 FFmpeg 的可复现构建

本目录的脚本产出 `app/resources/ffmpeg/bin/` 里那套 FFmpeg 二进制。
**这是许可合规的一部分**：随包的 FFmpeg 必须是真正的 LGPL 构建，
构建方式必须可复现，才能履行 LGPL 的"对应源码"义务。

> 本目录的 4 个脚本就是**实际产出当前随包二进制的那 4 步**（不是事后补写的理想版）。
> 其中的坑与顺序要求都来自本次构建的真实翻车。

## 为什么要自建（而不是继续用现成分发包）

原随包二进制来自 BtbN FFmpeg-Builds 的 `win64-lgpl-shared`。
该变体**名义上是 LGPL，实际不是**：它把 GPL-2.0-or-later 的 **FFTW 3.3.11**
经 chromaprint（`-DFFT_LIB=fftw3`）**静态链进了 `avformat-63.dll`**，
于是那个 DLL 必须按 GPL-3.0 对待，而 README 与声明里标的是 LGPL。

根因是上游构建脚本缺闸门：

| 脚本 | lgpl 闸门 | 后果 |
| --- | --- | --- |
| `scripts.d/50-x264.sh`（对照） | 有 `[[ $VARIANT == lgpl* ]] && return -1` | GPL 库被正确排除 |
| `scripts.d/25-fftw3.sh` | **无**（裸 `return 0`） | 任何变体都编 FFTW，且静态库 |
| `scripts.d/50-chromaprint.sh` | **无**（只有 FFmpeg 版本判断） | 任何变体都编，且 `-DFFT_LIB=fftw3` |

而 BtbN README 明示 *"`lgpl` Lacking libraries that are GPL-only"* ——
属**上游违反自身声明的缺陷**（已在本仓库文档中记录）。

FFmpeg 自报的 `license: LGPL-3.0-or-later` **不能作为依据**：它只看自己的
configure 开关，看不见经第三方库间接引入的 GPL 代码。

## 前置条件

- Windows + MSYS2（无需管理员权限；本次构建就是解压
  `msys2-base-x86_64-*.tar.xz` 到非系统目录完成的 —— GUI 安装器在未开
  Developer Mode 的机器上会因建不了符号链接而空转）
- 网络可达（脚本默认用清华 MSYS2 镜像与 codeload.github.com）

## 步骤（顺序不可变）

在 **MSYS2 MINGW64** shell 里依次执行（`WORK` 指向一个足够大的临时目录，约需 15–25 GB）：

```bash
export MSYSTEM=MINGW64
export WORK=/d/build/ffmpeg-build        # 按需改；不要放在仓库里
export REPO=/d/path/to/WT-NameRelay      # 04 用来定位仓库根；缺省取脚本上两级

bash tools/ffmpeg-build/01-toolchain.sh
bash tools/ffmpeg-build/02-build.sh            # 取源码 + configure + make
bash tools/ffmpeg-build/03-normalize-prefix.sh # 归一中缀（02 之后必跑）
bash tools/ffmpeg-build/04-finalize.sh         # 定版本 + 剥符号 + 收件 + 审计
```

耗时参考（18 核、MSYS2、无杀软拦截下实测）：工具链约 3 分钟；configure 约 35 分钟
（上千次编译探测，MSYS2 的 fork/exec 开销是主因）；`make -j18` 约 40 分钟；
归一中缀约 8 分钟；收尾约 2 分钟。**总计约 1.5 小时。**

> 本目录的 `.sh` 按仓库 `.gitattributes`（`* text=auto eol=crlf`）存为 CRLF。
> MSYS2 的 bash 以**文本模式**读脚本，CRLF 可正常执行（已实测：LF 与 CRLF 两版
> 都能跑通 `set -euo pipefail`、变量展开与循环）；但换到二进制模式的
> Git-Bash / WSL 时须先转成 LF 再跑。

### 两个必须知道的顺序约束

1. **`03` 必须在 `02` 之后**：`02` 用 `$WORK/out` 作 `--prefix`，该路径会被编进
   `FFMPEG_CONFIGURATION` / `FFMPEG_DATADIR` 常量。`03` 把它改写成中性路径
   `/ffbuild/ffmpeg-lgpl` 并只重编受影响的翻译单元。
2. **定版本串必须在 `03` 之后**（也就是放在 `04`）：`03` 的 `make` 会按 `version.sh`
   **重新生成** `libavutil/ffversion.h`，把先前写入的版本串覆盖回 `"8.0.git"`。

### 三个容易误判的地方

- **判断组件开关要看 `ffbuild/config.mak`，不是 `config.h`**：前者出现
  `CONFIG_X=yes` 即启用、缺席即关闭，是完整权威源；后者只含一个子集。
  本次构建曾因为查 `config.h` 而在 `CONFIG_LAVFI_INDEV` 上得到"未定义"，
  据此误判 lavfi indev 被关掉了（实际上它是开着的）。
- **`--disable-autodetect` 之后只剩显式 enable 的三个外部库**：不要据此以为
  内部 codec / filter / device 被裁了 —— 我们没有做任何内部裁剪。
- **不做 `make install`，产物直接从源码树取**：共享构建把各 DLL 放在
  `libavcodec/`、`libavutil/` 等子目录里，源码树根部的 `ffmpeg.exe` 直接跑会因
  找不到同级 DLL 而以 127 退出（本次构建踩过）。所以 `04` 是按产物清单逐个 `cp`
  进 `app/resources/ffmpeg/bin/` 的 —— 那个 `bin/` 是**收件之后才存在**的目录。

## 构建参数与其理由

```
--enable-version3           LGPL-3.0-or-later（而非 2.1）
--enable-shared --disable-static
--disable-autodetect        只认显式 enable 的库，杜绝误引入
--disable-network           本程序只处理本地文件，不需要网络协议栈
--disable-doc --disable-debug --disable-ffplay
--enable-libmp3lame --enable-libopus --enable-zlib
                            ↑ 全部外部依赖只有这三个
```

**没有 `--enable-chromaprint`** —— 这就是 GPL 的 FFTW 不再出现的原因。
**没有 `--enable-gpl`**、**没有 `--enable-nonfree`**。

保留 FFmpeg 全部**内置**组件（不裁剪），因为应用用到
`-f lavfi`（libavdevice 的 lavfi indev）、`ebur128`、`showspectrumpic`、
`loudnorm`、`silencedetect`、`anullsrc`、`aresample`、`aformat` 等，全是内置件。

源码锁定 commit `fe953596e9f53e3d61c465bce7a29834cae3375b`，与原随包二进制同一个
commit —— 于是 DLL 主版本号不变（`avcodec-63` 等），不会牵动 spec、打包与文档。

### 收尾为什么要补 4 个 DLL

本构建用共享版依赖，`ffmpeg.exe` 与各 DLL 还依赖：

| DLL | 来源 | 许可 |
| --- | --- | --- |
| `libgcc_s_seh-1.dll` | GCC 运行时 | GPL-3.0 **带 GCC Runtime Library Exception 3.1**（可自由随非 GPL 程序分发） |
| `libwinpthread-1.dll` | mingw 线程 | MIT AND BSD-3-Clause |
| `libmp3lame-0.dll` | LAME | LGPL-2.0-or-later |
| `libopus-0.dll` | Opus | BSD-3-Clause |

原 BtbN 构建把这些静态链进了自己的 DLL，所以只有 10 个文件；本构建是 13 个。
`build_release.py` 会复制 `bin/` 下所有 `*.dll`，故一并随包分发。

## 事实核验（AGENTS.md §4.7）

构建完成后，用仓库里这两个脚本**自证**，不要只凭本文的说法：

```bash
python tools/audit_ffmpeg_license.py          # 二进制许可审计：必须 PASS
python tools/verify_ffmpeg_licenses.py        # 许可文本集合与清单逐文件哈希一致
```

它们检查的是：内嵌 configure 行无 GPL/nonfree 开关；**屏蔽 configure 行后**逐二进制
扫描 GPL-only 组件的代码级特征（FFTW / x264 / x265 / Xvid / libpostproc / fdk-aac /
vidstab / rubberband / frei0r / AviSynth / libsmbclient / libcdio）；再与界面声明的
许可标签对拍。`tests/test_ffmpeg_license.py` 是换件绊线 —— 组件集合一变就失败。

本目录的四个脚本另有不依赖真机构建的语法自检（几秒出结果）：

```bash
for f in tools/ffmpeg-build/0*.sh; do bash -n "$f" && echo "OK  $f"; done
```

`01`–`04` 均已通过 `bash -n`。

换件后还要同步更新：

- `licenses/ffmpeg/`（组件集合变了就重建清单与 `MANIFEST.md`）
- `FFMPEG_BUILD_INFO.md`、`THIRD_PARTY_LICENSES.md`
- `app/i18n.py`（`_ABOUT_ORIGINAL` 块）与 `app/widgets/license_dialog.py` 里的版本串
- `tests/test_ffmpeg_license.py` 的 `KNOWN_GPL_FINDINGS` 与 `tests/test_release_features.py` 的版本串断言
- 改了含中文的代码文件后跑 `python -m compileall -q main.py app tests tools`
