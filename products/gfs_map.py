"""GFS surface map drawn from raw NOMADS GRIB in a clean, GALWEM-like style:
tan land, light blue-gray ocean, 6-h precipitation (green -> dark green -> yellow -> red),
gray MSLP isobars, black 10-m wind barbs, dotted lat/lon grid with inline labels, and the
1000-500 mb thickness (570 solid red, 540 solid blue, others red dashed).

The image keeps the exact size and Mercator geometry of the NCEP MAG 'west-atl' maps the
slides used before (1280 x 1024, mapping in gfs_thick), so the slides' crop, KSC marker and
layout stay the same. It is rendered at SCALE x that size for sharpness."""
import datetime as dt
import io
import tempfile

import numpy as np

from .common import get
from .gfs_thick import AX, AY, BX, BY, LEVELS, thickness

SCALE = 2
W, H = 1280, 1024
NOMADS = ("https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?"
          "file=gfs.t{cc:02d}z.pgrb2.0p25.f{fff:03d}"
          "&lev_mean_sea_level=on&lev_10_m_above_ground=on&lev_surface=on"
          "&var_PRMSL=on&var_UGRD=on&var_VGRD=on&var_APCP=on"
          "&subregion=&leftlon=-115&rightlon=-35&toplat=52&bottomlat=-8&dir=%2Fgfs.{ymd}%2F{cc:02d}%2Fatmos")
LAND, OCEAN = "#f6e7c8", "#d9e6e8"
LINE = "#4a4a4a"
# 6-h precipitation (inches): light green = light ... dark green ... yellow ... red
P_LEVELS = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 1.00, 1.50, 2.00, 10.0]
P_COLORS = ["#c9ecbd", "#93d58a", "#4fb35a", "#23843a", "#0f5c27", "#f4e65a", "#f2b233", "#e8562a", "#c0141c"]


def _inv_merc(m):
    return np.degrees(2 * np.arctan(np.exp(np.radians(m))) - np.pi / 2)


def _fields(init, fff):
    """MSLP (mb), 10-m u/v (kt), 6-h precip ending at fff (in), lats, lons."""
    import pygrib

    def grab(f):
        data = get(NOMADS.format(cc=init.hour, fff=f, ymd=f"{init:%Y%m%d}"), tries=3, timeout=90).content
        with tempfile.NamedTemporaryFile(suffix=".grb2") as tf:
            tf.write(data)
            tf.flush()
            g = pygrib.open(tf.name)
            recs = list(g)
            g.close()
        return recs

    recs = grab(fff)
    by = {}
    for r in recs:
        by.setdefault(r.shortName, []).append(r)
    mslp, lats, lons = (by.get("prmsl") or by["msl"])[0].data()
    u = by["10u"][0].values * 1.943844
    v = by["10v"][0].values * 1.943844
    # APCP: use a record covering exactly (fff-6, fff]; else difference of 0-based totals
    ap = {(int(r.startStep), int(r.endStep)): r.values for r in by.get("tp", [])}
    if (fff - 6, fff) in ap:
        pcp = ap[(fff - 6, fff)]
    elif (0, fff) in ap:
        prev = {(int(r.startStep), int(r.endStep)): r.values for r in grab(fff - 6) if r.shortName == "tp"}
        if (0, fff - 6) in prev:
            pcp = ap[(0, fff)] - prev[(0, fff - 6)]
        elif (fff - 12, fff - 6) in prev and (fff - 12, fff) in ap:
            pcp = ap[(fff - 12, fff)] - prev[(fff - 12, fff - 6)]
        else:
            pcp = ap[(0, fff)] - next(iter(prev.values())) if prev else ap[(0, fff)]
    elif ap:
        (s, e), vals = max(ap.items(), key=lambda kv: kv[0][1])
        pcp = vals
    else:
        pcp = np.zeros_like(mslp)
    pcp = np.clip(np.asarray(pcp), 0, None) / 25.4  # kg m-2 (mm) -> inches
    lons = np.where(lons > 180, lons - 360, lons)
    return np.asarray(mslp) / 100.0, np.asarray(u), np.asarray(v), pcp, lats, lons


