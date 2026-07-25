#!/usr/bin/env python3
"""Build cardsense installers with bundled hash index.

Usage:
    python build.py            # Build for current platform
    python build.py --clean    # Clean build artifacts first
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.absolute()
HASH_DIR = ROOT / 'hashindex' / 'data'
DIST_DIR = ROOT / 'dist'
BUILD_DIR = ROOT / 'build'

def clean():
    """Remove build artifacts."""
    print("🧹 Cleaning build artifacts...")
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"   Removed {d}")

def check_hash_files():
    """Verify hash files exist, download if missing."""
    required = [
        HASH_DIR / 'phash_index.npz',
        HASH_DIR / 'phash_meta.json',
    ]
    
    missing = [f for f in required if not f.exists()]
    
    if missing:
        print("⚠️  Hash files missing, downloading...")
        print(f"   Missing: {[f.name for f in missing]}")
        
        # Run update_index.py to download
        update_script = ROOT / 'hashindex' / 'update_index.py'
        result = subprocess.run(
            [sys.executable, str(update_script)],
            cwd=ROOT,
        )
        if result.returncode != 0:
            print("❌ Failed to download hash files")
            return False
        
        # Verify they exist now
        missing = [f for f in required if not f.exists()]
        if missing:
            print(f"❌ Still missing: {[f.name for f in missing]}")
            return False
    
    total_size = sum(f.stat().st_size for f in required)
    print(f"✅ Hash files ready ({total_size / 1024 / 1024:.1f} MB)")
    return True

def build():
    """Run PyInstaller build."""
    print(f"\n🔨 Building for {platform.system()}...")
    
    spec_file = ROOT / 'cardsense.spec'
    if not spec_file.exists():
        print(f"❌ {spec_file} not found")
        return False
    
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', str(spec_file)],
        cwd=ROOT,
    )
    
    if result.returncode != 0:
        print("❌ Build failed")
        return False
    
    print("✅ Build successful")
    
    # Show output location
    if platform.system() == 'Darwin':
        app = DIST_DIR / 'cardsense.app'
        if app.exists():
            size = sum(
                f.stat().st_size 
                for f in app.rglob('*') if f.is_file()
            )
            print(f"\n📦 macOS app: {app} ({size / 1024 / 1024:.1f} MB)")
            print(f"   Test: open {app}")
    else:
        exe_dir = DIST_DIR / 'cardsense'
        if exe_dir.exists():
            size = sum(
                f.stat().st_size 
                for f in exe_dir.rglob('*') if f.is_file()
            )
            print(f"\n📦 Windows exe: {exe_dir} ({size / 1024 / 1024:.1f} MB)")
            print(f"   Test: {exe_dir / 'cardsense.exe'}")
    
    return True

def main():
    parser = argparse.ArgumentParser(description='Build cardsense installers')
    parser.add_argument('--clean', action='store_true', help='Clean before building')
    args = parser.parse_args()
    
    print("🚀 CardSense Installer Build")
    print(f"   Platform: {platform.system()}")
    
    if args.clean:
        clean()
    
    if not check_hash_files():
        return 1
    
    if not build():
        return 1
    
    print("\n✨ Done!")
    return 0

if __name__ == '__main__':
    sys.exit(main())
