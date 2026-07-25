# CodeRhapsody Guide to cardsense

**Last updated**: 2026-07-25  
**Project**: https://github.com/waywardgeek/cardsense  
**Current version**: v0.2.1

This document helps future CodeRhapsody instances (or other AI assistants) be effective when working on cardsense.

---

## Project Overview

**cardsense** is an accessibility tool for low-vision Magic: The Gathering Arena (MTGA) players. It uses screen capture + perceptual hashing to identify cards and read them aloud via text-to-speech.

**Built by**: Bill Cox (20/180 vision, macular dystrophy) and CodeRhapsody AI  
**Users**: Bill and Pete (both low-vision MTGA players)  
**License**: Apache 2.0

### Key Features
- Real-time card identification (dual pHash + OCR fallback)
- Fast TTS (550 WPM via macOS NSSpeechSynthesizer)
- 53K+ card database bundled (offline-ready)
- Auto-calibration for screen layout
- Apple-notarized macOS distribution

---

## Project Structure

```
cardsense/
├── capture/          # Screen capture + card detection
│   ├── gui.py        # Main GUI (Tkinter) - ENTRY POINT
│   └── detect.py     # Headless detector (testing)
├── hashindex/        # pHash matching + database
│   ├── phash.py      # Core pHash + OCR logic
│   ├── update_index.py   # Auto-updater (GitHub/Scryfall)
│   └── data/         # Hash files (gitignored, 26MB)
│       ├── phash_index.npz   (53K cards, dual 512-bit pHash)
│       └── phash_meta.json   (card metadata)
├── venv/             # Python virtual environment
├── dist/             # Build output (gitignored)
├── build.py          # PyInstaller build automation
├── notarize.py       # Apple notarization workflow
├── cardsense.spec    # PyInstaller configuration
└── entitlements.plist # macOS code signing entitlements
```

---

## Development Workflow

### Setup
```bash
cd ~/projects/cardsense
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# First run downloads hash files from GitHub (~5s)
venv/bin/python3 capture/gui.py
```

### Running from Source
```bash
# GUI mode (normal use)
venv/bin/python3 capture/gui.py

# Debug mode (saves crops to /tmp)
venv/bin/python3 capture/gui.py --debug

# Headless loop (testing)
venv/bin/python3 -u capture/detect.py --loop --debug
# NOTE: -u is REQUIRED - unbuffered output, or logs are hidden
```

### Git Workflow
```bash
# Bill's home instance commits as CodeRhapsody (not Hewitt)
git config user.name "CodeRhapsody"
git config user.email "coderhapsody@coderhapsody.local"

# Standard workflow
git add -A
git commit -m "..."
git push origin main
```

---

## Building & Releasing

### 1. Local Build (macOS .app)

```bash
# Build signed .app with bundled hash files
python build.py

# Output: dist/cardsense.app (419 MB)
# Includes: 26MB hash files bundled at Contents/Resources/hashindex/data/
```

**Key files**:
- `build.py` - Automated build script (uses venv Python)
- `cardsense.spec` - PyInstaller config (code signing, entitlements, icon)
- `entitlements.plist` - Hardened Runtime settings (JIT, unsigned memory)

### 2. Testing Built App

```bash
# Launch GUI
open dist/cardsense.app

# Or run from command line to see output
/path/to/cardsense.app/Contents/MacOS/cardsense --debug

# Check bundled hash files
ls -lh dist/cardsense.app/Contents/Resources/hashindex/data/
# Should show: phash_index.npz, phash_meta.json
```

### 3. Notarization (macOS Distribution)

**Prerequisites** (one-time setup):
- Apple Developer account ($99/year)
- Developer ID Application certificate (already installed)
- App-specific password stored in Keychain:
  ```bash
  xcrun notarytool store-credentials CardSense \
    --apple-id waywardgeek@gmail.com \
    --team-id B2SUY7SU9A
  ```

