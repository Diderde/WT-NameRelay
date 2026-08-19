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

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[],
    binaries=[],
    datas=ffmpeg_datas,
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
    name='WT-NameRelay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(ROOT / 'windows_version_info.txt'),
    icon=[str(ROOT / 'app' / 'resources' / 'icons' / 'wt_name_relay.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WT-NameRelay',
)
