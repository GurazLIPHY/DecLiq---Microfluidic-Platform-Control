# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['frontend_gui.py'],
    pathex=[],
    binaries=[
        ('uProcess_x64.pyd', '.'),  # Embarque la DLL LabSmith à la racine du bundle
    ],
    datas=[
        ('icon.svg', '.'),
    ],
    hiddenimports=[
        'serial',
        'serial.tools.list_ports',
        'PyQt6.sip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DecLiq',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Fenêtre pure (pas d'invite de commande noire en arrière-plan)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DecLiq',
)