**Notarize & Create DMG**:
```bash
# Build + notarize + create DMG (15-20 min total)
python notarize.py

# Or skip rebuild (if already built)
python notarize.py --skip-build

# Output:
# - dist/cardsense.app (signed, notarized, stapled)
# - dist/cardsense.dmg (86 MB, ready for distribution)
```

**What notarize.py does**:
1. Builds signed .app (or skips if `--skip-build`)
2. Creates ZIP for Apple
3. Submits to Apple notarization service (~5-15 min wait)
4. Staples notarization ticket to .app
5. Creates DMG for distribution

**Notarization credentials**:
- Apple ID: `waywardgeek@gmail.com`
- Team ID: `B2SUY7SU9A`
- Keychain profile: `CardSense`
- Certificate: `Developer ID Application: Bill Cox (B2SUY7SU9A)`

### 4. Creating GitHub Release

**Update version** in `cardsense.spec`:
```python
'CFBundleShortVersionString': '0.2.2',  # Change this
'CFBundleVersion': '0.2.2',             # And this
```

**Create release notes** (`RELEASE_NOTES_v0.2.2.md`):
```markdown
# CardSense vX.Y.Z - Title

Brief description of changes.

## 🐛 Bugs Fixed / ✨ Features Added

- Fixed: ...
- Added: ...

## 📥 Installation (macOS 10.13+)

1. **Download** `cardsense.dmg` (below)
...
```

**Publish release**:
```bash
# Create release with DMG
gh release create v0.2.2 \
  --title "CardSense v0.2.2 - Title" \
  --notes-file RELEASE_NOTES_v0.2.2.md \
  dist/cardsense.dmg

# Verify release
gh release view v0.2.2 --repo waywardgeek/cardsense
```

**Commit release**:
```bash
git add cardsense.spec RELEASE_NOTES_v0.2.2.md
git commit -m "Release v0.2.2 - Title

- Updated version in cardsense.spec
- Created release notes

Release: https://github.com/waywardgeek/cardsense/releases/tag/v0.2.2
Notarization: <submission-id> (Accepted)
DMG: XX.X MB, notarized and stapled"

git push origin main
```

---

## Key Technical Details

### PyInstaller Bundle Path Detection (CRITICAL!)

**Problem**: Bundled data files aren't found in .app because `__file__` points to wrong location.

**Solution** (in `hashindex/phash.py`):
```python
import sys
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Running from PyInstaller bundle
    DATA_DIR = os.path.join(sys._MEIPASS, "hashindex", "data")
else:
    # Running from source
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
```

**This was the v0.2.0 → v0.2.1 critical fix!** Without it, bundled hash files aren't found and the app tries to download 281 MB on every launch.

### Screen Recording Permission

**First launch flow**:
1. User launches app from Applications (NOT from DMG!)
2. Clicks "Start"
3. macOS prompts for screen recording permission
4. User grants permission in System Settings
5. User restarts app
6. App now works

**Permission descriptions** (in `cardsense.spec` Info.plist):
- `NSScreenCaptureUsageDescription` - shown in permission prompt
- `NSMicrophoneUsageDescription` - side effect of screen capture API

**Debugging permission issues**:
```bash
# Check permission status
sqlite3 ~/Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT service, client, auth_value FROM access WHERE service='kTCCServiceScreenCapture'"

# Reset permission (forces re-prompt)
tccutil reset ScreenCapture com.coderhapsody.cardsense

# Manually grant permission
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
```

### Hash Index Files

**Location in source**: `hashindex/data/` (gitignored)  
**Location in bundle**: `Contents/Resources/hashindex/data/`  
**Size**: ~26 MB total (phash_index.npz 11MB, phash_meta.json 15MB)

**Update strategy**:
1. **First run**: Downloads from GitHub release (~5s)
2. **Subsequent runs**: Checks GitHub for updates, skips if current
3. **Installers**: Hash files bundled → instant startup

**Never commit hash files to git** - they're 26MB and updated frequently. Use GitHub releases instead.

### Cross-Platform TTS