def render(init, fff):
    """PNG bytes of the map for GFS run `init` (UTC) at forecast hour fff."""
    import matplotlib
    matplotlib.use("Agg")
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt

    mslp, u, v, pcp, lats, lons = _fields(init, fff)
    lat_t, lon_t, th = thickness(init, fff)

    # extent from the MAG pixel mapping (full image, Mercator)
    lon0, lon1 = (0 - BX) / AX, (W - BX) / AX
    lat1, lat0 = _inv_merc((BY - 0) / AY), _inv_merc((BY - H) / AY)
    proj = ccrs.Mercator()
    pc = ccrs.PlateCarree()
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100 * SCALE)
    ax = fig.add_axes([0, 0, 1, 1], projection=proj)
    ax.set_extent([lon0, lon1, lat0, lat1], crs=pc)
    ax.set_facecolor(OCEAN)
    ax.add_feature(cfeature.LAND.with_scale("50m"), facecolor=LAND, edgecolor="none", zorder=0)
    ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor=OCEAN, edgecolor=LINE, linewidth=0.4, zorder=0.5)

    cf = ax.contourf(lons, lats, pcp, levels=P_LEVELS, colors=P_COLORS, alpha=0.82, transform=pc, zorder=1)

    ax.add_feature(cfeature.COASTLINE.with_scale("50m"), edgecolor="#2b2b2b", linewidth=0.9, zorder=2)
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor="#2b2b2b", linewidth=0.8, zorder=2)
    ax.add_feature(cfeature.STATES.with_scale("50m"), edgecolor="#555555", linewidth=0.5, zorder=2)

    # dotted lat/lon grid with small inline labels (like the GALWEM chart)
    for lo in range(-105, -50, 5):
        ax.plot([lo, lo], [lat0, lat1], transform=pc, color="#6d6d6d", lw=0.6, ls=(0, (1, 3)), zorder=2.5)
    for la in range(5, 45, 5):
        ax.plot([lon0, lon1], [la, la], transform=pc, color="#6d6d6d", lw=0.6, ls=(0, (1, 3)), zorder=2.5)
    for lo in range(-100, -50, 5):
        for la in range(10, 45, 5):
            ax.text(lo + 0.15, la + 0.35, f"{la}N", transform=pc, fontsize=5.5, color="#555", zorder=2.6)
            ax.text(lo + 0.15, la - 1.9, f"{abs(lo)}W", transform=pc, fontsize=5.5, color="#555",
                    rotation=90, zorder=2.6)

    # MSLP every 4 mb, gray, labeled
    cs = ax.contour(lons, lats, mslp, levels=np.arange(960, 1060, 4), colors="#5c5c5c", linewidths=1.0,
                    transform=pc, zorder=3)
    for t in ax.clabel(cs, fmt="%d", fontsize=7.5, inline=True, inline_spacing=3):
        t.set_color("#4d4d4d")

    # 10-m wind barbs (kt) every 2 degrees
    s = 8
    ax.barbs(lons[::s, ::s], lats[::s, ::s], u[::s, ::s], v[::s, ::s], transform=pc, length=5.2,
             linewidth=0.6, color="black", zorder=4, sizes=dict(emptybarb=0))

    # 1000-500 mb thickness: 570 solid red, 540 solid blue, others red dashed (as before)
    styles = []
    for lev in LEVELS:
        if lev == 570:
            styles.append(("#e00000", "solid", 2.0))
        elif lev == 540:
            styles.append(("#0040ff", "solid", 2.0))
        else:
            styles.append(("#e00000", (0, (5, 3)), 1.4))
    ct = ax.contour(lon_t, lat_t, th, levels=LEVELS, colors=[c for c, _, _ in styles],
                    linestyles=[ls for _, ls, _ in styles], linewidths=[w for _, _, w in styles],
                    transform=pc, zorder=5)
    # thickness labels: reuse the in-view labeler (works in display pixels of a 1280x1024 frame)
    _label_thickness(ax, pc, lon_t, lat_t, th, styles, pe)

    # title band like before
    valid = init + dt.timedelta(hours=fff)
    ax.add_patch(plt.Rectangle((0, 1 - 34 / H), 1, 34 / H, transform=ax.transAxes, color="white", zorder=8))
    ax.text(0.5, 1 - 17 / H, f"GFS {init:%m/%d/%y %H}UTC  {fff:03d}HR FCST  VALID {valid:%a %m/%d/%y %H}UTC   "
            "6-HR PRECIP (IN), MSLP (MB), 10-M WIND (KT), 1000-500 MB THICKNESS (DAM)",
            transform=ax.transAxes, ha="center", va="center", fontsize=7.5, zorder=9)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100 * SCALE)
    plt.close(fig)
    return buf.getvalue()


def _label_thickness(ax, pc, lons, lats, th, styles, pe, spacing=480, margin=28):
    """Thickness value labels along the lines, inside the slide's visible window.
    Positions are worked out in MAG pixel space (same Mercator mapping as the map)."""
    import matplotlib.pyplot as plt
    from .gfs_thick import _merc
    X, Y = AX * lons + BX, BY - AY * _merc(lats)
    f2 = plt.figure()
    cs = f2.add_subplot().contour(X, Y, th, levels=LEVELS)
    allsegs = cs.allsegs
    plt.close(f2)
    x0, x1, y0, y1 = 131 + margin, 1120 - margin, 34 + margin, 647 - margin  # slide crop window
    placed = []
    for lev, segs, (color, _, _) in zip(LEVELS, allsegs, styles):
        for seg in segs:
            if len(seg) < 2:
                continue
            px, py = seg[:, 0], seg[:, 1]
            inside = (px > x0) & (px < x1) & (py > y0) & (py < y1)
            idx = np.flatnonzero(np.diff(np.r_[0, inside.astype(int), 0]))
            for a, b in zip(idx[::2], idx[1::2]):
                rx, ry = px[a:b], py[a:b]
                if len(rx) < 2:
                    continue
                d = np.r_[0, np.cumsum(np.hypot(np.diff(rx), np.diff(ry)))]
                if d[-1] < 60:
                    continue
                n = max(1, int(d[-1] // spacing))
                for k in range(n):
                    i = min(np.searchsorted(d, d[-1] * (k + 0.5) / n), len(rx) - 1)
                    Xp, Yp = rx[i], ry[i]
                    if any(abs(Xp - qx) < 60 and abs(Yp - qy) < 20 for qx, qy in placed):
                        continue
                    placed.append((Xp, Yp))
                    lon = (Xp - BX) / AX
                    lat = _inv_merc((BY - Yp) / AY)
                    ax.text(lon, lat, f"{lev:.0f}", color=color, fontsize=7.5, ha="center", va="center",
                            zorder=6, transform=pc,
                            path_effects=[pe.withStroke(linewidth=2.2, foreground="white")])
