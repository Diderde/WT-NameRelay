#!/usr/bin/env bash
# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
#
# 03 - 归一构建前缀，消除内嵌的构建机路径。**必须在 02 之后、04 之前跑。**
#
# 问题：configure 的 --prefix 会被编进每个库的 FFMPEG_CONFIGURATION 常量
# （avutil_configuration() 等返回它），以及 fftools 的 FFMPEG_DATADIR。
# 若用本地路径（如 $WORK/out）构建，该路径就随二进制一起分发，泄露构建机的
# 目录布局。实测：本步之前 9 个二进制**全部**带着 `--prefix=<本机目录>`。
#
# 做法：把 config.h / ffbuild/config.mak 里的前缀改成中性路径（这正是 configure
# 用该 prefix 运行时本就会写出的内容），只重编嵌入该常量的翻译单元再重链 ——
# 避免因改动 config.h 触发全量重编。
#
# 顺带一个坑：本步的 `make` 会按 version.sh **重新生成 libavutil/ffversion.h**，
# 把先前写入的版本串覆盖回 "8.0.git"。所以定版本串必须放在本步**之后**（见 04）。
#
# 用法（在 MSYS2 MINGW64 shell 里）：
#   MSYSTEM=MINGW64 WORK=/d/path/to/work bash tools/ffmpeg-build/03-normalize-prefix.sh
#
# 环境变量：
#   WORK            构建工作目录（默认：当前目录下的 ffmpeg-build）
#   FFMPEG_PREFIX   目标中性前缀（默认 /ffbuild/ffmpeg-lgpl）
#   JOBS            并行度（默认：nproc）

set -euo pipefail

WORK="${WORK:-$PWD/ffmpeg-build}"
FPREFIX="${FFMPEG_PREFIX:-/ffbuild/ffmpeg-lgpl}"
JOBS="${JOBS:-$(nproc)}"
SRC="$(head -1 "$WORK/source-info.txt")"

# 与 04 共用同一份产物清单（共享构建的产物落在各子库目录里，不在 bin/）
BINARIES="libavcodec/avcodec-63.dll libavformat/avformat-63.dll libavutil/avutil-61.dll
libavfilter/avfilter-12.dll libavdevice/avdevice-63.dll
libswresample/swresample-7.dll libswscale/swscale-10.dll
ffmpeg.exe ffprobe.exe"

cd "$SRC"

echo "=== 1. 找出 config.h 里当前的前缀 ==="
CUR="$(grep -oE '^#define FFMPEG_CONFIGURATION "--prefix=[^ ]+' config.h | head -1 | sed 's/.*--prefix=//' || true)"
echo "  当前 prefix = ${CUR:-（未解析到）}"
if [ -z "$CUR" ]; then echo "*** 未能解析当前 prefix ***"; exit 1; fi
if [ "$CUR" = "$FPREFIX" ]; then echo "  已是目标值"; fi

echo
echo "=== 2. 改写 config.h 中的前缀 ==="
# 备份留下（04 靠它推导出旧前缀做残留复核，从而不必写死任何本机路径）
cp -n config.h config.h.bak-prefix 2>/dev/null || true
sed -i "s|$CUR|$FPREFIX|g" config.h
grep -oE '^#define FFMPEG_(CONFIGURATION|DATADIR) "[^"]*"' config.h | head -2

echo
echo "=== 3. 改写 ffbuild/config.mak 的 prefix ==="
if [ -f ffbuild/config.mak ]; then
  cp -n ffbuild/config.mak ffbuild/config.mak.bak-prefix 2>/dev/null || true
  sed -i "s|^prefix=.*|prefix=$FPREFIX|" ffbuild/config.mak
  grep -E '^prefix=' ffbuild/config.mak
fi

echo
echo "=== 4. 只重编嵌入该常量的翻译单元 ==="
# 每个库的 version.c 都返回 FFMPEG_CONFIGURATION；fftools 用到 FFMPEG_DATADIR
touch libavutil/version.c libavcodec/version.c libavformat/version.c \
      libavfilter/version.c libavdevice/version.c libswresample/version.c \
      libswscale/version.c 2>/dev/null || true
touch fftools/*.c 2>/dev/null || true
echo "  已 touch"

echo
echo "=== 5. make ==="
# 注：-o 只能挡住 config.h 引起的重编，ffbuild/config.mak 仍是 make 的输入，
# 实测仍会重编一部分 libavfilter —— 属可接受代价，不影响正确性。
make -o config.h -o ffbuild/config.mak -j"$JOBS" 2>&1 | tail -18

echo
echo "=== 6. 复核：旧前缀是否还有残留 ==="
# 探针取自第 1 步解析出的真实旧前缀，不写死任何本机路径
LEFT=0
for f in $BINARIES; do
  if [ ! -f "$f" ]; then echo "  *** 缺 $f ***"; LEFT=$((LEFT+1)); continue; fi
  if grep -q -- "$CUR" "$f" 2>/dev/null; then
    echo "  *** 仍含旧前缀: $f ***"; LEFT=$((LEFT+1))
  fi
done
echo "  残留文件数: $LEFT（旧前缀 = $CUR）"

echo
echo "=== 7. 确认中性前缀已写进 fftools ==="
HITS="$(grep -c -- "$FPREFIX" ffmpeg.exe 2>/dev/null || true)"
echo "  ffmpeg.exe 命中 $FPREFIX 的次数: ${HITS:-0}"

# 注：本步**不**跑 ffmpeg.exe 自报 —— 源码树里各产物分处子库目录，
# 直接跑会因找不到同级 DLL 而以 127 退出。自报与功能核查统一放在 04 收件之后。

if [ "$LEFT" -eq 0 ]; then
  echo
  echo "RESULT: PASS（下一步 04-finalize.sh）"
else
  echo
  echo "RESULT: FAIL"
  exit 1
fi
