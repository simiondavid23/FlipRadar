"""Helper-e GENERICE de hashing imagine + potrivire de pret, partajate intre detectoarele
de duplicate (Imobiliare Monitor + Auto Anunturi). Extrase din
services/real_estate/duplicate_detector.py — logica IDENTICA, doar mutata intr-un loc comun.
Nimic specific unui domeniu aici (fara zona/camere/suprafata sau make/model).
"""
from typing import Optional


# ── Image hashing ──────────────────────────────────────────────

def compute_phash(image_url: str) -> Optional[str]:
    try:
        import imagehash
        from PIL import Image
        import requests as req
        resp = req.get(image_url, timeout=8, stream=True)
        if resp.status_code != 200:
            return None
        from io import BytesIO
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        h = imagehash.phash(img)
        return str(h)
    except Exception:
        return None


def compute_color_hist(image_url: str) -> Optional[list]:
    try:
        from PIL import Image
        import requests as req
        from io import BytesIO
        resp = req.get(image_url, timeout=8, stream=True)
        if resp.status_code != 200:
            return None
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        img_small = img.resize((64, 64))
        hist = img_small.histogram()
        total = sum(hist) or 1
        return [v / total for v in hist]
    except Exception:
        return None


def phash_distance(h1: str, h2: str) -> int:
    try:
        import imagehash
        return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)
    except Exception:
        return 64  # max distance if error


def hist_similarity(h1: list, h2: list) -> float:
    if not h1 or not h2 or len(h1) != len(h2):
        return 0.0
    try:
        dot = sum(a * b for a, b in zip(h1, h2))
        mag1 = sum(a * a for a in h1) ** 0.5
        mag2 = sum(b * b for b in h2) ** 0.5
        if mag1 * mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)
    except Exception:
        return 0.0


# ── Price matching helper ──────────────────────────────────────

def _prices_close(p1: float, p2: float, tolerance: float = 0.03) -> bool:
    if not p1 or not p2:
        return False
    return abs(p1 - p2) / max(p1, p2) <= tolerance
