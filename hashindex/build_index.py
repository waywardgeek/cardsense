#!/usr/bin/env python3
"""
build_index.py — download Scryfall bulk card data + images, compute a
perceptual hash for every card, and store a hash -> card lookup table.

Usage:
    python3 build_index.py --bulk-type default_cards --limit 200   # smoke test
    python3 build_index.py --bulk-type default_cards                # full build

Outputs (in ./data/):
    bulk_data.json      raw Scryfall bulk cards JSON (cached, not re-downloaded if present)
    images/<id>.jpg      downloaded card images (normal size)
    index.sqlite         hash -> scryfall_id + oracle data table

Design note: we hash the *full card frame* (normal-size PNG/JPG from Scryfall),
not just the art crop, because the frame (border, set symbol, template)
disambiguates alternate printings/foils that share art or name. See
../design.md for rationale.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from io import BytesIO

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
BULK_JSON_PATH = os.path.join(DATA_DIR, "bulk_data.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
DB_PATH = os.path.join(DATA_DIR, "index.sqlite")

SCRYFALL_BULK_META_URL = "https://api.scryfall.com/bulk-data"
USER_AGENT = "cardsense/0.1 (+https://github.com/bill/cardsense; accessibility tool for MTGA)"


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_bulk_data(bulk_type: str, force: bool):
    if os.path.exists(BULK_JSON_PATH) and not force:
        print(f"[bulk] using cached {BULK_JSON_PATH}")
        with open(BULK_JSON_PATH, "r") as f:
            return json.load(f)

    print("[bulk] fetching bulk-data manifest from Scryfall...")
    meta = fetch_json(SCRYFALL_BULK_META_URL)
    entries = meta["data"]
    match = next((e for e in entries if e["type"] == bulk_type), None)
    if match is None:
        available = [e["type"] for e in entries]
        raise SystemExit(f"bulk type {bulk_type!r} not found. Available: {available}")

    download_uri = match["download_uri"]
    print(f"[bulk] downloading {bulk_type} from {download_uri} ({match.get('size', '?')} bytes)...")
    req = urllib.request.Request(download_uri, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = resp.read()

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(BULK_JSON_PATH, "wb") as f:
        f.write(raw)

    cards = json.loads(raw.decode("utf-8"))
    print(f"[bulk] downloaded {len(cards)} card entries")
    return cards


def init_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            scryfall_id TEXT PRIMARY KEY,
            name TEXT,
            mana_cost TEXT,
            type_line TEXT,
            oracle_text TEXT,
            power TEXT,
            toughness TEXT,
            set_code TEXT,
            collector_number TEXT,
            phash TEXT,
            ahash TEXT,
            dhash TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_phash ON cards(phash)")
    conn.commit()
    return conn


def image_url_for(card, size="normal"):
    """Return best-effort image URL for a card, handling multi-face cards."""
    if "image_uris" in card:
        return card["image_uris"].get(size)
    faces = card.get("card_faces")
    if faces and "image_uris" in faces[0]:
        return faces[0]["image_uris"].get(size)
    return None


def oracle_text_for(card):
    """Concatenate oracle text across faces for double-faced cards."""
    if "oracle_text" in card and card["oracle_text"]:
        return card["oracle_text"]
    faces = card.get("card_faces")
    if faces:
        return "\n---\n".join(f.get("oracle_text", "") for f in faces)
    return ""


def download_image(url, dest_path, retries=5):
    if os.path.exists(dest_path):
        return True
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(dest_path, "wb") as f:
                f.write(data)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"  [warn] Rate limited (429) on attempt {attempt+1}. Sleeping 5s...")
                time.sleep(5)
            else:
                print(f"  [warn] HTTP error {e.code} on attempt {attempt+1}: {e}")
                time.sleep(1)
        except Exception as e:
            print(f"  [warn] download failed (attempt {attempt+1}/{retries}): {e}")
            time.sleep(1)
    return False



def get_existing_ids(conn):
    cur = conn.cursor()
    cur.execute("SELECT scryfall_id FROM cards")
    return set(row[0] for row in cur.fetchall())


def process_card(card, existing_ids):
    cid = card["id"]
    if cid in existing_ids:
        return ('existing', cid, None, None)
        
    url = image_url_for(card)
    if not url:
        return ('no_image', cid, None, None)

    dest = os.path.join(IMAGES_DIR, f"{cid}.jpg")
    
    ok = download_image(url, dest)
    if not ok:
        return ('download_fail', cid, None, None)

    try:
        from PIL import Image
        import imagehash
        img = Image.open(dest).convert("RGB")
        phash = str(imagehash.phash(img, hash_size=16))
        ahash = str(imagehash.average_hash(img))
        dhash = str(imagehash.dhash(img))
        return ('success', cid, card, (phash, ahash, dhash))
    except Exception as e:
        print(f"  [warn] hash failed for {cid} ({card.get('name')}): {e}")
        if os.path.exists(dest):
            os.remove(dest)
        return ('hash_fail', cid, None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bulk-type", default="default_cards",
                     help="Scryfall bulk data type: default_cards, unique_artwork, oracle_cards, all_cards")
    ap.add_argument("--limit", type=int, default=None, help="only process first N cards (smoke test)")
    ap.add_argument("--force-download", action="store_true", help="re-download bulk JSON even if cached")
    ap.add_argument("--workers", type=int, default=10, help="number of parallel download workers")
    args = ap.parse_args()

    cards = download_bulk_data(args.bulk_type, args.force_download)

    if args.limit:
        cards = cards[: args.limit]

    os.makedirs(IMAGES_DIR, exist_ok=True)
    conn = init_db(DB_PATH)
    cur = conn.cursor()
    
    existing_ids = get_existing_ids(conn)
    print(f"[bulk] Found {len(existing_ids)} cards already in index. Skipping them.")

    processed = 0
    skipped_no_image = 0
    skipped_download_fail = 0
    skipped_hash_fail = 0
    skipped_existing = 0

    from concurrent.futures import ThreadPoolExecutor, as_completed

    print(f"[bulk] Starting processing with {args.workers} workers...")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_card, c, existing_ids): c for c in cards}
        
        for i, future in enumerate(as_completed(futures)):
            status, cid, card, hashes = future.result()
            
            if status == 'existing':
                skipped_existing += 1
            elif status == 'no_image':
                skipped_no_image += 1
            elif status == 'download_fail':
                skipped_download_fail += 1
            elif status == 'hash_fail':
                skipped_hash_fail += 1
            elif status == 'success':
                phash, ahash, dhash = hashes
                cur.execute("""
                    INSERT OR REPLACE INTO cards
                    (scryfall_id, name, mana_cost, type_line, oracle_text, power, toughness,
                     set_code, collector_number, phash, ahash, dhash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cid, card.get("name"), card.get("mana_cost"), card.get("type_line"),
                    oracle_text_for(card), card.get("power"), card.get("toughness"),
                    card.get("set"), card.get("collector_number"), phash, ahash, dhash,
                ))
                processed += 1

            if (i + 1) % 50 == 0:
                conn.commit()
                print(f"[{i+1}/{len(cards)}] processed={processed} existing={skipped_existing} "
                      f"no_image={skipped_no_image} dl_fail={skipped_download_fail} hash_fail={skipped_hash_fail}")

    conn.commit()
    conn.close()
    print(f"\nDone. processed={processed} existing={skipped_existing} no_image={skipped_no_image} "
          f"dl_fail={skipped_download_fail} hash_fail={skipped_hash_fail}")
    print(f"Index written to {DB_PATH}")


if __name__ == "__main__":
    main()
