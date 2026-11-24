"""Latest KXMR (Cape Canaveral) rawinsonde plot from the NWS Spaceflight Meteorology
Group, plus its precipitable water read off the plot's bottom stats row (the 'PW'
column, in mm) and converted to inches."""
import datetime as dt
import io
import json
import math

from PIL import Image, ImageDraw

from .common import get, now_utc

# SMG posts three KXMR plots: the routine early-morning synoptic (~12Z), the routine
# afternoon one, and the latest mission-support balloon (which only changes on launch
# support days). The slide shows whichever was launched most recently.
SOURCES = {
    "Early AM synoptic": "https://www.weather.gov/images/smg/SNDG9AM.GIF",
    "Afternoon": "https://www.weather.gov/images/smg/SNDG21PM.GIF",
    "Mission support": "https://www.weather.gov/images/smg/KSCSNDG.GIF",
}
URL = SOURCES["Early AM synoptic"]
# nominal launch hour (UTC) of the routine plots, used when the title time can't be read
NOMINAL_HOUR = {"Early AM synoptic": 12, "Afternoon": 0}
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


# digits of the red stats row on the routine (SNDG9AM / SNDG21PM) plots
RED_GLYPHS = {
    "0": ".####./#....#/#....#/#....#/#....#/#....#/#....#/#....#/.####.",
    "1": "..#./###./..#./..#./..#./..#./..#./..#./####",
    "2": ".####./#....#/.....#/.....#/....#./...#../..#.../.#..../######",
    "3": ".####./#....#/.....#/.....#/...##./.....#/.....#/#....#/.####.",
    "4": "...#.#/..#..#/..#..#/.#...#/######/.....#/.....#/.....#/.....#",
    "5": "######/#...../#...../#####./.....#/.....#/.....#/#....#/.####.",
    "6": ".####./#....#/#...../#...../#####./#....#/#....#/#....#/.####.",
    "7": "######/.....#/.....#/....#./....#./....#./....#./...#../...#..",
    "8": ".####./#....#/#....#/#....#/.####./#....#/#....#/#....#/.####.",
    "9": ".####./#....#/#....#/#....#/.#####/.....#/.....#/.....#/.####.",
}
# digits of the red title line (HHMM UTC ...) on the routine plots
TITLE_GLYPHS = {
    "0": "..####../.#....#./#......#/#......#/#......#/#......#/#......#/#......#/#......#/.#....#./..####..",
    "1": ".#../##../##../.#../.#../.#../.#../.#../.#../.#../####",
    "2": "..####../.#....#./#......#/.......#/......#./.....#../....#.../...#..../..#...../.#....../########",
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


def obs_time(token, now):
    """Sounding time from the plot's GMT field (DDHHMM, e.g. 182240 = 18th 22:40Z), taken
    as the latest such time not in the future."""
    if not token.isdigit() or len(token) not in (5, 6):
        return None
    token = token.zfill(6)
    day, hh, mm = int(token[:2]), int(token[2:4]), int(token[4:])
    y, m = now.year, now.month
    for _ in range(3):
        try:
            t = dt.datetime(y, m, day, hh, mm, tzinfo=dt.timezone.utc)
            if t <= now + dt.timedelta(minutes=30):
                return t
        except ValueError:
            pass
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return None


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


def _red(c):
    return c[0] > 150 and c[1] < 90 and c[2] < 90


def _cells(im, pred, y0, y1, x0, x1):
    px = im.load()
    cols = [any(pred(px[i, j]) for j in range(y0, y1 + 1)) for i in range(x0, x1)]
    out, i = [], 0
    while i < len(cols):
        if cols[i]:
            s = i
            while i < len(cols) and cols[i]:
                i += 1
            rows = ["".join("#" if pred(px[x, j]) else "." for x in range(x0 + s, x0 + i)) for j in range(y0, y1 + 1)]
            out.append((x0 + s, x0 + i, rows))
        else:
            i += 1
    return out


def read_routine(im):
    """(PW mm, stats row, title HHMM or None) from a routine SMG plot (red stats row
    'KI LI SWI ... MIX PW CAPE HELI' under the diagram; PW in mm under the 'PW' label)."""
    im = im.convert("RGB")
    W, H = im.size
    px = im.load()
    counts = [sum(_red(px[i, j]) for i in range(W)) for j in range(H)]
    band, j = None, int(H * 0.8)
    while j < H:  # the stats row: the first 9-pixel band of red text below the diagram
        if counts[j]:
            k = j
            while k + 1 < H and counts[k + 1]:
                k += 1
            if k - j + 1 == 9:
                band = (j, k)
                break
            j = k + 1
        else:
            j += 1
    if not band:
        raise RuntimeError("red stats row not found")
    lookup = {v: d for d, v in RED_GLYPHS.items()}
    toks = []
    for s, e, rows in _cells(im, _red, band[0], band[1], 0, W):
        if e - s <= 2:
            ch = "."
        elif sum("#" in r for r in rows) == 1:
            ch = "-"
        else:
            ch = lookup.get("/".join(rows), "?")
        if toks and s - toks[-1][1] <= 7:
            toks[-1] = [toks[-1][0], e, toks[-1][2] + ch]
        else:
            toks.append([s, e, ch])
    if len(toks) < 10:
        raise RuntimeError(f"stats row has {len(toks)} values")
    pw = toks[9][2]  # KI LI SWI TTI CVT FMAX ThE EL MIX PW CAPE HELI
    try:
        mm = round(float(pw))
    except ValueError:
        raise RuntimeError(f"PW unreadable: {pw!r} (row: {' '.join(t[2] for t in toks)})") from None
    if not 3 <= mm <= 90:
        raise RuntimeError(f"PW out of range: {pw}")
    hhmm = None
    tl = {v: d for d, v in TITLE_GLYPHS.items()}
    head = _cells(im, _red, 7, 17, 0, 60)
    digits = "".join(tl.get("/".join(r), "?") for _, _, r in head)
    if len(digits) == 4 and digits.isdigit() and int(digits[:2]) < 24 and int(digits[2:]) < 60:
        hhmm = digits
    return mm, " ".join(t[2] for t in toks), hhmm


def solid_dewpoint(im, color=(0, 120, 0), gap=14):
    """Routine SMG plots draw the dewpoint as a dashed bright-green line; recolor it dark
    green and bridge each dash to its nearest neighbor so it reads as a solid line."""
    import numpy as np
    from scipy import ndimage
    a = np.array(im.convert("RGB"))
    m = (a[..., 0] < 60) & (a[..., 1] > 200) & (a[..., 2] < 60)
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    ends = []
    for k in range(1, n + 1):
        ys, xs = np.nonzero(lab == k)
        pts = np.stack([xs, ys], 1)
        d = ((pts[:, None] - pts[None]) ** 2).sum(-1)
        i, j = np.unravel_index(d.argmax(), d.shape)
        ends += [(k, tuple(pts[i])), (k, tuple(pts[j]))]
    out = im.convert("RGB").copy()
    a2 = np.array(out); a2[m] = color; out = Image.fromarray(a2)
    dr = ImageDraw.Draw(out)
    # link each endpoint to the nearest endpoint of another dash
    used = set()
    pairs = []
    for i, (ki, pi) in enumerate(ends):
        for j, (kj, pj) in enumerate(ends):
            if j > i and ki != kj:
                pairs.append((np.hypot(pi[0]-pj[0], pi[1]-pj[1]), i, j))
    pairs.sort()
    linked = set()
    for dist, i, j in pairs:
        if dist > gap: break
        if i in used or j in used: continue
        ki, kj = ends[i][0], ends[j][0]
        if (min(ki,kj), max(ki,kj)) in linked: continue
        used |= {i, j}; linked.add((min(ki,kj), max(ki,kj)))
        dr.line([ends[i][1], ends[j][1]], fill=color, width=2)
    # thicken the whole line to 2 px
    a3 = np.array(out)
    g = np.all(a3 == color, -1)
    g2 = ndimage.binary_dilation(g, structure=np.array([[0,0,0],[0,1,1],[0,1,0]]))
    a3[g2 & ~g & (np.abs(a3.astype(int) - [255,0,0]).sum(-1) > 30)] = color
    return Image.fromarray(a3)


def _launch_before(t, hour):
    """Latest hour:00Z at or before t."""
    c = t.replace(hour=hour, minute=0, second=0, microsecond=0)
    return c if c <= t else c - dt.timedelta(days=1)


def _read(name, url, seen, now):
    """Fetch one SMG plot; returns its image, PW and launch time. Routine plots carry no
    machine-readable date, so their launch time is the nominal (or title) hour on or
    before the time we first saw that exact image (tracked by hash in `seen`)."""
    import hashlib
    # cache-bust: weather.gov's CDN otherwise can hand back the previous plot for a while
    resp = get(f"{url}?t={int(now.timestamp())}")
    im = Image.open(io.BytesIO(resp.content))
    im.seek(0)
    im = im.convert("RGB")
    h = hashlib.sha1(im.tobytes()).hexdigest()[:16]
    prev = seen.get(name) or {}
    first = now
    if prev.get("hash") == h and prev.get("first_seen"):
        first = dt.datetime.strptime(prev["first_seen"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=dt.timezone.utc)
    r = {"im": im, "modified": resp.headers.get("Last-Modified", ""), "mm": None, "row": None, "t": None,
         "err": None, "seen": {"hash": h, "first_seen": f"{first:%Y-%m-%dT%H:%MZ}"}}
    try:
        if name in NOMINAL_HOUR:
            r["mm"], r["row"], hhmm = read_routine(im)
            hour = int(hhmm[:2]) if hhmm else NOMINAL_HOUR[name]
            r["t"] = _launch_before(first + dt.timedelta(hours=2), hour)  # may post just before the hour
            if hhmm:
                r["t"] = r["t"].replace(minute=int(hhmm[2:]))
        else:
            try:
                r["mm"], r["row"] = read_pw_mm(im)
                r["t"] = obs_time(r["row"].split()[0], now)
            except Exception:  # noqa: BLE001  (layout differs; fall back to the routine reader)
                try:
                    r["mm"], r["row"], _ = read_routine(im)
                except Exception:  # noqa: BLE001
                    pass
            if r["t"] is None and prev.get("hash") != h or (r["t"] is None and now - first < dt.timedelta(hours=8)):
                # undated but newly posted image: count it as launched when we first saw it
                r["t"] = first
    except Exception as e:  # noqa: BLE001
        r["err"] = e
    return r


def build(out):
    now = now_utc()
    try:
        seen = json.loads((out / OUT_JSON).read_text()).get("seen", {})
    except Exception:  # noqa: BLE001
        seen = {}
    got, notes = {}, []
    for name, url in SOURCES.items():
        try:
            got[name] = _read(name, url, seen, now)
            g = got[name]
            notes.append(f"{name} {g['t']:%d/%H%MZ}" if g["t"] else f"{name} undated ({g['err']})")
        except Exception as e:  # noqa: BLE001
            notes.append(f"{name} failed ({type(e).__name__})")
    if not got:
        raise RuntimeError("no SMG sounding could be fetched; " + "; ".join(notes))
    oldest = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    # newest launch wins even if its PW can't be read yet (e.g. the ~7:10 AM preliminary plot)
    name = max(got, key=lambda n: (got[n]["t"] or oldest, got[n]["mm"] is not None, n == "Early AM synoptic"))
    s = got[name]
    img = s["im"]
    if name in NOMINAL_HOUR:
        try:
            img = solid_dewpoint(img)
        except Exception as e:  # noqa: BLE001
            notes.append(f"dewpoint restyle failed ({e})")
    img.save(out / OUT_IMG, optimize=True)
    result = {"updated": f"{now:%Y-%m-%d %H:%MZ}", "source": name, "url": SOURCES[name],
              "source_modified": s["modified"], "seen": {n: g["seen"] for n, g in got.items()}}
    if s["mm"] is not None:
        result.update({"pw_mm": s["mm"], "pw_in": round(s["mm"] / 25.4, 2), "row": s["row"]})
        note = f"{name}: PW {s['mm']} mm = {s['mm'] / 25.4:.2f} in"
    else:
        note = f"{name}: image saved; PW not read ({s['err']})"
    if s["t"]:
        result["obs_time"] = f"{s['t']:%Y-%m-%dT%H:%MZ}"
    note += " [" + ", ".join(notes) + "]"
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
            r = geo["dot_d"] * 1.7  # outer radius; star spans ~3.4x a dot's width
            sc = 4  # draw large and shrink for smooth edges
            big = im.resize((im.width * sc, im.height * sc), Image.LANCZOS)
            d = ImageDraw.Draw(big)
            d.polygon(_star(x * sc, y * sc, r * sc, r * sc * 0.45), fill=(255, 255, 0),
                      outline=(60, 60, 60), width=max(2, round(sc * geo["dot_d"] / 14)))
            im = big.resize(im.size, Image.LANCZOS)
            note = f"star at {pw:.2f} in"
    except Exception as e:  # noqa: BLE001
        note = f"no star ({type(e).__name__}: {e})"
    im.save(out / "snd_pw_climo.png", optimize=True)
    return note

