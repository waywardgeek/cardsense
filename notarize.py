#!/usr/bin/env python3
"""Notarize cardsense.app for distribution outside the Mac App Store.

This script:
1. Builds and signs the .app with Developer ID
2. Creates a ZIP for notarization
3. Submits to Apple for notarization
4. Waits for approval
5. Staples the notarization ticket
6. Creates a DMG for distribution

Requirements:
- Active Apple Developer account
- Developer ID Application certificate in Keychain
- App-specific password stored in Keychain (see README)
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.absolute()
DIST_DIR = ROOT / 'dist'
APP_PATH = DIST_DIR / 'cardsense.app'
ZIP_PATH = DIST_DIR / 'cardsense.zip'
DMG_PATH = DIST_DIR / 'cardsense.dmg'

# Use venv Python if available
VENV_PYTHON = ROOT / 'venv' / 'bin' / 'python3'
if VENV_PYTHON.exists():
    PYTHON = str(VENV_PYTHON)
else:
    PYTHON = sys.executable

# Apple Developer info
APPLE_ID = "waywardgeek@gmail.com"  # Your Apple ID
TEAM_ID = "B2SUY7SU9A"  # From your Developer ID certificate
KEYCHAIN_PROFILE = "CardSense"  # Keychain profile name (stored via notarytool store-credentials)

def run(cmd, check=True):
    """Run command and return output."""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result

def build_app():
    """Build signed .app with PyInstaller."""
    print("\n🔨 Building signed .app...")
    result = run([PYTHON, 'build.py', '--clean'])
    if not APP_PATH.exists():
        print(f"❌ Build failed: {APP_PATH} not found")
        sys.exit(1)
    print(f"✅ Built: {APP_PATH}")

def create_zip():
    """Create ZIP for notarization."""
    print("\n📦 Creating ZIP for notarization...")
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    
    run(['ditto', '-c', '-k', '--keepParent', str(APP_PATH), str(ZIP_PATH)])
    print(f"✅ Created: {ZIP_PATH} ({ZIP_PATH.stat().st_size / 1024 / 1024:.1f} MB)")

def submit_for_notarization():
    """Submit ZIP to Apple for notarization."""
    print("\n📤 Submitting to Apple for notarization...")
    print("   This may take 5-15 minutes...")
    
    result = run([
        'xcrun', 'notarytool', 'submit', str(ZIP_PATH),
        '--keychain-profile', KEYCHAIN_PROFILE,
        '--wait',
        '--output-format', 'json',
    ])
    
    data = json.loads(result.stdout)
    
    if data.get('status') == 'Accepted':
        print(f"✅ Notarization successful!")
        print(f"   Submission ID: {data.get('id')}")
        return data.get('id')
    else:
        print(f"❌ Notarization failed: {data.get('status')}")
        print(f"   Check logs with: xcrun notarytool log {data.get('id')} --keychain-profile {KEYCHAIN_PROFILE}")
        sys.exit(1)

def staple_ticket():
    """Staple notarization ticket to .app."""
    print("\n📎 Stapling notarization ticket...")
    run(['xcrun', 'stapler', 'staple', str(APP_PATH)])
    
    # Verify stapling
    result = run(['xcrun', 'stapler', 'validate', str(APP_PATH)])
    if 'The validate action worked!' in result.stdout:
        print("✅ Stapling verified")
    else:
        print("⚠️  Stapling validation unclear")

def create_dmg():
    """Create DMG for distribution."""
    print("\n💿 Creating DMG...")
    if DMG_PATH.exists():
        DMG_PATH.unlink()
    
    run([
        'hdiutil', 'create',
        '-volname', 'CardSense',
        '-srcfolder', str(APP_PATH),
        '-ov',
        '-format', 'UDZO',
        str(DMG_PATH)
    ])
    
    print(f"✅ Created: {DMG_PATH} ({DMG_PATH.stat().st_size / 1024 / 1024:.1f} MB)")

def verify_prerequisites():
    """Check that prerequisites are met."""
    print("🔍 Checking prerequisites...")
    print(f"   Using Python: {PYTHON}")
    
    # Check for Developer ID certificate
    result = run([
        'security', 'find-identity', '-v', '-p', 'codesigning'
    ], check=False)
    
    if 'Developer ID Application: Bill Cox' not in result.stdout:
        print("❌ Developer ID Application certificate not found")
        print("   Install it from developer.apple.com")
        sys.exit(1)
    print("✅ Developer ID certificate found")
    
    # Check for app-specific password
    print("\n⚠️  App-specific password required:")
    print("   1. Go to appleid.apple.com")
    print("   2. Sign in → Security → App-Specific Passwords → Generate")
    print("   3. Store in Keychain:")
    print(f"      xcrun notarytool store-credentials CardSense \\")
    print(f"        --apple-id {APPLE_ID} \\")
    print(f"        --team-id {TEAM_ID}")
    print("   (You only need to do this once)")

def main():
    parser = argparse.ArgumentParser(description='Build and notarize cardsense')
    parser.add_argument('--skip-build', action='store_true', help='Skip build step')
    parser.add_argument('--verify-only', action='store_true', help='Only verify prerequisites')
    args = parser.parse_args()
    
    verify_prerequisites()
    
    if args.verify_only:
        return
    
    if not args.skip_build:
        build_app()
    
    create_zip()
    submission_id = submit_for_notarization()
    staple_ticket()
    create_dmg()
    
    print("\n✨ Done! Distribution files:")
    print(f"   Signed .app: {APP_PATH}")
    print(f"   DMG: {DMG_PATH}")
    print(f"\n📤 Ready to distribute:")
    print(f"   - Upload {DMG_PATH} to GitHub releases")
    print(f"   - Users can download and drag to Applications")
    print(f"   - No Gatekeeper warnings (app is notarized)")

if __name__ == '__main__':
    os.chdir(ROOT)
    main()
