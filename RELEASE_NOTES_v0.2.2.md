# CardSense v0.2.2 - Incremental Updates & Enhanced Status

**MAJOR**: Incremental hash index updates now download only NEW cards instead of rebuilding all 53K from scratch.

## ✨ Features Added

- **Incremental Hash Updates**: When Scryfall publishes new cards, cardsense now downloads and hashes ONLY the new ones (2 seconds vs 25 minutes for full rebuild)
  - Example: Today's update added 72 new cards in 2 seconds instead of reprocessing all 53,770
  - Still merges with existing index automatically
  - Uses existing hash files from GitHub releases when available

- **Enhanced Status Reporting**: Clear emoji-based status messages throughout the app lifecycle
  - 🔍 Checking for updates...
  - 📚 Loading card index...
  - ✅ Loaded X cards
  - 👀 Watching... (when ready)
  - 🎯 Auto-calibrating... (first card match)
  - ❌ Clear error messages with troubleshooting hints
  - ⬇️ Download progress when updating

- **Screen Recording Permission Detection**: Detects when screen capture is blocked and shows clear instructions to enable permissions in System Settings

## 🐛 Bugs Fixed

- Fixed auto-update downloading 281 MB from Scryfall every time new data was published (now uses incremental approach)
- Better error handling and reporting throughout startup and detection

## 📊 Index Stats

- **Cards**: 53,770 (was 53,698 in v0.2.1)
- **Hash files**: 26 MB bundled in .app (instant startup)
- **Update size**: Only new cards when updating from v0.2.1

## 📥 Installation (macOS 10.13+)

1. **Download** `cardsense.dmg` (below)
2. **Open** the DMG and drag CardSense to Applications
3. **Launch** from Applications (NOT from the DMG!)
4. **Grant permission** when prompted:
   - System Settings → Privacy & Security → Screen Recording
   - Enable "cardsense"
5. **Restart** the app if you granted permission manually
6. **Click Start** and right-click a card in MTGA to test

## 🔧 Technical Details

- Auto-update now checks GitHub releases first (5s download vs 25min rebuild)
- Falls back to incremental Scryfall update only when needed
- Existing v0.2.1 users will see seamless incremental update to 53,770 cards

---

**For developers**: See `hashindex/update_index.py` for the incremental update implementation.

**Full changelog**: https://github.com/waywardgeek/cardsense/compare/v0.2.1...v0.2.2
