#!/usr/bin/env bash
# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
#
# 01 - 把 pacman 的 mingw / msys 源指向国内镜像，然后装工具链与三个外部库。
#
# 为什么只要三个外部库：本程序用到的 FFmpeg 能力是
#   * 编码：MP3（libmp3lame）、Opus（libopus）；FLAC 与 AAC(m4a) 用 FFmpeg 自带编码器
#   * 滤镜：ebur128 / loudnorm / silencedetect / showspectrumpic / anullsrc / aresample
#           / aformat / atrim / asetpts / concat —— 全部自带
#   * 输入：-f lavfi（libavdevice 的 lavfi indev）—— 自带
#   * PNG 输出：zlib
# 因此不需要原 BtbN 构建里的那 57 个外部组件。
#
# 注意本版 MSYS2 的 pacman.conf 用的是**单个** `/etc/pacman.d/mirrorlist.mingw`
# （所有 mingw 仓库共用），不存在 mirrorlist.mingw64 之类文件 —— 逐个去写
# mirrorlist.mingw64/ucrt64/clang64 是无效的（本次构建踩过这个坑）。
#
# 用法（在 MSYS2 MINGW64 shell 里）：
#   MSYSTEM=MINGW64 bash tools/ffmpeg-build/01-toolchain.sh
#
# 环境变量：
#   MSYS2_MIRROR  镜像站前缀（默认清华）

set -euo pipefail

MIRROR="${MSYS2_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/msys2}"

echo "=== 1. 把 mingw / msys 源指向 $MIRROR ==="
for pair in "mingw:mingw/\$repo" "msys:msys/x86_64"; do
  name="${pair%%:*}"
  sub="${pair#*:}"
  f="/etc/pacman.d/mirrorlist.${name}"
  [ -f "$f" ] || { echo "  跳过（不存在）: $f"; continue; }
  [ -f "$f.orig" ] || cp "$f" "$f.orig"
  printf 'Server = %s/%s/\n' "$MIRROR" "$sub" > "$f"
  echo "  $f"
  sed 's/^/      /' "$f"
done

echo
echo "=== 2. 同步索引（应当很快；若仍慢说明镜像不通）==="
time pacman -Sy --noconfirm

echo
echo "=== 3. 安装工具链与依赖 ==="
time pacman -S --noconfirm --needed \
  make \
  diffutils \
  mingw-w64-x86_64-gcc \
  mingw-w64-x86_64-binutils \
  mingw-w64-x86_64-nasm \
  mingw-w64-x86_64-pkgconf \
  mingw-w64-x86_64-lame \
  mingw-w64-x86_64-opus \
  mingw-w64-x86_64-zlib

echo
echo "=== 4. 版本核对 ==="
gcc --version | head -1
nasm --version
make --version | head -1
pkg-config --modversion lame
pkg-config --modversion opus
pkg-config --modversion zlib

echo
echo "RESULT: PASS"
