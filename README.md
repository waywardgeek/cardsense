# cardsense

Screen-watching accessibility tool for MTG Arena. See design.md for full
architecture. No OCR — matches zoomed card images against Scryfall via
perceptual hashing.

## Status

✅ **Working**: Detection, matching, TTS (550 WPM), twiddle calibration, GUI
⚠️ **Known Issues**: 
- Some cards fail to match (investigating - debug logging added)
- Calibration speech gets cut off by twiddle

## Quick Start

```bash
# Clone and install
git clone https://github.com/waywardgeek/cardsense.git
cd cardsense
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# First run (auto-downloads hash index from GitHub, ~5 seconds)
venv/bin/python3 capture/gui.py

# Right-click a card in MTGA → hear card name + oracle text
```

**First run**: Downloads 26MB hash index from GitHub release (~5s)  
**Subsequent runs**: Instant startup (checks for updates, skips if current)

## Layout

- `design.md` — architecture doc
- `hashindex/` — offline Scryfall bulk-download + pHash index builder (standalone, testable without MTGA)
  - `update_index.py` — auto-updater (fetches from Scryfall API)
  - `build_index.py` — legacy builder for pre-downloaded images
  - `phash.py` — dual pHash core (full card + art region)
- `capture/` — screen capture + stable-region detector (needs MTGA running to test against real footage)
  - `gui.py` — main launcher with TTS controls
- `speak/` — TTS readout formatting
