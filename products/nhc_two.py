"""NHC 7-day Atlantic outlook map with each disturbance's 7-day formation chance
written next to its shaded area, in the shading's color."""
import html as htmlmod
import io
import re

from PIL import Image, ImageDraw

from .common import font, get

PAGE = "https://www.nhc.noaa.gov/gtwo.php?basin=atlc&fdays=7"
MAP = "https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png"
SVG_W = 1920  # NHC's overlay coordinates are for a 1920-px-wide map
COLORS = {"low": (255, 255, 0), "medium": (255, 165, 0), "high": (230, 0, 0)}
# 12 pt on the slide: the map is 5,150,010 EMU wide; 12 pt = 152,400 EMU
FONT_FRAC = 152400 / 5150010


def _systems(page):
    start = page.find('id="view-atl-7d0"')
    if start < 0:
        raise RuntimeError("7-day Atlantic layer not found on NHC page")
    # the Atlantic 7-day layer ends where the next view (any basin/period) begins;
    # with no Atlantic areas there is no 'view-atl-7d1', so never run on into the Pacific
    end = page.find('id="view-', start + 10)
    sec = page[start:end if end > 0 else None]
    out = []
    for m in re.finditer(r'<g class="storm-system[^"]*"([^>]*)>(.*?)</g>', sec, re.S):
        attrs, body = m.groups()
        prob = re.search(r'data-prob="(\d+)"', attrs)
        risk = re.search(r'data-risk="(\w+)"', attrs)
        name = re.search(r'data-name="([^"]*)"', attrs)
        pts = re.search(r'<polygon[^>]*points="([^"]+)"', body)
        circ = re.search(r'<circle[^>]*cx="([\d.]+)"[^>]*cy="([\d.]+)"', body)
        if not prob or (risk and risk.group(1).lower() not in COLORS):
            continue  # active storms (risk="storm") have no formation chance
        xy = []
        if pts:
            v = [float(t) for t in re.split(r"[,\s]+", pts.group(1).strip()) if t]
            xy = list(zip(v[0::2], v[1::2]))
        elif circ:
            xy = [(float(circ.group(1)), float(circ.group(2)))]
        if xy:
            out.append({"prob": int(prob.group(1)), "risk": (risk.group(1) if risk else "low").lower(),
                        "name": htmlmod.unescape(name.group(1)) if name else "", "xy": xy})
    return out


def build(out):
    page = get(PAGE).text
    im = Image.open(io.BytesIO(get(MAP).content)).convert("RGB")
    W, H = im.size
    s = W / SVG_W
    systems = _systems(page)
    d = ImageDraw.Draw(im)
    f = font(max(14, round(W * FONT_FRAC * 1.05)), bold=True)
    placed = []
    for sy in systems:
        xs = [x * s for x, _ in sy["xy"]]
        ys = [y * s for _, y in sy["xy"]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        cy = (y0 + y1) / 2
        txt = f"{sy['prob']}%"
        l, t, r, b = d.textbbox((0, 0), txt, font=f, stroke_width=2)
        tw, th = r - l, b - t
        # try right of the area, then left, then above, then below
        cands = [(x1 + 6, cy - th / 2), (x0 - 6 - tw, cy - th / 2),
                 ((x0 + x1) / 2 - tw / 2, y0 - 6 - th), ((x0 + x1) / 2 - tw / 2, y1 + 6)]
        pos = None
        for x, y in cands:
            box = (x, y, x + tw, y + th)
            inside = x >= 4 and y >= 4 and x + tw <= W - 4 and y + th <= H * 0.86
            clash = any(not (box[2] < p[0] or box[0] > p[2] or box[3] < p[1] or box[1] > p[3]) for p in placed)
            if inside and not clash:
                pos = (x, y)
                break
        if pos is None:
            pos = (min(max(4, x1 + 6), W - tw - 4), min(max(4, cy - th / 2), H * 0.86 - th))
        placed.append((pos[0], pos[1], pos[0] + tw, pos[1] + th))
        d.text((pos[0] - l, pos[1] - t), txt, font=f, fill=COLORS.get(sy["risk"], COLORS["low"]),
               stroke_width=2, stroke_fill=(0, 0, 0))
    im.save(out / "nhc_atl_7d_labeled.png", optimize=True)
    return ", ".join(f"{x['prob']}% ({x['risk']})" for x in systems) or "no areas outlined"
