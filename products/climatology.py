"""Climatology charts with a NOW marker at today's date, plus the NHC 10-day
points-of-origin map for the current period."""
import calendar
import datetime as dt
import re

from PIL import Image, ImageDraw

from .common import ASSETS, font, get_image, now_label, now_local

# ---------------------------------------------------------------- precip / lightning
# x pixel of day-of-year d (0-based) in precip_ltg_climo_base.png (1280x720)
PL_X0, PL_PX_PER_DAY = 50, 1203 / 365
PL_TOP, PL_BOT = 86, 631
# annotation boxes (x0, y0, x1, y1) the line must not cross
PL_BOXES = [(720, 93, 858, 134), (508, 129, 621, 170), (845, 144, 983, 185), (413, 207, 574, 248),
            (108, 252, 246, 293), (1116, 252, 1254, 293), (994, 268, 1092, 309), (270, 288, 411, 329),
            (99, 329, 176, 370), (699, 336, 838, 377), (324, 362, 501, 403)]


def precip_ltg(out):
    today = now_local().date()
    doy = min(today.timetuple().tm_yday - 1, 364)
    x = round(PL_X0 + (doy + 0.5) * PL_PX_PER_DAY)
    im = Image.open(ASSETS / "precip_ltg_climo_base.png").convert("RGB")
    d = ImageDraw.Draw(im)
    gaps = sorted((y0 - 4, y1 + 8) for x0, y0, x1, y1 in PL_BOXES if x0 - 4 <= x <= x1 + 6)
    y = PL_TOP
    for g0, g1 in gaps + [(PL_BOT, PL_BOT)]:
        if g0 > y:
            d.line([(x, y), (x, min(g0, PL_BOT))], fill=(224, 0, 0), width=5)
        y = max(y, g1)
    now_label(d, x, PL_BOT - 6, size=20)
    im.save(out / "precip_ltg_climo_now.png", optimize=True)
    return f"x={x} for {today}"


# ---------------------------------------------------------------- hurricane activity
# tc_activity_base.png (802x469): Aug 1 tick at x=364, 2.836 px/day; plot May 1 .. Dec 31
TC_AUG1, TC_PX_PER_DAY = 364, 2.836
TC_TOP, TC_BOT = 115, 424


def tc_activity(out):
    today = now_local().date()
    days = (today - dt.date(today.year, 8, 1)).days
    x = round(TC_AUG1 + days * TC_PX_PER_DAY)
    im = Image.open(ASSETS / "tc_activity_base.png").convert("RGB")
    d = ImageDraw.Draw(im)
    if dt.date(today.year, 5, 1) <= today <= dt.date(today.year, 12, 31):
        yellow = (255, 255, 0)
        d.line([(x, TC_TOP), (x, TC_BOT)], fill=yellow, width=4)
        f = font(28)
        l, t, r, b = d.textbbox((0, 0), "NOW!", font=f)
        d.text((x - (r - l) / 2 - l, TC_TOP - 2 - b), "NOW!", font=f, fill=yellow)
        note = f"x={x}"
    else:
        note = "outside May-Dec chart range; no NOW line"
    im.save(out / "tc_activity_now.png", optimize=True)
    return f"{note} for {today}"


# ---------------------------------------------------------------- NHC points of origin
MON = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _periods(year, month):
    last = calendar.monthrange(year, month)[1]
    return [(1, 10), (11, 20), (21, last)]


