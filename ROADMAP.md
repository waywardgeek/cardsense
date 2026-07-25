# cardsense Roadmap

## Current Status (2026-07-24)

✅ **Working**:
- macOS screen capture via mss
- Dual pHash matching (512-bit: full card + art region)
- NSSpeechSynthesizer TTS (550 WPM, Reed voice)
- Auto-update from Scryfall on startup
- Twiddle calibration for box alignment
- Debug logging for failed matches

⚠️ **Known Issues**:
- Detection rate ~50% (investigating via debug crops)
- NO_CARD_FRAMES=10 may be too slow
- Calibration speech timing (fixed but needs live testing)

## Phase 1: Reliability (Current)

- [ ] Investigate match failures — analyze `/tmp/cardsense_nomatch_*.png` crops
- [ ] Tune detection thresholds (max_dist, min_margin) based on real MTGA testing
- [ ] Add fallback for cards with alternate art / foils / showcase variants
- [ ] Optimize box position detection (may need per-card-type sizes)

## Phase 2: Windows Support

### Cross-platform Screen Capture
- [x] macOS: mss (working)
- [ ] Windows: test mss on Windows (should work, but needs validation)
- [ ] Linux: test mss on Linux (future)

### Cross-platform TTS
- [x] macOS: NSSpeechSynthesizer with NSRunLoop (working)
- [x] Windows: `pyttsx3` + SAPI 5 (implemented, async thread, 450 WPM default)
  - Uses async command queue pattern (matches macOS architecture)
  - Prefers Zira/Hazel voices, falls back to first available
- [ ] Windows testing: verify voice quality, adjust rate if needed
- [ ] Test fallback: Linux/other platforms (currently uses pyttsx3)

### Platform Detection
- [x] Detect OS (macOS/Windows/Linux) — using platform.system()
- [x] Load platform-specific TTS backend — get_speaker() factory in gui.py
- [ ] Platform-specific default box positions (MTGA window size/position varies)

## Phase 3: Installers for Low-Vision Users

**Goal**: One-click install, zero terminal commands, works immediately.

### Installer Infrastructure
- [x] PyInstaller spec file (cardsense.spec) — supports macOS .app and Windows .exe
- [x] Build script (build.py) — automated build with hash file bundling
- [x] Build documentation (BUILD.md) — step-by-step instructions
- [x] Bundle hash files (~26MB) → instant startup, no download
- [ ] Test macOS .app build
- [ ] Test Windows .exe build

### macOS Installer (.app bundle)
- [x] PyInstaller spec to bundle Python + dependencies
- [x] **Bundle hash index files (11MB + 15MB)** → instant startup, no download
- [ ] Test build: `python build.py` → dist/cardsense.app
- [ ] Code-sign the .app (prevents macOS Gatekeeper warnings)
- [ ] DMG installer with drag-to-Applications
- [ ] Accessibility: VoiceOver-friendly installer UI
- [ ] Auto-update mechanism (check GitHub releases, download new .app)

### Windows Installer (.exe + installer)
- [x] PyInstaller spec to bundle Python + dependencies
- [x] **Bundle hash index files** → instant startup, no download
- [ ] Test build: `python build.py` → dist/cardsense/cardsense.exe
- [ ] NSIS or Inno Setup installer (silent install option for screen readers)
- [ ] Code-sign the .exe (prevents Windows SmartScreen warnings)
- [ ] Start Menu shortcuts
- [ ] Accessibility: NVDA/JAWS-friendly installer
- [ ] Auto-update mechanism

### Installer UX for Low-Vision Users
- [ ] Large fonts, high-contrast UI
- [ ] Screen reader announcements at each step
- [ ] No required configuration — works immediately after install
- [ ] Optional: voice-guided setup (TTS during install)
- [ ] Clear error messages if MTGA not detected

## Phase 4: Advanced Features

- [ ] Multi-monitor support (detect MTGA window, follow it)
- [ ] Card history log (what opponent played, what you drew)
- [ ] Export match log to text file
- [ ] Hotkey to repeat last card (useful if you missed it)
- [ ] Configurable TTS templates (some users may want shorter/longer text)
- [ ] Support for other card games (Hearthstone, Legends of Runeterra)

## Phase 5: Community & Distribution

- [ ] Open-source release (MIT license?)
- [ ] Website with download links + video tutorial
- [ ] Submit to accessibility forums (low-vision gaming communities)
- [ ] Auto-update server (GitHub Releases or custom CDN)
- [ ] Telemetry (opt-in): track match failures to improve detection

## Technical Debt

- [ ] Replace fixed box with MTGA window detection (pygetwindow or similar)
- [ ] Add unit tests for pHash matching
- [ ] Add integration tests (synthetic card images)
- [ ] Profile performance (can we run at 60 FPS?)
- [ ] Reduce memory footprint (53K cards × 64 bytes = 3.4MB is fine, but check runtime)

---

## Notes

- **Bill's vision**: 20/180, listens at 750 wpm for reading, 550 wpm for cards
- **Pete**: Also low-vision, plays MTGA — potential second user
- **Priority**: Reliability > Features. Get detection to 95%+ before adding features.
