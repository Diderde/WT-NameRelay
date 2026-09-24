# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""把构建出的 wheel 中和为"无构建机痕迹"再入库/发布。

做两件事：
  1. 把 SBOM（`*.dist-info/sboms/*.cyclonedx.json`）里的**项目绝对路径**
     （`path+file:///<构建机上的项目目录>/vtcore`）替换为中性值；
  2. 重写 `RECORD`（因为 SBOM 内容变了，其 sha256/大小必须同步）。

二进制本体（`.pyd`）的路径痕迹由构建期 `--remap-path-prefix` 解决，本脚本不碰它。
用法：python tools/sanitize_wheel.py <源 wheel> <目标 wheel>
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

# 判定用的"路径形状"字样。**本机身份字样（用户名、开发根目录名）不写死在这里** ——
# 本文件随公开分支分发，写死等于把身份信息当名单一起发布；改为运行时从环境推导
# （在构建机上检出效果与写死一致）。泛化的路径形状可以保留。
def _identity_needles() -> tuple[bytes, ...]:
    items: list[bytes] = []
    home = Path.home()
    if home.name:
        items.append(home.name.encode("utf-8", "replace"))
    parent = Path(__file__).resolve().parents[1].parent.name
    if parent:
        items.append(parent.encode("utf-8", "replace"))
    return tuple(dict.fromkeys(items))


NEEDLES = (*_identity_needles(), b"C:\\Users", b"D:\\")

# SBOM 里的绝对路径引用：`path+file:///<构建机上的任意绝对路径>/<包名>#<版本>`
# → 归一为 `<包名>#<版本>`（无路径形状，且不同构建机产出完全一致）。
SBOM_PATH_REF = re.compile(r"path\+file:///(?:[^\"#]*/)?(?P<name>[^/\"#]+)#")

if len(sys.argv) < 3:
    print(__doc__)
    raise SystemExit(2)
src = Path(sys.argv[1])
dst = Path(sys.argv[2])


def record_hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return "sha256=" + digest.decode()


def main() -> int:
    if not src.exists():
        print(f"FAIL 源 wheel 不存在：{src}")
        return 1

    with zipfile.ZipFile(src) as archive:
        entries = {info.filename: archive.read(info.filename) for info in archive.infolist()}

    replaced = 0
    for name, data in list(entries.items()):
        if "sboms/" in name and name.endswith(".json"):
            text = data.decode("utf-8")
            text, count = SBOM_PATH_REF.subn(r"\g<name>#", text)
            replaced += count
            entries[name] = text.encode("utf-8")

    # 重建 RECORD（列出除自身外的全部文件）
    record_lines = [f"{name},{record_hash(data)},{len(data)}" for name, data in entries.items() if not name.endswith("/RECORD")]
    record_name = next((name for name in entries if name.endswith("/RECORD")), None)
    if record_name is None:
        print("FAIL 找不到 RECORD")
        return 1
    record_lines.append(f"{record_name},,")
    entries[record_name] = ("\n".join(record_lines) + "\n").encode("utf-8")

    dst.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in entries.items():
            out.writestr(name, data)
    dst.write_bytes(buffer.getvalue())

    # 复核：新 wheel 里不应再有构建机痕迹
    with zipfile.ZipFile(dst) as archive:
        leftovers = {}
        for info in archive.infolist():
            data = archive.read(info.filename)
            hits = {n.decode("latin1"): data.count(n) for n in NEEDLES if data.count(n)}
            if hits:
                leftovers[info.filename] = hits
        bad = archive.testzip()

    print(f"源   {src.name}  {src.stat().st_size} 字节")
    print(f"目标 {dst.name}  {dst.stat().st_size} 字节（SBOM 替换 {replaced} 处）")
    print(f"zip 完整性：{'OK' if bad is None else f'FAIL {bad}'}")
    if leftovers:
        print("FAIL 仍有痕迹：")
        for name, hits in leftovers.items():
            print(f"  {name}: {hits}")
        return 1
    print("RESULT: PASS 无构建机路径痕迹")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
