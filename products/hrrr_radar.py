"""HRRR composite reflectivity for 11 AM, 2 PM, 5 PM and 8 PM local, from the latest HRRR
run that covers all four times, drawn from NOMADS GRIB in the look of the SPC REFS viewer
(slide 'Modeled Future Radar'): same map domain, colors, county/state lines.

Panel geometry copies viewers.REFS: the viewer at 800x1048 css px, centered on
REFS_VIEW (-80.82, 28.50, zoom 6.87, 512-px tiles), cropped to CROP, at 2x."""
import datetime as dt
import math
import tempfile
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageDraw

from .common import font, get, now_utc

ET = ZoneInfo("America/New_York")
HOURS = [11, 14, 17, 20]
OUT_IMG = "hrrr_cref.png"
IDX = ("https://nomads.ncep.noaa.gov/pub/data/nccf/com/hrrr/prod/hrrr.{ymd}/conus/"
       "hrrr.t{cc:02d}z.wrfsfcf{ff:02d}.grib2.idx")
FILTER = ("https://nomads.ncep.noaa.gov/cgi-bin/filter_hrrr_2d.pl?file=hrrr.t{cc:02d}z.wrfsfcf{ff:02d}.grib2"
          "&var_REFC=on&lev_entire_atmosphere=on&subregion=&leftlon=-85&rightlon=-76&toplat=32&bottomlat=24"
          "&dir=%2Fhrrr.{ymd}%2Fconus")

# --- REFS viewer geometry (see viewers.py) ---
VW, VH = 800, 1048
CROP = (96, 84, 800, 978)
CENTER = (-80.82, 28.50, 6.87)
CENTER_PX = (VW / 2, VH / 2 + 27)  # map center is 27 css px below page center (fit to coastlines)
SC = 2  # render scale (the viewer screenshots were at device_scale_factor 2)
R = 6378137.0

# SPC REFS reflectivity colors, 2.5-dBZ bands from 12.5 to 70
LEVELS = [12.5 + 2.5 * k for k in range(24)]
COLORS = ['#b5c4e3', '#90a7d6', '#6a89c8', '#476cbb', '#274fae', '#254f5d', '#4e764d', '#7e9a73',
          '#adbf8f', '#fdf384', '#f0d46e', '#e4b559', '#d99844', '#cd7933', '#c35c24', '#bb271a',
          '#931d15', '#6c1413', '#933ea8', '#772c9b', '#59198d', '#828282', '#b4b4b4']
OCEAN, LAND = "#d8f2ff", "#ffffff"


def extent():
    """Web-Mercator (EPSG:3857) bounds of the cropped viewer panel."""
    lon, lat, z = CENTER
    s = 2 * math.pi * R / (512 * 2 ** z)  # meters per css px
    xc = R * math.radians(lon)
    yc = R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    cx, cy = CENTER_PX
    x0, y0, x1, y1 = CROP
    return xc + (x0 - cx) * s, xc + (x1 - cx) * s, yc - (y1 - cy) * s, yc + (cy - y0) * s


def _ok(url):
    try:
        get(url, tries=1, timeout=20)
        return True
    except Exception:  # noqa: BLE001
        return False


