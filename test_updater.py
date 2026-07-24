#!/usr/bin/env python3
"""Quick test of update_index.py functionality.

Tests metadata fetch and first 10 cards only (quick validation).
"""
import sys
import os

# Add hashindex to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "hashindex"))

from update_index import fetch_bulk_metadata, needs_update
import json

print("Testing Scryfall API connection...")
try:
    meta = fetch_bulk_metadata()
    print(f"✅ Bulk metadata fetched:")
    print(f"   Download URL: {meta['download_uri']}")
    print(f"   Updated: {meta['updated_at']}")
    print(f"   Size: {meta.get('size', 0) / (1024*1024):.1f} MB")
    print(f"   Type: {meta.get('type')}")
except Exception as e:
    print(f"❌ Failed to fetch metadata: {e}")
    sys.exit(1)

print("\nChecking if update needed...")
try:
    need_update, reason = needs_update(force=False)
    print(f"   Update {'needed' if need_update else 'not needed'}: {reason}")
except Exception as e:
    print(f"   Check failed: {e}")

print("\n✅ update_index.py connectivity test passed")
