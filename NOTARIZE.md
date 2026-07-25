# Notarizing cardsense for macOS Distribution

This guide walks through notarizing cardsense for distribution **outside the Mac App Store**. Notarization tells macOS users that Apple has scanned your app for malware, preventing Gatekeeper warnings.

**Why not the Mac App Store?**  
CardSense needs screen recording permission, which Mac App Store sandboxing blocks. Direct distribution with notarization is the correct path for accessibility tools like this.

## Prerequisites

### 1. Apple Developer Account
✅ You have this! (Active as of 2026-07-25)

### 2. Developer ID Application Certificate
✅ Already installed in your Keychain:
```
Developer ID Application: Bill Cox (B2SUY7SU9A)
```

### 3. App-Specific Password (One-Time Setup)

Apple requires an app-specific password for notarization automation:

**Create the password:**
1. Go to [appleid.apple.com](https://appleid.apple.com)
2. Sign in → **Security** → **App-Specific Passwords**
3. Click **Generate** and name it "CardSense Notarization"
4. Copy the generated password (like `abcd-efgh-ijkl-mnop`)

**Store in Keychain:**
```bash
xcrun notarytool store-credentials AC_PASSWORD \
  --apple-id waywardgeek@gmail.com \
  --team-id B2SUY7SU9A
```

When prompted, paste the app-specific password. This saves it securely in your Keychain as `AC_PASSWORD`.

**You only do this once.** Future notarizations will use the saved password.

## Building & Notarizing

### Quick Path (Automated)
```bash
python notarize.py
```

This script:
1. ✅ Builds and signs cardsense.app
2. ✅ Creates a ZIP for Apple
3. ✅ Submits to Apple for notarization (~5-15 min)
4. ✅ Waits for approval
5. ✅ Staples the notarization ticket to the .app
6. ✅ Creates a DMG for distribution

### Manual Path (Step-by-Step)

**1. Build signed .app:**
```bash
python build.py --clean
```

**2. Create ZIP for notarization:**
```bash
cd dist
ditto -c -k --keepParent cardsense.app cardsense.zip
```

**3. Submit to Apple:**
```bash
xcrun notarytool submit cardsense.zip \
  --apple-id waywardgeek@gmail.com \
  --team-id B2SUY7SU9A \
  --password @keychain:AC_PASSWORD \
  --wait
```

**4. Staple the ticket:**
```bash
xcrun stapler staple cardsense.app
xcrun stapler validate cardsense.app
```

**5. Create DMG:**
```bash
hdiutil create -volname CardSense -srcfolder cardsense.app \
  -ov -format UDZO cardsense.dmg
```

## Verification

Test the notarized app on a **different Mac** (or after removing from quarantine):

```bash
# Download the DMG
# Mount it and drag cardsense.app to Applications
# Launch it

# Should show NO Gatekeeper warning
# Should request screen recording permission normally
```

## Distribution

Upload `dist/cardsense.dmg` to:
- **GitHub Releases** (recommended): Create a v0.2.0 release with the DMG attached
- Your website: Direct download link
- Google Drive / Dropbox: Share link

**Users will:**
1. Download cardsense.dmg
2. Double-click to mount
3. Drag CardSense.app to Applications
4. Launch (no warnings!)
5. Grant screen recording permission when prompted

## Troubleshooting

### "App-specific password not found"
```bash
# Re-run the credential storage:
xcrun notarytool store-credentials AC_PASSWORD \
  --apple-id waywardgeek@gmail.com \
  --team-id B2SUY7SU9A
```

### Notarization rejected
```bash
# Get the submission ID from the error message, then:
xcrun notarytool log <submission-id> \
  --apple-id waywardgeek@gmail.com \
  --team-id B2SUY7SU9A \
  --password @keychain:AC_PASSWORD
```

Common issues:
- Missing entitlements (already configured in entitlements.plist)
- Unsigned binaries (PyInstaller handles this)
- Hardened runtime issues (already configured)

### Users still see Gatekeeper warnings
- **Did you staple the ticket?** `xcrun stapler validate dist/cardsense.app` should say "The validate action worked!"
- **Did they download via Safari?** Safari sets quarantine bit differently than Chrome
- **Ask them to:** Right-click → Open (first launch only)

## Updating

When releasing a new version:
1. Update version in `cardsense.spec` (CFBundleShortVersionString)
2. Run `python notarize.py`
3. Upload new DMG to GitHub releases
4. Users download and replace the old .app

No re-notarization of old versions needed.

## Cost

- **Apple Developer Program**: $99/year (you already have this)
- **Notarization**: FREE (unlimited submissions)
- **Distribution**: FREE (no App Store fees)

Perfect for a free accessibility tool!

---

**Next steps after notarization:**
1. Create a GitHub release (v0.2.0)
2. Upload cardsense.dmg
3. Write release notes (mention accessibility focus, MTGA support, Bill + Pete use cases)
4. Share with low-vision gaming communities
