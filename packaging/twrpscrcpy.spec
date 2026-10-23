# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe used by the release workflow.

The two ARM helper binaries are data files: they are pushed to the phone and
executed there, never on the host.
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
BIN = ROOT / "twrpscrcpy" / "bin"

datas = [
    (str(BIN / "fbstream-arm64"), "twrpscrcpy/bin"),
    (str(BIN / "fbstream-arm"), "twrpscrcpy/bin"),
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # A .app bundle cannot be one file; use the onedir layout so macOS
    # security and the bundle structure stay valid.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="twrpscrcpy",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
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
        upx=False,
        upx_exclude=[],
        name="twrpscrcpy",
    )
    app = BUNDLE(
        coll,
        name="twrpscrcpy.app",
        icon=None,
        bundle_identifier="io.github.twrpscrcpy",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="twrpscrcpy",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
