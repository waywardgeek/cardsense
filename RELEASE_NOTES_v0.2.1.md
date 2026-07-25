# CardSense v0.2.1 - Critical Fix

**CRITICAL UPDATE**: This release fixes a bug that prevented the app from working at all in v0.2.0.

## 🐛 Bug Fixed

**Hash files not found in bundled .app**
- v0.2.0 tried to download 281 MB of card data from Scryfall on every launch
- The bundled hash files (26 MB) weren't being found due to incorrect path detection
- Fixed by detecting PyInstaller bundle and using correct resource path
- App now works instantly with bundled data

## 📥 Installation (macOS 10.13+)

1. **Download** `cardsense.dmg` (below)
2. **Double-click** to mount
3. **Drag** cardsense.app to your Applications folder
4. **Launch** from Applications
5. **Grant screen recording permission** when prompted
6. **Click Start** and right-click cards in MTGA!

## ⚠️ Upgrading from v0.2.0

If you installed v0.2.0, simply:
1. Delete the old cardsense.app from Applications
2. Install this version
3. You may need to re-grant screen recording permission (one-time)

## 🔧 Technical Details

**What changed:**
- Fixed `DATA_DIR` path detection in `hashindex/phash.py`
- Now detects PyInstaller bundle via `sys.frozen` and `sys._MEIPASS`
- Bundled hash files are found at `sys._MEIPASS/hashindex/data/`

**Before:** App launched but couldn't match any cards (hash files missing)  
**After:** App works instantly with bundled 53K+ card database

## 📝 All v0.2.x Features

- Real-time MTGA card identification via screen capture
- 550 WPM text-to-speech (adjustable 200-750)
- Dual pHash + OCR fallback for accuracy
- 53,000+ cards bundled (offline-ready)
- Auto-calibration for your screen
- Apple-notarized (no Gatekeeper warnings)

## 🙏 Credits

- **Bill Cox** - Creator, tester
- **CodeRhapsody** - AI development assistant  
- **Scryfall** - Card database

## 📝 License

Apache 2.0 License - free for personal and commercial use.

---

**Full changelog**: https://github.com/waywardgeek/cardsense/compare/v0.2.0...v0.2.1
