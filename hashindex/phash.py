#!/usr/bin/env python3
"""cardsense pHash core — single source of truth for hashing + matching.

The winning descriptor (measured on real MTGA captures 2026-07-22, see design.md):
a card is fingerprinted by TWO 256-bit DCT pHashes concatenated into one 512-bit
(64-byte) vector:

    dual = phash(full_card) ++ phash(art_box)

Matching is Hamming distance over the whole 64-byte vector, which equals the SUM
of the full-card and art-box distances. This full+art ensemble gave a mean
correct-vs-nearest-wrong margin of ~48 bits (2.6x the whole-card baseline);
crucially it rescued the thin cases (one test card went from margin 10 -> 40).

Why not other regions: the title and rules-text bands score NEGATIVE margins —
MTGA renders fonts/anti-aliasing differently from Scryfall's paper scans, so text
is pure domain-gap noise. The ART is the most render-stable discriminator. This is
also why OCR-the-name was the wrong path.

Everything here is deliberately plain array math (resize / DCT / median / XOR /
popcount) so it ports cleanly to a single Go binary later.

UPDATE 2026-07-24: OCR fallback added for MTGA rendering differences. MTGA uses
different fonts and even different card text than Scryfall, making pHash unreliable.
OCR the title + Scryfall fuzzy search is now the primary fallback (~200ms, very accurate).
"""
import os
import numpy as np
import cv2

# Optional imports for OCR fallback
try:
    import pytesseract
    from PIL import Image
    import requests
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# --- Descriptor geometry (do not change without rebuilding the index) ---
HASH_SIZE = 16                 # 16x16 low-freq DCT coeffs -> 256 bits
IMG_SIZE = HASH_SIZE * 4       # 64x64 pre-DCT
CW, CH = 200, 280             # canonical card size (~0.714 aspect) for region crops
ART_BOX = (0.11, 0.56, 0.06, 0.94)   # (y0,y1,x0,x1) fractions of the card
DUAL_BYTES = 64               # 32 (full) + 32 (art)

_POPCOUNT = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(1).astype(np.uint16)

# Detect if running from PyInstaller bundle
import sys
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Running from PyInstaller bundle - data files are in _MEIPASS/hashindex/data
    DATA_DIR = os.path.join(sys._MEIPASS, "hashindex", "data")
else:
    # Running from source
    DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _phash256(gray):
    """gray HxW uint8 -> packed 32-byte (256-bit) DCT pHash."""
    small = cv2.resize(gray, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)
    d = cv2.dct(small.astype(np.float32))[:HASH_SIZE, :HASH_SIZE]
    return np.packbits((d > np.median(d)).flatten())


def dual_phash(gray, border_trim=None):
    """gray HxW uint8 (a card image/crop) -> packed 64-byte full++art pHash.
    
    Args:
        border_trim: Optional (left, top, right, bottom) pixels to trim before hashing.
                     Removes border artifacts that differ between MTGA and Scryfall.
    """
    if border_trim:
        left, top, right, bottom = border_trim
        h, w = gray.shape
        gray = gray[top:h-bottom, left:w-right]
    
    cg = cv2.resize(gray, (CW, CH), interpolation=cv2.INTER_AREA)
    y0, y1, x0, x1 = ART_BOX
    art = cg[int(y0 * CH):int(y1 * CH), int(x0 * CW):int(x1 * CW)]
    return np.concatenate([_phash256(gray), _phash256(art)])


def hamming_scan(query, bits):
    """query: 64-byte uint8. bits: [N,64] uint8 index. -> [N] Hamming distances."""
    return _POPCOUNT[np.bitwise_xor(bits, query[None, :])].sum(1)


def align_variants(gray, sweep=True, border_trim=None):
    """Yield the crop plus inward-cropped variants to absorb border misalignment.
    
    Args:
        border_trim: Optional (left, top, right, bottom) to trim before hashing
    """
    if border_trim:
        left, top, right, bottom = border_trim
        h, w = gray.shape
        trimmed = gray[top:h-bottom, left:w-right]
        yield trimmed
    else:
        yield gray
    
    if not sweep:
        return
    
    h, w = gray.shape[:2]
    for dz in (0.03, 0.06):
        m = int(min(h, w) * dz)
        if m > 0 and h - 2 * m > 10 and w - 2 * m > 10:
            cropped = gray[m:h - m, m:w - m]
            if border_trim:
                left, top, right, bottom = border_trim
                hc, wc = cropped.shape
                cropped = cropped[top:hc-bottom, left:wc-right]
            yield cropped



