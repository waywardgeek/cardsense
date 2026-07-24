#!/usr/bin/env python3
"""Auto-update the cardsense pHash index from Scryfall.

Fetches the latest Scryfall bulk data, downloads card images on-the-fly,
computes dual pHash for each, and writes phash_index.npz + phash_meta.json.
Images are deleted after hashing to save disk space.

Usage:
    python3 update_index.py [--force]      # --force re-downloads even if up-to-date
    python3 update_index.py --check-only   # just check if update available
"""
import argparse
import json
import os
import sys
import time
from urllib.request import urlopen, urlretrieve
from urllib.error import HTTPError

import numpy as np
import cv2

from phash import dual_phash, DATA_DIR


BULK_ENDPOINT = "https://api.scryfall.com/bulk-data/default-cards"
METADATA_FILE = os.path.join(DATA_DIR, "scryfall_metadata.json")


def fetch_bulk_metadata():
    """Fetch the bulk data endpoint to get download URL and updated_at timestamp."""
    print("Fetching Scryfall bulk metadata...", flush=True)
    with urlopen(BULK_ENDPOINT) as resp:
        return json.loads(resp.read())


def needs_update(force=False):
    """Check if index needs updating (new Scryfall data or missing index files)."""
    if force:
        return True, "forced update"
    
    # Check if index files exist
    index_path = os.path.join(DATA_DIR, "phash_index.npz")
    meta_path = os.path.join(DATA_DIR, "phash_meta.json")
    if not os.path.exists(index_path) or not os.path.exists(meta_path):
        return True, "index files missing"
    
    # Check if we have cached metadata
    if not os.path.exists(METADATA_FILE):
        return True, "no cached metadata"
    
    # Compare timestamps
    with open(METADATA_FILE) as f:
        cached = json.load(f)
    
    current = fetch_bulk_metadata()
    
    if current["updated_at"] != cached.get("updated_at"):
        return True, f"new data available (cached: {cached.get('updated_at')}, current: {current['updated_at']})"
    
    return False, "index up-to-date"


def download_and_hash(cards, verbose=True):
    """Download card images on-the-fly, hash them, return (bits, ids, meta)."""
    bits_list, ids, meta = [], [], []
    n_ok = n_missing_img = n_download_fail = n_hash_fail = 0
    
    temp_dir = os.path.join(DATA_DIR, "temp_images")
    os.makedirs(temp_dir, exist_ok=True)
    
    t0 = time.time()
    
    for i, card in enumerate(cards):
        if verbose and i % 1000 == 0 and i > 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (len(cards) - i) / rate if rate > 0 else 0
            print(f"  {i}/{len(cards)} hashed ({elapsed:.0f}s, {rate:.1f}/s, ETA {eta:.0f}s) "
                  f"ok={n_ok} missing={n_missing_img} fail={n_download_fail+n_hash_fail}",
                  flush=True)
        
        card_id = card.get("id")
        if not card_id:
            continue
        
        # Get image URL - prefer 'normal' size
        image_uris = card.get("image_uris", {})
        if not image_uris:
            # Check card_faces for double-faced cards
            faces = card.get("card_faces", [])
            if faces and faces[0].get("image_uris"):
                image_uris = faces[0]["image_uris"]
        
        img_url = image_uris.get("normal") or image_uris.get("large")
        if not img_url:
            n_missing_img += 1
            continue
        
        # Download image to temp file
        temp_path = os.path.join(temp_dir, f"{card_id}.jpg")
        try:
            urlretrieve(img_url, temp_path)
        except (HTTPError, Exception) as e:
            n_download_fail += 1
            if verbose and n_download_fail <= 5:
                print(f"    Download failed for {card.get('name')}: {e}", flush=True)
            continue
        
        # Read and hash
        try:
            gray = cv2.imread(temp_path, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                n_hash_fail += 1
                continue
            
            bits_list.append(dual_phash(gray))
            ids.append(card_id)
            meta.append({
                "id": card_id,
                "name": card.get("name"),
                "type_line": card.get("type_line"),
                "mana_cost": card.get("mana_cost"),
                "oracle_text": card.get("oracle_text")
            })
            n_ok += 1
        except Exception as e:
            n_hash_fail += 1
            if verbose and n_hash_fail <= 5:
                print(f"    Hash failed for {card.get('name')}: {e}", flush=True)
        finally:
            # Delete temp image immediately
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    # Clean up temp directory
    try:
        os.rmdir(temp_dir)
    except:
        pass
    
    elapsed = time.time() - t0
    print(f"\nDONE: ok={n_ok} missing_img={n_missing_img} download_fail={n_download_fail} "
          f"hash_fail={n_hash_fail} in {elapsed:.0f}s", flush=True)
    
    bits = np.array(bits_list, dtype=np.uint8)
    return bits, np.array(ids), meta


def update_index(force=False):
    """Main update workflow."""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Check if update needed
    need_update, reason = needs_update(force)
    if not need_update:
        print(f"Index {reason}, skipping update", flush=True)
        return True
    
    print(f"Update needed: {reason}", flush=True)
    
    # Fetch bulk metadata
    bulk_meta = fetch_bulk_metadata()
    download_url = bulk_meta["download_uri"]
    updated_at = bulk_meta["updated_at"]
    
    print(f"Downloading bulk data from {download_url}", flush=True)
    print(f"  Updated: {updated_at}", flush=True)
    print(f"  Size: {bulk_meta.get('size', 0) / (1024*1024):.1f} MB", flush=True)
    
    # Download bulk JSON
    with urlopen(download_url) as resp:
        cards = json.loads(resp.read())
    
    print(f"Loaded {len(cards)} card records", flush=True)
    
    # Download images on-the-fly and hash
    bits, ids, meta = download_and_hash(cards)
    
    if len(bits) == 0:
        print("ERROR: No cards successfully hashed", flush=True)
        return False
    
    # Save index files
    index_path = os.path.join(DATA_DIR, "phash_index.npz")
    meta_path = os.path.join(DATA_DIR, "phash_meta.json")
    
    print(f"Saving index with {len(bits)} cards...", flush=True)
    np.savez(index_path, bits=bits, ids=ids)
    with open(meta_path, "w") as f:
        json.dump(meta, f)
    
    # Cache bulk metadata for future checks
    with open(METADATA_FILE, "w") as f:
        json.dump(bulk_meta, f)
    
    print(f"✅ Index updated: {len(bits)} cards in phash_index.npz ({bits.nbytes / (1024*1024):.1f} MB)", flush=True)
    return True


def main():
    ap = argparse.ArgumentParser(description="Update cardsense pHash index from Scryfall")
    ap.add_argument("--force", action="store_true", help="Force update even if current")
    ap.add_argument("--check-only", action="store_true", help="Only check if update needed")
    args = ap.parse_args()
    
    if args.check_only:
        need_update, reason = needs_update(args.force)
        print(f"Update {'needed' if need_update else 'not needed'}: {reason}", flush=True)
        sys.exit(0 if not need_update else 1)
    
    success = update_index(args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
