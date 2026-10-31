"""GOES-19 Southeast GeoColor loop limited to the most recent 2 hours."""
import datetime as dt
import io
import re

from PIL import Image

from .common import get, now_utc

BASE = "https://cdn.star.nesdis.noaa.gov/GOES19/ABI/SECTOR/se/GEOCOLOR/"
PAT = re.compile(r'href="((\d{4})(\d{3})(\d{2})(\d{2})_GOES19-ABI-se-GEOCOLOR-600x600\.jpg)"')
HOURS = 2


def build(out):
    html = get(BASE).text
    frames = []
    for m in PAT.finditer(html):
        name, y, j, hh, mm = m.groups()
        t = dt.datetime(int(y), 1, 1, int(hh), int(mm), tzinfo=dt.timezone.utc) + dt.timedelta(days=int(j) - 1)
        frames.append((t, name))
    frames = sorted(set(frames))
    if not frames:
        raise RuntimeError("no GOES frames listed")
    newest = frames[-1][0]
    if now_utc() - newest > dt.timedelta(hours=1):
        raise RuntimeError(f"newest GOES frame is stale ({newest:%H%MZ})")
    keep = [f for f in frames if f[0] >= newest - dt.timedelta(hours=HOURS)]
    imgs = []
    for _, name in keep:
        im = Image.open(io.BytesIO(get(BASE + name).content)).convert("RGB")
        imgs.append(im.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    durations = [180] * (len(imgs) - 1) + [1500]
    imgs[0].save(out / "goes19_se_2h.gif", save_all=True, append_images=imgs[1:],
                 duration=durations, loop=0, optimize=True)
    return f"{len(imgs)} frames {keep[0][0]:%H%M}-{newest:%H%M}Z"