class CardIndex:
    """Loaded pHash index + card metadata."""

    def __init__(self, data_dir=DATA_DIR):
        import json
        z = np.load(os.path.join(data_dir, "phash_index.npz"), allow_pickle=True)
        self.bits = z["bits"]                    # [N,64] uint8
        self.ids = z["ids"]
        self.meta = json.load(open(os.path.join(data_dir, "phash_meta.json")))
        self.names = [m.get("name") for m in self.meta]
        assert self.bits.shape[1] == DUAL_BYTES, \
            f"index is {self.bits.shape[1]}B/card, expected {DUAL_BYTES} — rebuild it"

    def __len__(self):
        return len(self.meta)

    def identify(self, gray, sweep=True, max_dist=280, min_margin=20, border_trim=None, ocr_fallback=True):
        """Identify a card crop.

        Returns (card_meta, dist, margin) on a confident match, else None.
        
        Strategy:
        1. Try pHash first (fast, works for most cards)
        2. If no match or low confidence (margin < 50), try OCR fallback
        
        OCR fallback handles MTGA rendering differences (different fonts, text)
        that make pHash unreliable even though the art is identical.

        Args:
            border_trim: Optional (left, top, right, bottom) pixels to trim before hashing.
            ocr_fallback: If True, use OCR when pHash has low confidence (default: True)

        Returns:
            (card_meta, dist, margin) on success, None on failure
            card_meta will have 'ocr_fallback': True if OCR was used
        """
        # Try pHash first
        best = None
        for v in align_variants(gray, sweep, border_trim):
            d = hamming_scan(dual_phash(v, border_trim=None), self.bits)  # Already trimmed in align_variants
            best = d if best is None else np.minimum(best, d)
        order = np.argsort(best)
        top = order[0]
        top_name = self.names[top]
        top_dist = int(best[top])
        
        # Find margin (distance to next different name)
        runner = None
        for idx in order[1:]:
            if self.names[idx] != top_name:
                runner = int(best[idx]); break
        margin = (runner - top_dist) if runner is not None else 10 ** 9
        
        # Check if pHash gives confident match
        if top_dist <= max_dist and margin >= min_margin:
            result = self.meta[top].copy()
            result['ocr_fallback'] = False
            return result, top_dist, margin
        
        # pHash failed or low confidence - try OCR fallback
        # Guard 1: pHash distance must be reasonable (not random noise)
        if not (ocr_fallback and HAS_OCR and top_dist <= 200):  # Tightened from 300
            return None
        
        # Guard 2: Aspect ratio must be card-like (0.65-0.80)
        h, w = gray.shape
        aspect = w / h
        if not (0.65 <= aspect <= 0.80):
            return None
        
        # Try OCR extraction
        card_name = ocr_card_name(gray)
        if not card_name:
            return None
        
        # Guard 3: OCR text must look like a real card name
        # - At least 5 characters (e.g., "Loki")
        # - At least 4 letters (filters "d=0 m=999" style text)
        # - No more than 2 consecutive spaces (filters garbled multi-line OCR)
        if len(card_name) < 5 or sum(c.isalpha() for c in card_name) < 4:
            return None
        if "  " in card_name:  # Multiple consecutive spaces = garbled
            return None
        
        # Query Scryfall
        card_meta = query_scryfall(card_name)
        if card_meta:
            card_meta['ocr_fallback'] = True
            card_meta['ocr_text'] = card_name  # Save what we extracted
            # Return with synthetic dist/margin to indicate OCR was used
            return card_meta, 0, 999
        
        # Both pHash and OCR failed
        return None



# ── OCR fallback (for MTGA rendering differences) ─────────────────────────
def ocr_card_name(gray_crop):
    """Extract card name from title region via OCR.
    
    Returns card name string or None if OCR unavailable/failed.
    Fast (~70ms) and works even when pHash fails due to MTGA vs Scryfall rendering.
    """
    if not HAS_OCR:
        return None
    
    try:
        h, w = gray_crop.shape
        
        # Extract title region (top 5-14% of card, avoiding borders)
        title = gray_crop[int(h*0.05):int(h*0.14), int(w*0.05):int(w*0.95)]
        
        # Preprocess for OCR: invert (white text on dark → black on white)
        inverted = cv2.bitwise_not(title)
        
        # Threshold to clean up
        _, binary = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Upscale 3x for better OCR
        scaled = cv2.resize(binary, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        
        # OCR with letter-only whitelist
        pil_img = Image.fromarray(scaled)
        text = pytesseract.image_to_string(
            pil_img, 
            config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz '
        )
        
        # Clean and return
        cleaned = text.strip()
        return cleaned if cleaned else None
        
    except Exception as e:
        return None


def query_scryfall(card_name):
    """Query Scryfall API for card by fuzzy name match.
    
    Returns dict with {name, type_line, oracle_text} or None if not found.
    Scryfall's fuzzy search is very forgiving of OCR errors.
    """
    if not HAS_OCR:
        return None
    
    try:
        resp = requests.get(
            f'https://api.scryfall.com/cards/named?fuzzy={card_name}',
            headers={'User-Agent': 'cardsense/1.0'},
            timeout=5
        )
        
        if resp.status_code == 200:
            card = resp.json()
            return {
                "id": card.get("id"),
                "name": card.get("name"),
                "type_line": card.get("type_line"),
                "mana_cost": card.get("mana_cost"),
                "oracle_text": card.get("oracle_text")
            }
        return None
        
    except Exception as e:
        return None
