#!/usr/bin/env bash
# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
#
# 02 - 取 FFmpeg 源码并编译「真 LGPL」构建。
#
# 关键点
#   * 锁定 commit fe953596e9f53e3d61c465bce7a29834cae3375b：
#     与原随包二进制同一个 commit，因此 DLL 主版本号不变
#     （avcodec-63 / avdevice-63 / avfilter-12 / avformat-63 / avutil-61 /
#      swresample-7 / swscale-10），不会牵动 spec、打包与文档里的名字。
#   * **不启用 chromaprint** —— 这是移除 GPL 的 FFTW 的关键。
#     （BtbN 的 lgpl-shared 变体因构建脚本缺 lgpl 闸门而把它静态链了进去。）
#   * --disable-autodetect + 只显式 enable 3 个外部库，杜绝误引入。
#
# 注意：本步用 $FPREFIX 作为 --prefix，该路径会被编进
# `FFMPEG_CONFIGURATION` / `FFMPEG_DATADIR` 常量。因此**下一步 03 必须紧接着跑**
# 把前缀归一为中性路径，否则产物会带开发机目录布局。
#
# 本步**不做 make install**：产物直接从源码树取（见 04；共享构建的 DLL 落在各
# 子库目录里，`make install` 并非必需，实测也没能装上）。
#
# 用法（在 MSYS2 MINGW64 shell 里）：
#   MSYSTEM=MINGW64 WORK=/d/path/to/work bash tools/ffmpeg-build/02-build.sh
#
# 环境变量：
#   WORK  构建工作目录（默认：当前目录下的 ffmpeg-build）
#   JOBS  并行度（默认：nproc）

set -euo pipefail

WORK="${WORK:-$PWD/ffmpeg-build}"
SRC="$WORK/src"
# 仅作 --prefix 字符串用，不是安装目录；03 会把它改写成中性路径
FPREFIX="$WORK/out"
JOBS="${JOBS:-$(nproc)}"
COMMIT="fe953596e9f53e3d61c465bce7a29834cae3375b"

mkdir -p "$SRC"

echo "=== 1. 取源码（$COMMIT）==="
TAR="$WORK/ffmpeg-$COMMIT.tar.gz"
if [ ! -s "$TAR" ]; then
  echo "  下载 codeload tarball …"
  curl -L --fail --retry 4 --ssl-no-revoke \
    -o "$TAR" "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/$COMMIT"
fi
ls -la "$TAR"

SRCDIR="$SRC/FFmpeg-$COMMIT"
if [ ! -d "$SRCDIR" ]; then
  echo "  解压 …"
  tar -xzf "$TAR" -C "$SRC"
fi
# 记录给后续脚本用（03 / 04 会读）
printf '%s\n%s\n' "$SRCDIR" "$COMMIT" > "$WORK/source-info.txt"

cd "$SRCDIR"

echo
echo "=== 2. 清理上次构建痕迹 ==="
if [ -f ffbuild/config.mak ]; then
  make distclean >/dev/null 2>&1 || true
fi

echo
echo "=== 3. configure（LGPL v3，无 chromaprint）==="
./configure \
  --prefix="$FPREFIX" \
  --arch=x86_64 \
  --target-os=mingw32 \
  --enable-version3 \
  --enable-shared \
  --disable-static \
  --disable-autodetect \
  --disable-network \
  --disable-doc \
  --disable-debug \
  --disable-ffplay \
  --enable-libmp3lame \
  --enable-libopus \
  --enable-zlib \
  2>&1 | tee "$WORK/configure.log"

echo
echo "=== 4. configure 结果核查 ==="
# 权威位置是 ffbuild/config.mak：出现 `CONFIG_X=yes` 即启用，缺席即关闭。
# （config.h 只含其中一个子集，用它判断会误报 —— 本次构建踩过这个坑：
#   在那儿查 CONFIG_LAVFI_INDEV 得到"未定义"，据此误判 lavfi indev 被关掉了。）
MAK=ffbuild/config.mak
if [ ! -f "$MAK" ]; then
  echo "  *** 找不到 $MAK，configure 可能失败 ***"
  exit 1
fi

echo "--- 必须【缺席】的开关（出现即为致命）---"
FATAL=0
for k in CONFIG_GPL CONFIG_NONFREE CONFIG_CHROMAPRINT CONFIG_LIBX264 CONFIG_LIBX265 \
         CONFIG_LIBXVID CONFIG_LIBXAVS2 CONFIG_LIBFDK_AAC; do
  if grep -qE "^${k}=yes" "$MAK"; then
    echo "  *** 已启用: $k ***"
    FATAL=$((FATAL+1))
  else
    echo "  OK  未启用: $k"
  fi
done

echo "--- 必须【出现】的开关 ---"
for k in CONFIG_VERSION3 CONFIG_LIBMP3LAME CONFIG_LIBOPUS CONFIG_ZLIB CONFIG_LAVFI_INDEV; do
  if grep -qE "^${k}=yes" "$MAK"; then
    echo "  OK  已启用: $k"
  else
    echo "  *** 未启用: $k ***"
    FATAL=$((FATAL+1))
  fi
done
[ "$FATAL" -eq 0 ] || { echo; echo "RESULT: FAIL（开关核查不通过）"; exit 1; }

echo
echo "=== 5. make -j$JOBS（这一步最慢，MSYS2 上约 40 分钟）==="
make -j"$JOBS" 2>&1 | tail -20

echo
echo "=== 6. 产物（留在源码树内，不 install）==="
for f in libavcodec/avcodec-63.dll libavformat/avformat-63.dll libavutil/avutil-61.dll \
         libavfilter/avfilter-12.dll libavdevice/avdevice-63.dll \
         libswresample/swresample-7.dll libswscale/swscale-10.dll \
         ffmpeg.exe ffprobe.exe; do
  if [ -f "$f" ]; then printf '  %-34s %10d B\n' "$f" "$(stat -c %s "$f")"; else echo "  *** 缺 $f ***"; fi
done

echo
echo "  内嵌前缀（03 会把它归一化成中性路径）："
CFG="$(grep -oE '^#define FFMPEG_CONFIGURATION "--prefix=[^ ]+' config.h | head -1 | sed 's/.*--prefix=//' || true)"
echo "    ${CFG:-（未解析到）}"

echo
echo "RESULT: PASS（下一步必须跑 03-normalize-prefix.sh）"
