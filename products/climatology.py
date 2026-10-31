"""Climatology charts with a NOW marker at today's date, plus the NHC 10-day
points-of-origin map for the current period."""
import calendar
import datetime as dt

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
            return url
        except Exception as e:  # noqa: BLE001
            err = e
    raise RuntimeError(f"no NHC origin map found: {err}")