def pick_run(now=None):
    """Latest HRRR run on NOMADS (<= the 11 AM valid time) whose forecast reaches 8 PM."""
    now = now or now_utc()
    day = now.astimezone(ET).date()
    valids = [dt.datetime(day.year, day.month, day.day, h, tzinfo=ET).astimezone(dt.timezone.utc) for h in HOURS]
    t = min(now, valids[0]).replace(minute=0, second=0, microsecond=0)
    for _ in range(14):
        fmax = 48 if t.hour % 6 == 0 else 18
        fh = [int((v - t).total_seconds() // 3600) for v in valids]
        if fh[-1] <= fmax and _ok(IDX.format(ymd=f"{t:%Y%m%d}", cc=t.hour, ff=fh[-1])):
            return t, valids, fh
        t -= dt.timedelta(hours=1)
    raise RuntimeError("no HRRR run found on NOMADS covering 11 AM - 8 PM")


def _refc(init, ff):
    import pygrib
    data = get(FILTER.format(ymd=f"{init:%Y%m%d}", cc=init.hour, ff=ff), tries=3, timeout=90).content
    with tempfile.NamedTemporaryFile(suffix=".grb2") as tf:
        tf.write(data)
        tf.flush()
        g = pygrib.open(tf.name)
        r = g.select(shortName="refc")[0] if g.select(shortName="refc") else g[1]
        vals, lats, lons = r.data()
        g.close()
    return np.ma.filled(vals, -10), lats, lons


def render_panel(vals=None, lats=None, lons=None, overlay_only=False):
    import cartopy.crs as ccrs
    import cartopy.feature as cf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap

    pw, ph = (CROP[2] - CROP[0]) * SC, (CROP[3] - CROP[1]) * SC
    dpi = 100
    fig = plt.figure(figsize=(pw / dpi, ph / dpi), dpi=dpi)
    merc = ccrs.Mercator.GOOGLE
    ax = fig.add_axes([0, 0, 1, 1], projection=merc)
    x0, x1, y0, y1 = extent()
    ax.set_extent([x0, x1, y0, y1], crs=merc)
    ax.set_aspect("auto")
    ax.axis("off")
    ax.spines["geo"].set_visible(False)
    pc = ccrs.PlateCarree()
    if overlay_only:
        fig.patch.set_alpha(0)
        ax.patch.set_alpha(0)
    else:
        fig.patch.set_facecolor(OCEAN)
        ax.add_feature(cf.OCEAN.with_scale("10m"), facecolor=OCEAN, edgecolor="none", zorder=0)
        ax.add_feature(cf.LAND.with_scale("10m"), facecolor=LAND, edgecolor="none", zorder=0)
        ax.add_feature(cf.LAKES.with_scale("10m"), facecolor=OCEAN, edgecolor="none", zorder=0.5)
        if vals is not None:
            cmap = ListedColormap(COLORS)
            norm = BoundaryNorm(LEVELS, cmap.N)
            ax.contourf(lons, lats, vals, levels=LEVELS, cmap=cmap, norm=norm, transform=pc, zorder=1,
                        antialiased=True)
    counties = cf.NaturalEarthFeature("cultural", "admin_2_counties", "10m", facecolor="none")
    ax.add_feature(counties, edgecolor="#4d4d4d", linewidth=1.9, linestyle=(0, (5, 3)), zorder=2)
    ax.add_feature(cf.STATES.with_scale("10m"), edgecolor="#333333", linewidth=3.0, zorder=2.1)
    ax.add_feature(cf.COASTLINE.with_scale("10m"), edgecolor="#222222", linewidth=4.2, zorder=2.2)
    buf = tempfile.SpooledTemporaryFile()
    fig.savefig(buf, format="png", dpi=dpi, transparent=overlay_only, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGBA" if overlay_only else "RGB")


def _fmt_hour(t):
    return t.strftime("%I %p").lstrip("0")


def compose(panels, init, valids, fh, out):
    S = 5000  # EMU per px, same layout as refs_18z.png
    pw, ph, gap = 2647000 // S, 3361000 // S, 120000 // S
    W = 4 * pw + 3 * gap
    lab_h, pan_y, src_y = 460000 // S, 500000 // S, (5274000 - 1250000) // S
    H = src_y + 300000 // S
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    f1, f2, f3 = font(38, bold=True), font(25), font(22)
    for k, (pan, v, f) in enumerate(zip(panels, valids, fh)):
        x = k * (pw + gap)
        lv = v.astimezone(ET)
        t1 = f"{_fmt_hour(lv)} {lv:%Z}"
        t2 = f"{init:%H}Z run (F{f:02d}) · Valid {v:%H}Z {v:%a %d %b}"
        for txt, ft, col, yb in ((t1, f1, (31, 42, 68), lab_h - 34), (t2, f2, (64, 64, 64), lab_h)):
            l, t, r, b = d.textbbox((0, 0), txt, font=ft)
            d.text((x + (pw - (r - l)) / 2 - l, yb - (b - t) - t), txt, font=ft, fill=col)
        im.paste(pan.resize((pw, ph), Image.LANCZOS), (x, pan_y))
        d.rectangle([x, pan_y, x + pw - 1, pan_y + ph - 1], outline=(127, 127, 127), width=2)
    src = (f"HRRR Composite Reflectivity · {init:%H}Z {init:%d %b %Y} run · "
           f"Source: NOAA/NCEP HRRR (nomads.ncep.noaa.gov) · Updated {now_utc():%H%MZ}")
    d.text((0, H - 34), src, font=f3, fill=(89, 89, 89))
    im.save(out / OUT_IMG, optimize=True)


def build(out):
    init, valids, fh = pick_run()
    panels = []
    for f in fh:
        vals, lats, lons = _refc(init, f)
        panels.append(render_panel(vals, lats, lons))
    compose(panels, init, valids, fh, out)
    return f"HRRR {init:%d/%HZ} run, F{'/'.join(f'{f:02d}' for f in fh)}"


def preview(out):
    note = build(out)
    render_panel(overlay_only=True).save(out / "hrrr_overlay.png")
    return note
