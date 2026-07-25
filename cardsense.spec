# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for cardsense cross-platform build.

Usage:
    # macOS
    pyinstaller cardsense.spec
    
    # Windows
    pyinstaller cardsense.spec
    
This bundles the hash files (phash_index.npz, phash_meta.json) so the app
works offline immediately after install, no download required.
"""
import os
import sys
from pathlib import Path

# Determine platform
IS_MACOS = sys.platform == 'darwin'
IS_WINDOWS = sys.platform == 'win32'

# Paths
ROOT = Path('.').absolute()
HASH_DIR = ROOT / 'hashindex' / 'data'

# Data files to bundle
datas = []

# Bundle hash files if they exist (instant startup)
if HASH_DIR.exists():
    hash_files = [
        ('hashindex/data/phash_index.npz', 'hashindex/data'),
        ('hashindex/data/phash_meta.json', 'hashindex/data'),
    ]
    for src, dest in hash_files:
        if os.path.exists(src):
            datas.append((src, dest))
            print(f"✅ Bundling {src}")
        else:
            print(f"⚠️  {src} not found, will download on first run")

# Platform-specific hidden imports
hiddenimports = [
    'queue',
    'threading',
    'tkinter',
    'cv2',
    'numpy',
    'pytesseract',
    'requests',
]

if IS_MACOS:
    hiddenimports.extend([
        'AppKit',
        'Foundation',
        'objc',
    ])
elif IS_WINDOWS:
    hiddenimports.extend([
        'pyttsx3',
        'pyttsx3.drivers',
        'pyttsx3.drivers.sapi5',
    ])

block_cipher = None

a = Analysis(
    ['capture/gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='cardsense',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if IS_WINDOWS else 'icon.icns',  # Optional: add icons later
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='cardsense',
)

# macOS .app bundle
if IS_MACOS:
    app = BUNDLE(
        coll,
        name='cardsense.app',
        icon='icon.icns',  # Optional: add icon later
        bundle_identifier='com.coderhapsody.cardsense',
        info_plist={
            'CFBundleName': 'CardSense',
            'CFBundleDisplayName': 'CardSense',
            'CFBundleShortVersionString': '0.2.0',
            'CFBundleVersion': '0.2.0',
            'LSMinimumSystemVersion': '10.13',  # macOS High Sierra
            'NSHighResolutionCapable': True,
        },
    )
