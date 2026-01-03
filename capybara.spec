# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import sys
import os

datas = []
binaries = []
hiddenimports = []

# Collect all data and submodules from capybara
# We need to ensure src is in path to find capybara if it's not installed as package site-package
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))

# Manual collection for capybara to be safe
datas += collect_data_files('capybara')
hiddenimports += collect_submodules('capybara')

# Dependencies that often need help
datas += collect_data_files('tiktoken')
datas += collect_data_files('litellm')
hiddenimports += collect_submodules('litellm')
hiddenimports += collect_submodules('pydantic')
hiddenimports += ['uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'engineio.async_drivers.aiohttp']

block_cipher = None

a = Analysis(
    ['src/capybara/cli/main.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude all Qt bindings (capybara is CLI-only, no GUI needed)
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PySide2.QtCore',
        'PySide2.QtGui',
        'PySide2.QtWidgets',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # Exclude GUI/TK packages
        'tkinter',
        '_tkinter',
        'Tkinter',
        # Exclude matplotlib (if not used)
        'matplotlib',
        'matplotlib.pyplot',
        # Exclude test frameworks
        'pytest',
        'unittest',
        'nose',
        # Exclude IPython/Jupyter
        'IPython',
        'jupyter',
        'notebook',
        'qtconsole',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='capybara',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
