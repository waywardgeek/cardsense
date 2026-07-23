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
"""
import os
import numpy as np
import cv2

# --- Descriptor geometry (do not change without rebuilding the index) ---
HASH_SIZE = 16                 # 16x16 low-freq DCT coeffs -> 256 bits
IMG_SIZE = HASH_SIZE * 4       # 64x64 pre-DCT
CW, CH = 200, 280             # canonical card size (~0.714 aspect) for region crops
ART_BOX = (0.11, 0.56, 0.06, 0.94)   # (y0,y1,x0,x1) fractions of the card
DUAL_BYTES = 64               # 32 (full) + 32 (art)

_POPCOUNT = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(1).astype(np.uint16)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _phash256(gray):
    """gray HxW uint8 -> packed 32-byte (256-bit) DCT pHash."""
    small = cv2.resize(gray, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)
    d = cv2.dct(small.astype(np.float32))[:HASH_SIZE, :HASH_SIZE]
    return np.packbits((d > np.median(d)).flatten())


def dual_phash(gray):
    """gray HxW uint8 (a card image/crop) -> packed 64-byte full++art pHash."""
    cg = cv2.resize(gray, (CW, CH), interpolation=cv2.INTER_AREA)
    y0, y1, x0, x1 = ART_BOX
    art = cg[int(y0 * CH):int(y1 * CH), int(x0 * CW):int(x1 * CW)]
    return np.concatenate([_phash256(gray), _phash256(art)])


def hamming_scan(query, bits):
    """query: 64-byte uint8. bits: [N,64] uint8 index. -> [N] Hamming distances."""
    return _POPCOUNT[np.bitwise_xor(bits, query[None, :])].sum(1)


def align_variants(gray, sweep=True):
    """Yield the crop plus a couple of inward-cropped variants to absorb
    border/hover-glow misalignment. pHash is scale-normalized but sensitive to
    extra border pixels, so we take the best (min) distance over these."""
    yield gray
    if not sweep:
        return
    h, w = gray.shape[:2]
    for dz in (0.03, 0.06):
        m = int(min(h, w) * dz)
        if m > 0 and h - 2 * m > 10 and w - 2 * m > 10:
            yield gray[m:h - m, m:w - m]


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

    def identify(self, gray, sweep=True, max_dist=190, min_margin=20):
        """Identify a card crop.

        Returns (card_meta, dist, margin) on a confident match, else None.
        Confidence gate: best distance <= max_dist AND the runner-up with a
        DIFFERENT name is at least min_margin farther. Otherwise we stay silent
        (never guess) — the accessibility tool must not speak a wrong card.

        Defaults max_dist/min_margin are conservative starting points in the
        512-bit space; calibration tightens them per-display.
        """
        best = None
        for v in align_variants(gray, sweep):
            d = hamming_scan(dual_phash(v), self.bits)
            best = d if best is None else np.minimum(best, d)
        order = np.argsort(best)
        top = order[0]
        top_name = self.names[top]
        top_dist = int(best[top])
        # nearest entry with a different name
        runner = None
        for idx in order[1:]:
            if self.names[idx] != top_name:
                runner = int(best[idx]); break
        margin = (runner - top_dist) if runner is not None else 10 ** 9
        if top_dist <= max_dist and margin >= min_margin:
            return self.meta[top], top_dist, margin
        return None
