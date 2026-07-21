# cardsense

Screen-watching accessibility tool for MTG Arena. See design.md for full
architecture. No OCR — matches zoomed card images against Scryfall via
perceptual hashing.

## Status: early build, see design.md

## Layout

- `design.md` — architecture doc
- `hashindex/` — offline Scryfall bulk-download + pHash index builder (standalone, testable without MTGA)
- `capture/` — screen capture + stable-region detector (needs MTGA running to test against real footage)
- `speak/` — TTS readout formatting
