# CardSense

**An accessibility tool for low-vision Magic: The Gathering Arena players.**

CardSense uses screen capture and perceptual hashing to identify MTGA cards and read them aloud via text-to-speech at 550 WPM, making the game accessible for players with visual impairments.

Built by Bill Cox (20/180 vision, macular dystrophy) for himself and Pete, with assistance from CodeRhapsody AI.

## Quick Start (macOS)

### Download & Install

1. **Download the latest release**: [cardsense.dmg](https://github.com/waywardgeek/cardsense/releases/latest)
2. **Double-click** the DMG to mount it
3. **Drag** CardSense.app to your Applications folder
4. **Launch** CardSense from Applications
5. **Grant screen recording permission** when prompted (System Settings → Privacy & Security → Screen Recording)
6. **Click Start** and right-click a card in MTGA!

**No Gatekeeper warnings** - the app is notarized by Apple.

### First Launch

When you first launch CardSense:
1. macOS will ask for **screen recording permission** - click "Open System Settings"
2. Toggle **CardSense** ON in the Screen Recording list
3. **Restart CardSense** (quit and relaunch)
4. Click **Start** to begin card detection
5. Launch MTGA and right-click on any card to hear it read aloud

## Features

✅ **Real-time card identification** - Hover over a card in MTGA → hear it spoken instantly  
✅ **Fast text-to-speech** - 550 WPM (adjustable 200-750) using macOS voices  
✅ **Dual pHash + OCR** - Perceptual hashing for speed, OCR fallback for accuracy  
✅ **Auto-calibration** - Detects your screen layout automatically  
✅ **Offline-ready** - 53K+ card database bundled (no download after install)  
✅ **Zero configuration** - Just drag to Applications and launch

## Usage

1. Launch **MTGA** and **CardSense**
2. Click **Start** in CardSense
3. Right-click (or hover) on any card in MTGA
4. CardSense identifies the card and speaks:
   - Card name
   - Type line (Creature - Human Wizard, etc.)
   - Mana cost
   - Oracle text

**Controls:**
- **Speed slider**: Adjust TTS speed (200-750 WPM)
- **Voice dropdown**: Choose TTS voice (Reed, Samantha, Alex, etc.)
- **Test button**: Verify TTS is working ("Llanowar Elves" test)
- **Start/Stop**: Enable/disable card detection

## Platforms

✅ **macOS 10.13+** (High Sierra and later) - fully supported, notarized  
🚧 **Windows** - infrastructure ready, testing needed  
🚧 **Linux** - planned

## System Requirements

- **macOS 10.13** (High Sierra) or later
- **Screen recording permission** (granted on first launch)
- **~420 MB** disk space (app + bundled card database)
- **MTGA** installed and running

## Troubleshooting

### "CardSense is not detecting cards"
1. Check that **screen recording permission** is granted (System Settings → Privacy & Security → Screen Recording)
2. **Restart CardSense** after granting permission
3. Ensure MTGA is in **windowed or fullscreen mode** (not minimized)
4. Try clicking **Stop** then **Start** again to reset detection

### "No audio when I right-click cards"
1. Click the **Test** button - you should hear "Llanowar Elves..."
2. If Test works but cards don't speak, check MTGA is in focus
3. Try adjusting the **Speed** slider (some voices fail at certain speeds)

### "Permission prompt appears every launch"
- This happens when the app is rebuilt/updated - grant permission once and it will stick

### "Cards are identified incorrectly"
- Some showcase/alternate art cards may trigger OCR fallback (~200ms slower)
- Report misidentifications as [GitHub issues](https://github.com/waywardgeek/cardsense/issues)

## Technical Details

- **Detection**: Dual perceptual hashing (full card + art box) + OCR fallback
- **Database**: 53,000+ Scryfall cards (auto-updates on launch)
- **TTS**: macOS NSSpeechSynthesizer (Reed voice default)
- **Frame rate**: 20 FPS analysis with motion gating
- **Languages**: Python 3.13+ (PyInstaller bundled)

## Building from Source

See [BUILD.md](BUILD.md) for developer instructions.

## Contributing

Issues and pull requests welcome! This tool was built by someone with visual impairment for people with visual impairment - suggestions for accessibility improvements are especially appreciated.

## Credits

- **Bill Cox** - Creator, primary user, tester
- **CodeRhapsody AI** - Development assistant
- **Scryfall** - Card database API
- **Pete** - Testing and feedback (also low-vision MTGA player)

## License

MIT License - free for personal and commercial use.

## Links

- **Latest Release**: https://github.com/waywardgeek/cardsense/releases/latest
- **Report Issues**: https://github.com/waywardgeek/cardsense/issues
- **Scryfall API**: https://scryfall.com/docs/api
