# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""检查构建出的 wheel 里是否残留**构建机痕迹**（入库或发布前必查）。

判定用的是"路径形状"而非裸词：项目名 `WT-NameRelay` 出现在 METADATA 里是正常的，
只有带分隔符/位于用户目录的形式（`…\\WT-NameRelay\\`、`C:\\Users\\…`）才算泄漏。

用法：python tools/check_wheel_leaks.py [wheel ...]
不给参数时扫描 `vtcore/wheels/*.whl`。全部通过返回 0，任一命中返回 1。
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _machine_needles() -> tuple[bytes, ...]:
    """本机身份字样（用户名、开发根目录名）——**运行时推导，不写死在源码里**。

    本文件会随公开分支分发，把真实用户名/开发根名字面量写在 NEEDLES 里，
    等于把身份信息当成"名单"一起发布。改为运行时从环境推导：
    在构建机上检出效果与写死完全一致，在别的机器上则自动只查那台机器自己的痕迹。
    """
    items: list[bytes] = []
    home = Path.home()
    if home.name:
        items.append(home.name.encode("utf-8", "replace"))
    parent = REPO.parent.name
    if parent:
        items.append(parent.encode("utf-8", "replace"))
    return tuple(dict.fromkeys(items))


NEEDLES = (
    *_machine_needles(),
    b"C:\\Users",
    b"/Users/",
    b".cargo",
    b"WT-NameRelay\\",
    b"WT-NameRelay/",
)

# 形状类（正则）：**任何盘符路径**都算痕迹。构建期 remap 若留下 `C:\cargo\...` 这种虚拟绝对路径，
# 虽不含用户名，仍不可移植，必须一并消除（remap 目标应写成 POSIX 风格，如 `/cargo`）。
SHAPES = (
    re.compile(rb"[A-Za-z]:\\"),
    re.compile(rb"[A-Za-z]:/(?!/)"),
)


def check(path: Path) -> bool:
    worst = 0
    with zipfile.ZipFile(path) as archive:
        print(f"{path.name}  {path.stat().st_size} 字节")
        for name in archive.namelist():
            data = archive.read(name)
            hits = {n.decode("latin1"): data.count(n) for n in NEEDLES if data.count(n)}
            for pattern in SHAPES:
                count = len(pattern.findall(data))
                if count:
                    hits[f"形状/{pattern.pattern.decode('latin1')}"] = count
            worst = max(worst, sum(hits.values()))
            print(f"  {name:44} {len(data):>8} B  " + (str(hits) if hits else "无路径痕迹"))
    print(f"  -> {'PASS 无构建机痕迹' if worst == 0 else f'FAIL 命中 {worst} 处'}")
    return worst == 0


def main() -> int:
    targets = [Path(arg) for arg in sys.argv[1:]]
    if not targets:
        targets = sorted((REPO / "vtcore" / "wheels").glob("*.whl"))
    if not targets:
        print("FAIL 未找到待检查的 wheel（可用参数指定路径）")
        return 1
    ok = True
    for path in targets:
        if not path.exists():
            print(f"FAIL 不存在：{path}")
            ok = False
            continue
        ok = check(path) and ok
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
