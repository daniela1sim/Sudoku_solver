"""Experimental printed-digit recognition using normalized glyph templates.

Scores measure visual similarity, not calibrated probabilities. Every result
requires human review; Sudoku constraints are never used to invent clues.
"""

import base64
from functools import lru_cache
from io import BytesIO
import warnings

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16_000_000


def _dependencies():
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError as exc:
        raise ValueError('Image import needs optional packages. Run: python -m pip install ".[vision]"') from exc
    return cv2, np, Image, ImageDraw, ImageFont, ImageOps


def _normalize(mask):
    cv2, np, *_ = _dependencies()
    points = cv2.findNonZero(mask)
    if points is None:
        return np.zeros((40, 32), dtype=np.float32)
    x, y, w, h = cv2.boundingRect(points)
    scale = min(26 / w, 34 / h)
    w2, h2 = max(1, round(w * scale)), max(1, round(h * scale))
    glyph = cv2.resize(mask[y:y+h, x:x+w], (w2, h2), interpolation=cv2.INTER_AREA)
    result = np.zeros((40, 32), dtype=np.float32)
    top, left = (40-h2)//2, (32-w2)//2
    result[top:top+h2, left:left+w2] = glyph / 255
    return result


@lru_cache(maxsize=1)
def _templates():
    cv2, np, Image, ImageDraw, ImageFont, _ = _dependencies()
    templates = []
    fonts = ["arial.ttf", "arialbd.ttf", "times.ttf", "timesbd.ttf", "calibri.ttf",
             "DejaVuSans.ttf", "DejaVuSerif.ttf", "LiberationSans-Regular.ttf"]
    for digit in range(1, 10):
        for face in [cv2.FONT_HERSHEY_SIMPLEX, cv2.FONT_HERSHEY_DUPLEX,
                     cv2.FONT_HERSHEY_COMPLEX, cv2.FONT_HERSHEY_TRIPLEX]:
            for thickness in [1, 2, 3]:
                mask = np.zeros((80, 80), dtype=np.uint8)
                cv2.putText(mask, str(digit), (15, 60), face, 1.8, 255, thickness, cv2.LINE_AA)
                templates.append((digit, _normalize(mask)))
        for name in fonts:
            try:
                font = ImageFont.truetype(name, 52)
            except OSError:
                continue
            mask = Image.new("L", (90, 90))
            ImageDraw.Draw(mask).text((15, 5), str(digit), font=font, fill=255)
            templates.append((digit, _normalize(np.array(mask))))
    return templates


def _recognize(mask):
    cv2, np, *_ = _dependencies()
    glyph = _normalize(mask)
    scores = {}
    for digit, template in _templates():
        # Soft intersection-over-union penalizes both missing and extra ink.
        score = float(np.minimum(glyph, template).sum() / np.maximum(glyph, template).sum())
        scores[digit] = max(scores.get(digit, 0), score)
    ranked = sorted(scores, key=scores.get, reverse=True)
    best, second = ranked[:2]
    return best, scores[best], scores[best] - scores[second]


def _is_border_fragment(stat, shape):
    """Ignore narrow line remnants along a cell crop's perimeter.

    Perspective interpolation and double grid borders can leave a few pixels
    inside the crop. Normalizing these slivers would turn them into digit 1.
    Keep narrow central strokes and substantial edge components: those may be
    real digits, including clipped clues that need review.
    """
    x, y, width, height, _ = stat
    rows, cols = shape
    edge = max(2, round(min(shape) * .05))
    vertical = width <= edge and (x <= edge or x + width >= cols - edge)
    horizontal = height <= edge and (y <= edge or y + height >= rows - edge)
    return vertical or horizontal


