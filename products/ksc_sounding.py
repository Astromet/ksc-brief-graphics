"""Latest KXMR (Cape Canaveral) rawinsonde plot from the NWS Spaceflight Meteorology
Group, plus its precipitable water read off the plot's bottom stats row (the 'PW'
column, in mm) and converted to inches."""
import io
import json

from PIL import Image

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
    return note
