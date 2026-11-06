"""Latest KXMR (Cape Canaveral) rawinsonde plot from the NWS Spaceflight Meteorology
Group, plus its precipitable water read off the plot's bottom stats row (the 'PW'
column, in mm) and converted to inches."""
import datetime as dt
import io
import json
import math

from PIL import Image, ImageDraw

from .common import get, now_utc

URL = "https://www.weather.gov/images/smg/KSCSNDG.GIF"
OUT_IMG = "ksc_sounding.png"
OUT_JSON = "ksc_sounding.json"

# McIDAS 7x9 digit glyphs used on the plot ('#' = black pixel)
GLYPHS = {
    "0": "..###../.#...#./#.....#/#.....#/#.....#/#.....#/#.....#/.#...#./..###..",
    "1": "..#./.##./#.#./..#./..#./..#./..#./..#./####",
    "2": "..###../.#...#./#.....#/......#/.....#./...##../..#..../.#...../#######",
    "3": "..###../.#...#./#.....#/.....#./...##../.....#./#.....#/.#...#./..###..",
    "4": "...#..#/..#...#/..#...#/.#....#/#######/......#/......#/......#/......#",
    "5": "#######/#....../#....../#####../.....#./......#/#.....#/.#...#./..###..",
    "6": "..###../.#...#./#.....#/#....../#####../#....#./#.....#/.#...#./..###..",
    "7": "#######/......#/.....#./.....#./.....#./....#../....#../...#.../...#...",
    "8": "..###../.#...#./#.....#/.#...#./..###../.#...#./#.....#/.#...#./..###..",
    "9": "..###../.#...#./#.....#/.#....#/..#####/......#/......#/.....#./..###..",
}


def _pad(rows, w=7):
    return [r.ljust(w, ".")[:w] for r in rows]


def _match(rows):
    """Best digit for a glyph bitmap (exact match, else closest within 4 pixels)."""
    if len(rows) != 9:
        return "?"
    key = "/".join(rows)
    for d, g in GLYPHS.items():
        if g == key:
            return d
    best, score = "?", 5
    for d, g in GLYPHS.items():
        a, b = _pad(g.split("/")), _pad(rows)
        diff = sum(x != y for ra, rb in zip(a, b) for x, y in zip(ra, rb))
        if diff < score:
            best, score = d, diff
    return best


def read_pw_mm(im):
    """Return PW (mm) from the last token of the black stats row under the plot."""
    im = im.convert("RGB")
    W, H = im.size
    px = im.load()
    xmax = int(W * 0.82)  # stats columns end left of the big 'KSC' label
    dark = lambda i, j: sum(px[i, j]) < 300  # noqa: E731  (black text; grey labels are lighter)
    counts = [sum(dark(i, j) for i in range(xmax)) for j in range(H)]
    # the values row: a 9-pixel band of dense black text in the bottom quarter
    band = None
    j = int(H * 0.75)
    while j < H:
        if counts[j] >= 15:
            k = j
            while k + 1 < H and counts[k + 1] >= 15:
                k += 1
            if k - j + 1 == 9:
                band = (j, k)
            j = k + 1
        else:
            j += 1
    if not band:
        raise RuntimeError("stats row not found")
    y0, y1 = band
    cols = [any(dark(i, j) for j in range(y0, y1 + 1)) for i in range(xmax)]
    glyphs, i = [], 0
    while i < xmax:
        if cols[i]:
            s = i
            while i < xmax and cols[i]:
                i += 1
            rows = ["".join("#" if dark(x, j) else "." for x in range(s, i)) for j in range(y0, y1 + 1)]
            glyphs.append((s, i, _match(rows)))
        else:
            i += 1
    tokens = []
    for s, e, ch in glyphs:
        if tokens and s - tokens[-1][1] <= 4:
            tokens[-1] = (tokens[-1][0], e, tokens[-1][2] + ch)
        else:
            tokens.append((s, e, ch))
    if not tokens:
        raise RuntimeError("no values in stats row")
    pw = tokens[-1][2]
    if not pw.isdigit() or not 3 <= int(pw) <= 90:
        raise RuntimeError(f"PW value unreadable: {pw!r} (row: {' '.join(t[2] for t in tokens)})")
    return int(pw), " ".join(t[2] for t in tokens)


def build(out):
    data = get(URL).content
    im = Image.open(io.BytesIO(data))
    im.seek(0)
    im = im.convert("RGB")
    im.save(out / OUT_IMG, optimize=True)
    result = {"updated": f"{now_utc():%Y-%m-%d %H:%MZ}"}
    try:
        mm, row = read_pw_mm(im)
        result.update({"pw_mm": mm, "pw_in": round(mm / 25.4, 2), "row": row})
        note = f"PW {mm} mm = {mm / 25.4:.2f} in (row: {row})"
    except Exception as e:  # noqa: BLE001
        note = f"image saved; PW not read ({e})"
    (out / OUT_JSON).write_text(json.dumps(result, indent=1))
    try:
        star = star_chart(out)
        note += f"; climo chart {star}"
    except Exception as e:  # noqa: BLE001
        note += f"; climo star failed ({e})"
    return note


def _star(cx, cy, r_out, r_in):
    pts = []
    for k in range(10):
        r = r_out if k % 2 == 0 else r_in
        a = math.radians(-90 + 36 * k)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def star_chart(out):
    """Redraw snd_pw_climo.png from its clean copy with a yellow star at today's date
    and the latest KXMR precipitable water (inches)."""
    base = out / "snd_pw_climo_base.png"
    if not base.exists():
        return "no base chart"
    im = Image.open(base).convert("RGB")
    note = "no star (PW missing)"
    try:
        geo = json.loads((out / "snd_pw_climo_geo.json").read_text())
        snd = json.loads((out / OUT_JSON).read_text())
        upd = dt.datetime.strptime(snd["updated"], "%Y-%m-%d %H:%MZ").replace(tzinfo=dt.timezone.utc)
        fresh = now_utc() - upd < dt.timedelta(hours=3)
        if "pw_in" in snd and fresh:
            pw = min(float(snd["pw_in"]), geo["ymax"])
            x, y = geo["x"], geo["y0"] - pw * geo["px_per_in"]
            r = geo["dot_d"] * 0.85  # outer radius; star spans ~1.7x a dot's width
            sc = 4  # draw large and shrink for smooth edges
            big = im.resize((im.width * sc, im.height * sc), Image.LANCZOS)
            d = ImageDraw.Draw(big)
            d.polygon(_star(x * sc, y * sc, r * sc, r * sc * 0.45), fill=(255, 221, 0),
                      outline=(60, 60, 60), width=max(2, round(sc * geo["dot_d"] / 14)))
            im = big.resize(im.size, Image.LANCZOS)
            note = f"star at {pw:.2f} in"
    except Exception as e:  # noqa: BLE001
        note = f"no star ({type(e).__name__}: {e})"
    im.save(out / "snd_pw_climo.png", optimize=True)
    return note
