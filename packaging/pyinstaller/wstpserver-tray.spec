# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parents[1]
SRC = ROOT / "src"
ENTRYPOINT = ROOT / "packaging" / "pyinstaller" / "entrypoint.py"
TRAY_ICON = SRC / "wolfram_pool_tray" / "assets" / "spikey.svg"


a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(SRC)],
    binaries=[],
    datas=[(str(TRAY_ICON), "wolfram_pool_tray/assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WSTPServerManager",
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WSTPServerManager",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="WSTPServerManager.app",
        icon=None,
        bundle_identifier="dev.local.wstpserver-manager",
    )
