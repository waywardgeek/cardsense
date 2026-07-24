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
# First run (auto-updates hash index from Scryfall)
cd ~/projects/cardsense
venv/bin/python3 capture/gui.py

# Manual index update
venv/bin/python3 hashindex/update_index.py --force

# Check if update available (no download)
venv/bin/python3 hashindex/update_index.py --check-only
```

Right-click a card in MTGA → hear card name + oracle text

## Layout

- `design.md` — architecture doc
- `hashindex/` — offline Scryfall bulk-download + pHash index builder (standalone, testable without MTGA)
  - `update_index.py` — auto-updater (fetches from Scryfall API)
  - `build_index.py` — legacy builder for pre-downloaded images
  - `phash.py` — dual pHash core (full card + art region)
- `capture/` — screen capture + stable-region detector (needs MTGA running to test against real footage)
  - `gui.py` — main launcher with TTS controls
- `speak/` — TTS readout formatting
