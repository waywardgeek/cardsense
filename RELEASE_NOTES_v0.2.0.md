# CardSense v0.2.0 - Initial Public Release

**An accessibility tool for low-vision Magic: The Gathering Arena players.**

CardSense uses screen capture and perceptual hashing to identify MTGA cards and read them aloud via text-to-speech at 550 WPM, making the game accessible for players with visual impairments.

## ✨ Features

- **Real-time card identification**: Hover over a card in MTGA → hear it spoken instantly
- **Fast text-to-speech**: 550 WPM (adjustable) using macOS NSSpeechSynthesizer
- **Dual pHash + OCR**: Perceptual hashing for fast matching, OCR fallback for rendering differences
- **Auto-calibration**: Automatically detects and calibrates to your screen layout
- **Offline-ready**: 53K+ card database bundled (no download after install)
- **Zero configuration**: Drag to Applications and launch - it just works

## 🎯 Who Is This For?

- **Low-vision gamers** who want to play MTGA independently
- **Players with macular dystrophy** or other visual impairments
- **Anyone who listens faster than they read** (750+ WPM listeners)

Built by Bill Cox (20/180 vision, macular dystrophy) for himself and Pete, with assistance from CodeRhapsody AI.

## 📥 Installation

### macOS 10.13+ (High Sierra and later)

1. **Download** `cardsense.dmg` (below)
2. **Double-click** to mount the disk image
3. **Drag** CardSense.app to your Applications folder
4. **Launch** CardSense from Applications
5. **Grant permission** when prompted for screen recording (System Settings → Privacy & Security → Screen Recording)
6. **Click Start** and hover over a card in MTGA!

**No Gatekeeper warnings** - this app is notarized by Apple.

### First Launch

On first launch, you'll need to:
1. Grant screen recording permission (one-time setup)
2. Click "Start" to begin watching for cards
3. Right-click on a card in MTGA to hear it read aloud

## 🎮 Usage

1. Launch MTGA and CardSense
2. Click **Start** in CardSense
3. Right-click (or hover) on any card in MTGA
4. CardSense identifies the card and speaks:
   - Card name
   - Type line (Creature - Human Wizard, etc.)
   - Mana cost
   - Oracle text

**Controls:**
- **Speed slider**: Adjust TTS speed (200-750 WPM)
- **Voice dropdown**: Choose TTS voice
- **Test button**: Verify TTS is working
- **Start/Stop**: Enable/disable card detection

## 🔧 Technical Details

- **Detection method**: Dual perceptual hashing (full card + art box) + OCR fallback
- **Database**: 53,000+ cards from Scryfall (auto-updates on launch)
- **TTS**: macOS NSSpeechSynthesizer (Reed voice default, 550 WPM)
- **Screen capture**: 20 FPS frame analysis with motion detection
- **No OCR needed**: Matches card images directly (OCR only for fallback)

## 🐛 Known Issues

- **Permission prompt on updates**: macOS may ask for screen recording permission again after updates (grant it once)
- **MTGA must be in default layout**: Full-screen or windowed mode works, but non-standard UI layouts may fail
- **Some showcase/alternate art cards** may require OCR fallback (~200ms slower)

## 🛠️ Building from Source

See [BUILD.md](https://github.com/waywardgeek/cardsense/blob/main/BUILD.md) for instructions.

## 📝 License

MIT License - free for personal and commercial use.

## 🙏 Credits

- **Bill Cox** - Creator, primary user, tester
- **CodeRhapsody** - AI development assistant
- **Scryfall** - Card database API
- **Pete** - Testing and feedback (also low-vision MTGA player)

## 🔗 Links

- **Repository**: https://github.com/waywardgeek/cardsense
- **Issues**: https://github.com/waywardgeek/cardsense/issues
- **Scryfall API**: https://scryfall.com/docs/api

---

**Accessibility note**: This tool was built by someone with visual impairment for people with visual impairment. If you have suggestions for improvements, please open an issue!
