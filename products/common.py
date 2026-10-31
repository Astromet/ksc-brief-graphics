"""Shared helpers for the KSC briefing graphics builders."""
import datetime as dt
import io
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
UA = {"User-Agent": "KSC-briefing-graphics (github.com/Astromet/ksc-brief-graphics)"}

FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation"]


def font(size, bold=False):
    names = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
             "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"]
    for d in FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


def get(url, tries=3, timeout=60, **kw):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=timeout, **kw)
            if r.status_code == 200:
                return r
            last = RuntimeError(f"HTTP {r.status_code} for {url}")
            if r.status_code == 404:
                break
        except requests.RequestException as e:
            last = e
        time.sleep(3 * (i + 1))
    raise last


def get_image(url):
    return Image.open(io.BytesIO(get(url).content))


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def now_local():
    """Eastern time (KSC)."""
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo("America/New_York"))


def now_label(draw, x, y_bottom, text="NOW", color=(224, 0, 0), size=22, pad=6, box=True):
    """Boxed label centered on x, sitting with its bottom edge at y_bottom."""
    f = font(size, bold=True)
    l, t, r, b = draw.textbbox((0, 0), text, font=f)
    w, h = r - l, b - t
    x0, y0 = x - w / 2 - pad, y_bottom - h - 2 * pad
    if box:
        draw.rectangle([x0, y0, x0 + w + 2 * pad, y_bottom], fill="white", outline=color, width=2)
    draw.text((x0 + pad - l, y0 + pad - t), text, font=f, fill=color)


def save_png(img, path):
    img.save(path, optimize=True)
