# Building cardsense Installers

This guide walks through building standalone installers for macOS and Windows that bundle all dependencies (including the 26MB hash index) for instant startup.

## Prerequisites

1. **Python 3.9+** (3.11+ recommended)
2. **Dependencies installed**: `pip install -r requirements.txt`
3. **Hash index downloaded**: Run `python hashindex/update_index.py` once to download the hash files

## Build Steps

### macOS (.app bundle)

```bash
# 1. Ensure hash files exist
python hashindex/update_index.py  # Downloads ~26MB if not present

# 2. Build the .app bundle
pyinstaller cardsense.spec

# Output: dist/cardsense.app (~100MB with bundled hash index)
```

**Testing the .app**:
```bash
open dist/cardsense.app
# Should launch immediately, no download, ready to use
```

**Distribution**:
- Zip the .app: `cd dist && zip -r cardsense-macos.zip cardsense.app`
- Or create DMG: `hdiutil create -volname CardSense -srcfolder dist/cardsense.app -ov -format UDZO cardsense-macos.dmg`

**Code Signing** (optional, prevents Gatekeeper warnings):
```bash
# Requires Apple Developer account ($99/year)
codesign --deep --force --verify --verbose --sign "Developer ID Application: Your Name" dist/cardsense.app
```

### Windows (.exe)

```bash
# 1. Ensure hash files exist
python hashindex\update_index.py  # Downloads ~26MB if not present

# 2. Build the .exe
pyinstaller cardsense.spec

# Output: dist\cardsense\ (~100MB with bundled hash index)
```

**Testing the .exe**:
```bash
dist\cardsense\cardsense.exe
# Should launch immediately, no download, ready to use
```

**Creating an Installer** (optional, using Inno Setup):
1. Download [Inno Setup](https://jrsoftware.org/isinfo.php)
2. Create `installer.iss` (see below)
3. Compile with Inno Setup → creates `cardsense-setup.exe`

**Distribution**:
- Zip the folder: `Compress-Archive -Path dist\cardsense -DestinationPath cardsense-windows.zip`
- Or use Inno Setup for a proper installer

## File Sizes

- Source repo: ~500KB
- Hash index (downloaded): ~26MB
- Built .app (macOS): ~100MB (includes Python + deps + hash index)
- Built .exe (Windows): ~120MB (includes Python + deps + hash index)

## Troubleshooting

### "No module named X" error when running built app
- Add the module to `hiddenimports` in `cardsense.spec`
- Rebuild with `pyinstaller cardsense.spec`

### Hash index not bundled
- Verify `hashindex/data/phash_index.npz` exists before building
- Check PyInstaller output for "✅ Bundling hashindex/data/phash_index.npz"

### macOS Gatekeeper warning
- Sign the .app with a Developer ID (requires Apple Developer account)
- Or: users can right-click → Open → Open Anyway (first launch only)

### Windows SmartScreen warning
- Sign the .exe with a code-signing certificate
- Or: users can click "More info" → "Run anyway"

## Inno Setup Script (Windows)

Save as `installer.iss`:

```ini
[Setup]
AppName=CardSense
AppVersion=0.2.0
DefaultDirName={pf}\CardSense
DefaultGroupName=CardSense
OutputDir=.
OutputBaseFilename=cardsense-setup
Compression=lzma2
SolidCompression=yes

[Files]
Source: "dist\cardsense\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\CardSense"; Filename: "{app}\cardsense.exe"
Name: "{commondesktop}\CardSense"; Filename: "{app}\cardsense.exe"

[Run]
Filename: "{app}\cardsense.exe"; Description: "Launch CardSense"; Flags: postinstall nowait skipifsilent
```

Compile: `"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss`
