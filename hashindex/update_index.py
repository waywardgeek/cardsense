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
from multiprocessing import Pool, cpu_count

import numpy as np
import cv2
import requests

from phash import dual_phash, DATA_DIR


BULK_LIST_ENDPOINT = "https://api.scryfall.com/bulk-data"
GITHUB_RELEASE_API = "https://api.github.com/repos/waywardgeek/cardsense/releases/latest"
METADATA_FILE = os.path.join(DATA_DIR, "scryfall_metadata.json")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 cardsense/1.0"


def download_from_github_release():
    """Try to download pre-built hash files from latest GitHub release.
    
    Returns True if successful, False if no release or download failed.
    Much faster than rebuilding from Scryfall (~10s vs 10-20 min).
    """
    try:
        print("Checking for pre-built hash files on GitHub releases...", flush=True)
        resp = requests.get(GITHUB_RELEASE_API, headers={"User-Agent": USER_AGENT}, timeout=10)
        if resp.status_code == 404:
            print("  No GitHub releases found, will rebuild from Scryfall", flush=True)
            return False
        resp.raise_for_status()
        release = resp.json()
        
        # Find the hash file assets
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
        if "phash_index.npz" not in assets or "phash_meta.json" not in assets:
            print("  Release missing hash files, will rebuild from Scryfall", flush=True)
            return False
        
        print(f"  Found release {release['tag_name']}: {release['name']}", flush=True)
        
        # Download hash files
        for filename, url in assets.items():
            if filename not in ("phash_index.npz", "phash_meta.json"):
                continue
            
            dest = os.path.join(DATA_DIR, filename)
            print(f"  Downloading {filename}...", flush=True)
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
            resp.raise_for_status()
            
            with open(dest, "wb") as f:
                f.write(resp.content)
            
            size_mb = len(resp.content) / (1024 * 1024)
            print(f"    ✅ {filename} ({size_mb:.1f} MB)", flush=True)
        
        print("✅ Downloaded pre-built hash files from GitHub", flush=True)
        return True
        
    except Exception as e:
        print(f"  GitHub download failed: {e}, will rebuild from Scryfall", flush=True)
        return False