def tc_origin(out):
    today = now_local().date()
    y, m = today.year, today.month
    per = [p for p in _periods(y, m) if p[0] <= today.day <= p[1]][0]
    # walk back through earlier periods if NHC has no map for this one (quiet season)
    cands = []
    yy, mm, idx = y, m, _periods(y, m).index(per)
    for _ in range(36):
        a, b = _periods(yy, mm)[idx]
        cands.append(f"https://www.nhc.noaa.gov/climo/images/{MON[mm - 1]}_{a}_{b}.png")
        if mm == 2 and b in (28, 29):
            cands.append(f"https://www.nhc.noaa.gov/climo/images/{MON[mm - 1]}_{a}_{29 if b == 28 else 28}.png")
        idx -= 1
        if idx < 0:
            mm -= 1
            if mm == 0:
                mm, yy = 12, yy - 1
            idx = 2
    err = None
    for url in cands:
        try:
            im = get_image(url).convert("RGB")
            if im.width > 1600:
                im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
            im.save(out / "tc_origin_current.png", optimize=True)
            _tc_origin_atlantic(im, url).save(out / "tc_origin_atl.png", optimize=True)
            return url
        except Exception as e:  # noqa: BLE001
            err = e
    raise RuntimeError(f"no NHC origin map found: {err}")


# NHC origin maps (scaled to 1600 px wide): map frame and graticule positions
ORG_LEFT_X = 800      # ~98.5W, just west of the Gulf coast of Mexico: drop the Pacific basin
ORG_MAP_TOP = 49      # top border of the map frame (title above it is redrawn)
ORG_MAP_BOT = 637     # bottom border of the map frame
ORG_OCEAN = (100, 162, 202)
ORG_LAT_Y = {50: 122, 45: 188, 40: 248, 35: 305, 30: 358, 25: 408, 20: 456, 15: 503, 10: 548, 5: 593}


def _tc_origin_atlantic(im, url):
    """Gulf, Caribbean and Atlantic to Africa only, with the title and latitude
    labels redrawn for the narrower map."""
    k = im.width / 1600
    mon_day = re.search(r"/([a-z]+)_(\d+)_(\d+)\.png$", url)
    months = {m.lower()[:3]: m for m in calendar.month_name if m}
    period = (f"{months.get(mon_day.group(1)[:3], mon_day.group(1).title())} {mon_day.group(2)}-{mon_day.group(3)}"
              if mon_day else "")
    im = im.copy()
    # erase the East Pacific origin points still inside the crop (south of
    # Guatemala/El Salvador: west of ~85.5W and south of ~13.5N)
    px = im.load()
    for x in range(round(ORG_LEFT_X * k), round(916 * k)):
        for y in range(round(516 * k), round(ORG_MAP_BOT * k)):
            r, g, b = px[x, y]
            if r - b > 30:  # yellow dot or its anti-aliased edge (ocean/grey/black are <= 0)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if sum(px[x + dx, y + dy]) > 120:  # keep black track lines
                            px[x + dx, y + dy] = ORG_OCEAN
    crop = im.crop((round(ORG_LEFT_X * k), round(ORG_MAP_TOP * k), im.width, im.height))
    # redraw the frame's top edge clean (the old title's descenders touch it)
    band = round(4 * k)
    row = crop.crop((0, band, crop.width, band + 1))
    for yy in range(band):
        crop.paste(row, (0, yy))
    ImageDraw.Draw(crop).line((0, 0, round((1590 - ORG_LEFT_X) * k), 0), fill="black", width=max(1, round(1.5 * k)))
    # blank the clipped "100W" tick label left over below the frame
    ImageDraw.Draw(crop).rectangle((0, round((ORG_MAP_BOT - ORG_MAP_TOP + 2) * k), round(30 * k), crop.height), fill="white")
    margin, title_h = round(62 * k), round(58 * k)
    W, H = crop.width + margin, crop.height + title_h
    canvas = Image.new("RGB", (W, H), "white")
    canvas.paste(crop, (margin, title_h))
    d = ImageDraw.Draw(canvas)
    title = f"{period} Atlantic Tropical & Subtropical Cyclone Points of Origin".strip()
    size = round(34 * k)
    while size > 12 and d.textlength(title, font=font(size)) > W - 20:
        size -= 1
    d.text((W / 2, title_h / 2 + 2), title, font=font(size), fill="black", anchor="mm")
    f = font(round(19 * k))
    for lat, y in ORG_LAT_Y.items():
        d.text((margin - 6, title_h + (y - ORG_MAP_TOP) * k), f"{lat}\u00b0N", font=f, fill="black", anchor="rm")
    return canvas