**macOS** (`MacOSSpeaker`):
- Uses `NSSpeechSynthesizer` via PyObjC
- Async thread with `NSRunLoop`
- 550 WPM Reed voice default
- In-process (0.002s latency)

**Windows** (`WindowsSpeaker`):
- Uses `pyttsx3` + SAPI 5
- Async thread with command queue
- 450 WPM mapped from 550 WPM logical rate
- Prefers Zira/Hazel voices

**Factory** (`get_speaker()`):
- Detects platform via `platform.system()`
- Returns appropriate Speaker instance

---

## Common Issues & Solutions

### "App doesn't detect cards"

**Check**:
1. Screen recording permission granted?
2. App installed to /Applications (not running from DMG)?
3. MTGA in windowed or fullscreen mode (not minimized)?
4. Try Stop → Start to reset detection

**Debug**:
```bash
# Run with --debug to save crops
/Applications/cardsense.app/Contents/MacOS/cardsense --debug

# Check for debug files
ls -lt /tmp/cardsense_*

# If no files: permission issue
# If files exist: check crops for what's being captured
```

### "Hash files missing / downloading 281 MB"

**Cause**: PyInstaller bundle path detection broken (see v0.2.1 fix above)

**Verify fix**:
```bash
# Check bundled files exist
ls -lh dist/cardsense.app/Contents/Resources/hashindex/data/

# Should show phash_index.npz and phash_meta.json
# If missing: build process didn't bundle them
```

### "Permission prompt every launch"

**Cause**: App signature changed (rebuild with different code/icon)

**Solution**: One-time - grant permission, it will stick for that build

### "Notarization failed"

**Check**:
```bash
# Get submission logs
xcrun notarytool log <submission-id> \
  --keychain-profile CardSense

# Common issues:
# - Missing entitlements (already configured)
# - Unsigned binaries (PyInstaller handles this)
# - Hardened runtime issues (already configured)
```

### "Build fails: No module named PyInstaller"

**Cause**: Running with system Python instead of venv

**Solution**: Use `venv/bin/python3 build.py` (build.py auto-detects venv)

---

## Testing Checklist

**Before releasing**:

1. ✅ Build from clean state: `rm -rf dist build && python build.py`
2. ✅ Test built app: Launch, click Start, verify TTS works
3. ✅ Check bundled files: `ls dist/cardsense.app/Contents/Resources/hashindex/data/`
4. ✅ Test with MTGA: Right-click card, verify it's read aloud
5. ✅ Test permission flow: Delete app, reinstall, verify permission prompt
6. ✅ Notarize: `python notarize.py`
7. ✅ Test DMG: Mount, drag to Applications, verify works
8. ✅ Create release: Update version, create release notes, publish
9. ✅ Verify download: Download DMG from GitHub, test fresh install

---

## Future Sessions - Quick Start

**Resume work on cardsense**:
```bash
cd ~/projects/cardsense

# Check project state
git status
git log --oneline -5
gh release list

# Run from source (test changes)
venv/bin/python3 capture/gui.py --debug

# Build and release
python build.py
python notarize.py
gh release create vX.Y.Z --title "..." --notes-file RELEASE_NOTES_vX.Y.Z.md dist/cardsense.dmg
```

**Key files to read first**:
- `README.md` - User-facing instructions
- `ROADMAP.md` - Future plans, known issues
- `design.md` - Architecture decisions
- `hashindex/phash.py` - Core pHash + OCR logic
- `capture/gui.py` - Main application entry point

**Bill's preferences**:
- This is a fun/accessibility project (not urgent)
- Conservative matching (false positives destroy trust)
- Real-time collaboration at 750 WPM
- Built for him and Pete (both low-vision MTGA players)

---

## Resources

- **Repo**: https://github.com/waywardgeek/cardsense
- **Releases**: https://github.com/waywardgeek/cardsense/releases
- **Scryfall API**: https://scryfall.com/docs/api
- **PyInstaller**: https://pyinstaller.org/
- **Apple Notarization**: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution

---

*This guide is maintained by CodeRhapsody. Update it when workflows change or new patterns emerge.*