def fetch_bulk_metadata():
    """Fetch the bulk data list and find the 'unique_artwork' entry.
    
    We use unique_artwork instead of default_cards because:
    - Includes all printings with different artwork (what we need for visual matching)
    - Smaller download (253MB vs 532MB)
    - Covers MTGA's full card pool including modern reprints
    """
    print("Fetching Scryfall bulk data list...", flush=True)
    resp = requests.get(BULK_LIST_ENDPOINT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    bulk_list = resp.json()
    
    # Find the unique_artwork entry
    for entry in bulk_list.get("data", []):
        if entry.get("type") == "unique_artwork":
            return entry
    
    raise RuntimeError("Could not find 'unique_artwork' in Scryfall bulk data list")


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


def _download_and_hash_card(args):
    """Download and hash a single card. For use with multiprocessing.Pool."""
    card, temp_dir = args
    
    card_id = card.get("id")
    if not card_id:
        return None, "no_id"
    
    # Get image URL
    image_uris = card.get("image_uris", {})
    if not image_uris:
        faces = card.get("card_faces", [])
        if faces and faces[0].get("image_uris"):
            image_uris = faces[0]["image_uris"]
    
    img_url = image_uris.get("normal") or image_uris.get("large")
    if not img_url:
        return None, "missing_img"
    
    # Download image
    temp_path = os.path.join(temp_dir, f"{card_id}.jpg")
    try:
        resp = requests.get(img_url, headers={"User-Agent": USER_AGENT}, timeout=10)
        resp.raise_for_status()
        with open(temp_path, 'wb') as f:
            f.write(resp.content)
    except Exception as e:
        return None, "download_fail"
    
    # Hash image
    try:
        gray = cv2.imread(temp_path, cv2.IMREAD_GRAYSCALE)
        if gray is None:
            return None, "hash_fail"
        
        bits = dual_phash(gray)
        card_meta = {
            "id": card_id,
            "name": card.get("name"),
            "type_line": card.get("type_line"),
            "mana_cost": card.get("mana_cost"),
            "oracle_text": card.get("oracle_text")
        }
        
        return (bits, card_id, card_meta), "ok"
    except Exception as e:
        return None, "hash_fail"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def download_and_hash(cards, verbose=True, parallel=True):
    """Download card images on-the-fly, hash them, return (bits, ids, meta).
    
    Args:
        parallel: Use multiprocessing for parallel downloads (default: True)
    """
    temp_dir = os.path.join(DATA_DIR, "temp_images")
    os.makedirs(temp_dir, exist_ok=True)
    
    t0 = time.time()
    
    if parallel:
        # Parallel processing with real-time progress
        n_workers = min(cpu_count(), 8)  # Cap at 8 to avoid overwhelming Scryfall
        print(f"  Using {n_workers} parallel workers", flush=True)
        
        with Pool(n_workers) as pool:
            args = [(card, temp_dir) for card in cards]
            # Use imap_unordered for real-time progress (yields results as they complete)
            results_iter = pool.imap_unordered(_download_and_hash_card, args, chunksize=10)
            
            # Collect results with progress reporting
            results = []
            for i, (result, status) in enumerate(results_iter, 1):
                results.append((result, status))
                
                # Progress update every 100 cards
                if i % 100 == 0:
                    elapsed = time.time() - t0
                    rate = i / elapsed
                    eta = (len(cards) - i) / rate if rate > 0 else 0
                    pct = i / len(cards) * 100
                    print(f"  {i}/{len(cards)} ({pct:.1f}%) — {elapsed:.0f}s elapsed, {rate:.1f}/s, ETA {eta:.0f}s", flush=True)
    else:
        # Serial processing (old path)
        results = [_download_and_hash_card((card, temp_dir)) for card in cards]
    
    # Collect results
    bits_list, ids, meta = [], [], []
    n_ok = n_missing_img = n_download_fail = n_hash_fail = 0
    
    for i, (result, status) in enumerate(results):
        if verbose and i % 1000 == 0 and i > 0:
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (len(results) - i) / rate if rate > 0 else 0
            print(f"  {i}/{len(results)} processed ({elapsed:.0f}s, {rate:.1f}/s, ETA {eta:.0f}s) "
                  f"ok={n_ok} missing={n_missing_img} fail={n_download_fail+n_hash_fail}",
                  flush=True)
        
        if result:
            bits, card_id, card_meta = result
            bits_list.append(bits)
            ids.append(card_id)
            meta.append(card_meta)
            n_ok += 1
        else:
            if status == "missing_img":
                n_missing_img += 1
            elif status == "download_fail":
                n_download_fail += 1
            elif status == "hash_fail":
                n_hash_fail += 1
    
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


def update_index(force=False, parallel=True):
    """Main update workflow with incremental updates.
    
    Args:
        force: Force full rebuild even if current
        parallel: Use parallel downloads (default: True, ~8x faster)
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Check if update needed
    need_update, reason = needs_update(force)
    if not need_update:
        print(f"Index {reason}, skipping update", flush=True)
        return True
    
    print(f"Update needed: {reason}", flush=True)
    
    # Try fast path: download from GitHub release (unless --force)
    if not force and download_from_github_release():
        # Cache metadata to avoid re-downloading
        bulk_meta = fetch_bulk_metadata()
        with open(METADATA_FILE, "w") as f:
            json.dump(bulk_meta, f)
        return True
    
    # Paths
    index_path = os.path.join(DATA_DIR, "phash_index.npz")
    meta_path = os.path.join(DATA_DIR, "phash_meta.json")
    
    # Load existing index if available (for incremental update)
    existing_ids = set()
    existing_bits = None
    existing_ids_array = None
    existing_meta = []
    
    if os.path.exists(index_path) and os.path.exists(meta_path) and not force:
        try:
            print("Loading existing index for incremental update...", flush=True)
            with np.load(index_path) as data:
                existing_bits = data['bits']
                existing_ids_array = data['ids']
                existing_ids = set(existing_ids_array)
            with open(meta_path) as f:
                existing_meta = json.load(f)
            print(f"  Found {len(existing_ids)} existing cards", flush=True)
        except Exception as e:
            print(f"  Failed to load existing index: {e}, doing full rebuild", flush=True)
            existing_ids = set()
            existing_bits = None
    
    # Fetch bulk metadata and download
    bulk_meta = fetch_bulk_metadata()
    download_url = bulk_meta["download_uri"]
    updated_at = bulk_meta["updated_at"]
    
    if force:
        print("\nForce rebuild requested, processing all cards...", flush=True)
    elif existing_ids:
        print(f"\nIncremental update from Scryfall (only new/changed cards)...", flush=True)
    else:
        print(f"\nFull rebuild from Scryfall bulk data...", flush=True)
    
    print(f"Downloading bulk data from {download_url}", flush=True)
    print(f"  Updated: {updated_at}", flush=True)
    print(f"  Size: {bulk_meta.get('size', 0) / (1024*1024):.1f} MB", flush=True)
    
    # Download bulk JSON
    resp = requests.get(download_url, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    all_cards = resp.json()
    
    print(f"Loaded {len(all_cards)} card records from Scryfall", flush=True)
    
    # Filter to only new cards if doing incremental update
    if existing_ids and not force:
        new_cards = [c for c in all_cards if c.get("id") not in existing_ids]
        print(f"  {len(new_cards)} new cards to process (skipping {len(all_cards) - len(new_cards)} existing)", flush=True)
        cards_to_process = new_cards
    else:
        cards_to_process = all_cards
    
    # If no new cards, we're done
    if len(cards_to_process) == 0:
        print("✅ No new cards to process", flush=True)
        # Still update metadata timestamp
        with open(METADATA_FILE, "w") as f:
            json.dump(bulk_meta, f)
        return True
    
    # Download images on-the-fly and hash (with parallel downloads)
    new_bits, new_ids, new_meta = download_and_hash(cards_to_process, parallel=parallel)
    
    if len(new_bits) == 0:
        print("ERROR: No cards successfully hashed", flush=True)
        return False
    
    # Merge with existing index if doing incremental update
    if existing_bits is not None and not force:
        print(f"Merging {len(new_bits)} new cards with {len(existing_bits)} existing...", flush=True)
        final_bits = np.vstack([existing_bits, new_bits])
        final_ids = np.concatenate([existing_ids_array, new_ids])
        final_meta = existing_meta + new_meta
    else:
        final_bits = new_bits
        final_ids = new_ids
        final_meta = new_meta
    
    # Save merged index
    print(f"Saving index with {len(final_bits)} total cards...", flush=True)
    np.savez(index_path, bits=final_bits, ids=final_ids)
    with open(meta_path, "w") as f:
        json.dump(final_meta, f)
    
    # Cache bulk metadata for future checks
    with open(METADATA_FILE, "w") as f:
        json.dump(bulk_meta, f)
    
    if existing_bits is not None and not force:
        print(f"✅ Incremental update complete: added {len(new_bits)} cards, total now {len(final_bits)} cards", flush=True)
    else:
        print(f"✅ Index built: {len(final_bits)} cards in phash_index.npz ({final_bits.nbytes / (1024*1024):.1f} MB)", flush=True)
    return True


def main():
    ap = argparse.ArgumentParser(description="Update cardsense pHash index from Scryfall")
    ap.add_argument("--force", action="store_true", help="Force update even if current")
    ap.add_argument("--check-only", action="store_true", help="Only check if update needed")
    ap.add_argument("--no-parallel", action="store_true", help="Disable parallel downloads (slower but easier to debug)")
    args = ap.parse_args()
    
    if args.check_only:
        need_update, reason = needs_update(args.force)
        print(f"Update {'needed' if need_update else 'not needed'}: {reason}", flush=True)
        sys.exit(0 if not need_update else 1)
    
    success = update_index(args.force, parallel=not args.no_parallel)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