def _warp(gray):
    cv2, np, *_ = _dependencies()
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 31, 9)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:30]:
        if cv2.contourArea(contour) < gray.size * .1:
            continue
        quad = cv2.approxPolyDP(contour, .02 * cv2.arcLength(contour, True), True)
        if len(quad) != 4 or not cv2.isContourConvex(quad):
            continue
        pts = quad.reshape(4, 2).astype(np.float32)
        sums, diffs = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
        ordered = np.array([pts[sums.argmin()], pts[diffs.argmin()],
                            pts[sums.argmax()], pts[diffs.argmax()]], dtype=np.float32)
        if len(np.unique(ordered, axis=0)) != 4:
            continue
        transform = cv2.getPerspectiveTransform(ordered, np.float32([[0, 0], [719, 0], [719, 719], [0, 719]]))
        warped = cv2.warpPerspective(gray, transform, (720, 720), borderValue=255)
        ink = cv2.adaptiveThreshold(warped, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 31, 9)
        # Require internal grid lines in both directions, not merely a rectangle.
        projections = [np.mean(ink > 0, axis=axis) for axis in [0, 1]]
        if all(sum(float(p[n*80-7:n*80+8].max()) > .55 for n in range(1, 9)) >= 7
               for p in projections):
            return warped, ink
    raise ValueError("Could not find a complete 9 by 9 grid. Crop around one upright puzzle with all borders visible.")


def read_image(data: bytes) -> dict:
    """Read PNG/JPEG/WebP bytes into an editable puzzle and review metadata."""
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise ValueError("Choose an image smaller than 8 MiB")
    cv2, np, Image, _, _, ImageOps = _dependencies()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Choose a PNG, JPEG, or WebP image")
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError("Image must be at most 16 megapixels")
                source = ImageOps.exif_transpose(source)
                rgba = source.convert("RGBA")
                background = Image.new("RGBA", rgba.size, "white")
                background.alpha_composite(rgba)
                gray = np.array(background.convert("L"))
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Cannot decode this image. Choose a smaller PNG, JPEG, or WebP file.") from exc
    if min(gray.shape) < 180:
        raise ValueError("Image is too small. Use a grid at least 180 pixels wide and tall.")
    if max(gray.shape) > 1800:
        scale = 1800 / max(gray.shape)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    warped, ink = _warp(gray)
    digits, cells = [], []
    for row in range(9):
        for col in range(9):
            crop = ink[row*80+9:(row+1)*80-9, col*80+9:(col+1)*80-9]
            count, labels, stats, _ = cv2.connectedComponentsWithStats(crop)
            components = [i for i in range(1, count)
                          if stats[i, cv2.CC_STAT_AREA] >= 16
                          and not _is_border_fragment(stats[i], crop.shape)]
            digit, score, review = 0, None, False
            if components:
                largest = max(components, key=lambda i: stats[i, cv2.CC_STAT_AREA])
                mask = np.uint8(labels == largest) * 255
                digit, score, margin = _recognize(mask)
                review = score < .65 or margin < .08 or len(components) > 1
                if score < .40 or stats[largest, cv2.CC_STAT_HEIGHT] < 19:
                    digit, review = 0, True
            digits.append(str(digit))
            cells.append({"row": row, "col": col, "digit": digit,
                          "score": round(score, 3) if score is not None else None, "review": review})
    # Mark all direct conflicts without silently changing recognized clues.
    units = [[r*9+c for c in range(9)] for r in range(9)]
    units += [[r*9+c for r in range(9)] for c in range(9)]
    units += [[(br+r)*9+bc+c for r in range(3) for c in range(3)]
              for br in [0, 3, 6] for bc in [0, 3, 6]]
    conflicts = set()
    for unit in units:
        for i in unit:
            if digits[i] != '0' and sum(digits[j] == digits[i] for j in unit) > 1:
                conflicts.add(i)
                cells[i]["review"] = True
    _, png = cv2.imencode(".png", warped)
    return {"puzzle": "".join(digits), "cells": cells, "conflicts": sorted(conflicts),
            "preview": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
            "warning": "Experimental recognition: compare every clue with the image before starting. Highlighted cells need extra attention."}
