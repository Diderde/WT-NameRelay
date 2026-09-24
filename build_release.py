"""Build debug onedir, release onedir, then release onefile for Windows."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYINSTALLER = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean"]
VERSION = ROOT / "windows_version_info.txt"
HOOKS = ROOT / "packaging" / "hooks"


def prepare_ffmpeg_payload() -> Path:
    """Stage only the FFmpeg executables and shared libraries used at runtime."""
    source = ROOT / "app" / "resources" / "ffmpeg"
    payload = ROOT / "build" / "package-assets" / "ffmpeg"
    resolved = payload.resolve()
    if ROOT.resolve() not in resolved.parents:
        raise RuntimeError(f"拒绝清理工作区外路径：{resolved}")
    if payload.exists():
        shutil.rmtree(payload)
    (payload / "bin").mkdir(parents=True)
    shutil.copy2(source / "LICENSE.txt", payload / "LICENSE.txt")
    for executable in ("ffmpeg.exe", "ffprobe.exe"):
        shutil.copy2(source / "bin" / executable, payload / "bin" / executable)
    for library in sorted((source / "bin").glob("*.dll")):
        shutil.copy2(library, payload / "bin" / library.name)
    return payload


def verify_ffmpeg_license() -> None:
    """确认内置 FFmpeg 可以合法地按 LGPL-3.0-or-later 分发。

    两道检查缺一不可：

    1. `ffmpeg -L` 的自报 —— 只能证明 **FFmpeg 自己**的 configure 开关是 LGPL 组合；
    2. `tools/audit_ffmpeg_license.py` 的二进制审计 —— 证明**经第三方库间接引入**的组件里
       没有 GPL-only 代码。

    第 2 道不可省：BtbN 的 `win64-lgpl-shared` 变体把 GPL-2.0-or-later 的 FFTW 经
    chromaprint（`-DFFT_LIB=fftw3`）静态链进了 `avformat-63.dll`，而第 1 道检查
    **完全看不见它** —— FFmpeg 的自报只看自己的 configure 行。
    重编步骤见 `FFMPEG_BUILD_INFO.md` §2。
    """
    ffmpeg = ROOT / "app" / "resources" / "ffmpeg" / "bin" / "ffmpeg.exe"
    result = subprocess.run(
        [str(ffmpeg), "-L"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    text = result.stdout + result.stderr
    if "GNU Lesser General Public License" not in text or "version 3" not in text:
        raise RuntimeError("内置 FFmpeg 的许可证输出与 LGPL-3.0-or-later 清单不一致")

    audit = ROOT / "tools" / "audit_ffmpeg_license.py"
    audited = subprocess.run(
        [sys.executable, str(audit)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if audited.returncode != 0:
        raise RuntimeError(
            "内置 FFmpeg 未通过二进制许可审计：含 GPL-only 组件，不能按 LGPL 分发。\n"
            "重编步骤见 FFMPEG_BUILD_INFO.md §2（去掉 chromaprint 即可移除 FFTW）。\n"
            "--- 审计输出 ---\n" + (audited.stdout or "")[-1500:]
        )


def build(
    name: str,
    *,
    onefile: bool,
    console: bool,
    dist: Path,
    ffmpeg_payload: Path,
) -> None:
    command = [
        *PYINSTALLER,
        "--name",
        name,
        "--version-file",
        str(VERSION),
        "--distpath",
        str(dist),
        "--workpath",
        str(ROOT / "build" / name),
        "--specpath",
        str(ROOT / "build" / "generated-specs"),
        "--additional-hooks-dir",
        str(HOOKS),
        "--hidden-import",
        "pyqtgraph",
        "--hidden-import",
        "numpy",
        "--exclude-module",
        "pyqtgraph.opengl",
        "--exclude-module",
        "OpenGL",
    ]
    command.append("--onefile" if onefile else "--onedir")
    command.append("--console" if console else "--windowed")
    command.extend(
        ["--add-data", f"{ffmpeg_payload};app/resources/ffmpeg"]
    )
    command.append(str(ROOT / "main.py"))
    subprocess.run(command, cwd=ROOT, check=True)


def stage_release() -> Path:
    """Stage the verified onedir build with notices and license texts."""
    release = ROOT / "release" / "WT-NameRelay-1.0.0"
    if release.exists():
        shutil.rmtree(release)
    shutil.copytree(ROOT / "dist" / "onedir" / "WT-NameRelay", release)
    shutil.copy2(ROOT / "THIRD_PARTY_LICENSES.md", release / "THIRD_PARTY_LICENSES.txt")
    shutil.copy2(ROOT / "PROJECT_USAGE_NOTICE.md", release / "PROJECT_USAGE_NOTICE.md")
    shutil.copy2(ROOT / "LICENSE", release / "LICENSE.txt")
    shutil.copy2(ROOT / "FFMPEG_BUILD_INFO.md", release / "FFMPEG_BUILD_INFO.md")
    shutil.copy2(ROOT / "release" / "README.txt", release / "README.txt")
    shutil.copytree(ROOT / "licenses", release / "licenses")
    archive = ROOT / "release" / "WT-NameRelay-1.0.0-windows-x64"
    shutil.make_archive(str(archive), "zip", release.parent, release.name)
    return release


if __name__ == "__main__":
    verify_ffmpeg_license()
    ffmpeg_payload = prepare_ffmpeg_payload()
    build(
        "WT-NameRelay-debug",
        onefile=False,
        console=True,
        dist=ROOT / "dist" / "debug",
        ffmpeg_payload=ffmpeg_payload,
    )
    build(
        "WT-NameRelay",
        onefile=False,
        console=False,
        dist=ROOT / "dist" / "onedir",
        ffmpeg_payload=ffmpeg_payload,
    )
    build(
        "WT-NameRelay",
        onefile=True,
        console=False,
        dist=ROOT / "dist" / "onefile",
        ffmpeg_payload=ffmpeg_payload,
    )
    print(f"Release staged at {stage_release()}")
