# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path(SPECPATH)
FFMPEG = ROOT / 'app' / 'resources' / 'ffmpeg'
ffmpeg_datas = [
    (str(FFMPEG / 'LICENSE.txt'), 'app/resources/ffmpeg'),
    (str(FFMPEG / 'bin' / 'ffmpeg.exe'), 'app/resources/ffmpeg/bin'),
    (str(FFMPEG / 'bin' / 'ffprobe.exe'), 'app/resources/ffmpeg/bin'),
]
ffmpeg_datas.extend(
    (str(path), 'app/resources/ffmpeg/bin')
    for path in sorted((FFMPEG / 'bin').glob('*.dll'))
)

ICONS = ROOT / 'app' / 'resources' / 'icons'
# 导航图标（Bootstrap Icons 1.11.3, MIT）与随附的上游许可正文。NavRail 运行期优先读 Qt
# 资源 `:/icons/`，这里随包收一份磁盘副本作回退，同时让 MIT「随副本保留版权与许可声明」
# 的义务随 EXE/onedir 一起成立（release 暂存的 licenses/ 另有一份 Bootstrap-Icons-MIT.txt）。
icons_datas = [
    (str(ICONS / 'bootstrap-icons-LICENSE.txt'), 'app/resources/icons'),
]
icons_datas.extend(
    (str(path), 'app/resources/icons')
    for path in sorted(ICONS.glob('nav-*.svg'))
)

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[],
    binaries=[],
    datas=ffmpeg_datas + icons_datas,
    hiddenimports=['pyqtgraph', 'numpy'],
    hookspath=[str(ROOT / 'packaging' / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pyqtgraph.opengl', 'OpenGL'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WT-NameRelay-debug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(ROOT / 'windows_version_info.txt'),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WT-NameRelay-debug',
)
