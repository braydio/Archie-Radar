from __future__ import annotations

import json
import math
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

from PIL import Image, ImageOps, ImageStat


@dataclass(frozen=True)
class ImageFingerprint:
    dhash: str
    color_histogram: list[float]

    def histogram_json(self) -> str:
        return json.dumps(self.color_histogram, separators=(",", ":"))


def _normalized_rgb(data: bytes) -> Image.Image:
    opened = Image.open(BytesIO(data))
    return ImageOps.exif_transpose(opened).convert("RGB")


def looks_like_placeholder_image(data: bytes) -> bool:
    """Conservatively detect low-information placeholder artwork.

    Lost-pet sites sometimes put the same generic "no photo" artwork on every card.
    Fingerprinting that artwork makes unrelated animals look like reposts. We only
    call an image a placeholder when it is extremely low-information, so a real
    photo with a plain wall/background still has plenty of texture to pass.
    """
    with Image.open(BytesIO(data)) as opened:
        rgb = ImageOps.exif_transpose(opened).convert("RGB")
        if rgb.width < 48 or rgb.height < 48:
            return True
        small = rgb.resize((64, 64), Image.Resampling.BILINEAR)
        gray = small.convert("L")
        hist = gray.histogram()
        total = float(sum(hist)) or 1.0
        entropy = -sum((n / total) * math.log2(n / total) for n in hist if n)
        # Quantize to 5 bits/channel. Real photographs typically occupy far more
        # than a handful of these coarse colors, even when mostly gray.
        coarse_colors = {
            (r // 32, g // 32, b // 32)
            for r, g, b in small.getdata()
        }
        stddev = ImageStat.Stat(gray).stddev[0]
        return entropy < 2.0 and len(coarse_colors) <= 12 and stddev < 70


def fingerprint_image(data: bytes) -> ImageFingerprint:
    """Create a tiny, model-free image fingerprint.

    dHash is useful for recognizing reused/near-identical photos. The coarse RGB
    histogram makes the comparison a little less brittle to resizing/compression.
    This is a triage heuristic, not facial recognition and not an identity probability.
    """
    with Image.open(BytesIO(data)) as opened:
        rgb = ImageOps.exif_transpose(opened).convert("RGB")

        # 64-bit difference hash.
        gray = rgb.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())
        bits = 0
        for y in range(8):
            row = y * 9
            for x in range(8):
                bits = (bits << 1) | int(pixels[row + x] > pixels[row + x + 1])
        dhash = f"{bits:016x}"

        # 4x4x4 = 64 bin normalized RGB histogram.
        small = rgb.resize((64, 64), Image.Resampling.BILINEAR)
        bins = [0] * 64
        for r, g, b in small.getdata():
            idx = (r // 64) * 16 + (g // 64) * 4 + (b // 64)
            bins[idx] += 1
        total = float(sum(bins)) or 1.0
        hist = [v / total for v in bins]

    return ImageFingerprint(dhash=dhash, color_histogram=hist)


def parse_histogram(value: str | list[float]) -> list[float]:
    if isinstance(value, list):
        return [float(v) for v in value]
    try:
        parsed = json.loads(value)
        return [float(v) for v in parsed]
    except Exception:
        return []


def _hash_similarity(a: str, b: str) -> float:
    try:
        xor = int(a, 16) ^ int(b, 16)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, 1.0 - (xor.bit_count() / 64.0))


def _histogram_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    aa = list(a)
    bb = list(b)
    if len(aa) != len(bb) or not aa:
        return 0.0
    return max(0.0, min(1.0, sum(math.sqrt(max(0.0, x) * max(0.0, y)) for x, y in zip(aa, bb))))


def compare_fingerprints(
    hash_a: str,
    histogram_a: str | list[float],
    hash_b: str,
    histogram_b: str | list[float],
) -> float:
    """Return 0..1 likeness for image triage.

    The weighting deliberately favors dHash, making this strongest at detecting
    reused/near-identical photos rather than claiming two different photos show
    the same individual cat.
    """
    h = _hash_similarity(hash_a, hash_b)
    c = _histogram_similarity(parse_histogram(histogram_a), parse_histogram(histogram_b))
    return max(0.0, min(1.0, 0.78 * h + 0.22 * c))
