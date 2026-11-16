"""GFS 1000-500 mb thickness (red dashed contours) drawn onto the MAG West-Atlantic
10-m wind / precip maps, for the same run and forecast hour.

The MAG 'west-atl' maps are Mercator; the pixel mapping below was fitted to MAG's own
1000_500_thick map of the same domain (matches its contours to within ~1-2 px)."""
import io
import math

import numpy as np
from PIL import Image

from .common import get

# x = AX * lon + BX ; y = BY - AY * mercator_deg(lat)   (1280 x 1024 MAG image)
AX, BX, AY, BY = 24.0472, 2563.42, 24.0602, 1085.72
FRAME = (38, 34, 1242, 967)          # map area (x0, y0, x1, y1); outside it is title/legend
LEVELS = np.arange(480, 612, 6)
BORDER = (70, 35, 10)                # dark brown for coastlines and state lines      # every 6 dam, as on MAG's thickness maps
NOMADS = ("https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25.pl?"
          "file=gfs.t{cc:02d}z.pgrb2.0p25.f{fff:03d}&lev_1000_mb=on&lev_500_mb=on&var_HGT=on"
          "&subregion=&leftlon=-115&rightlon=-35&toplat=52&bottomlat=-8&dir=%2Fgfs.{ymd}%2F{cc:02d}%2Fatmos")
_cache = {}


def _merc(lat):
    return np.degrees(np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)))


def thickness(init, fff):
    """(lats, lons, thickness dam) for the GFS run `init` (UTC datetime) at forecast hour fff."""
    key = (init, fff)
    if key not in _cache:
        import pygrib
        import tempfile
        data = get(NOMADS.format(cc=init.hour, fff=fff, ymd=f"{init:%Y%m%d}"), tries=3, timeout=90).content
        with tempfile.NamedTemporaryFile(suffix=".grb2") as tf:
            tf.write(data)
            tf.flush()
            grbs = pygrib.open(tf.name)
            z = {g.level: g for g in grbs}
            z500, lats, lons = z[500].data()
            z1000 = z[1000].values
            grbs.close()
        lons = np.where(lons > 180, lons - 360, lons)
        _cache[key] = (lats, lons, (np.asarray(z500) - np.asarray(z1000)) / 10.0)
    return _cache[key]


def bolder_borders(im):
    """Darken and thicken MAG's brown coastlines and state/country borders (the brown
    lat/lon grid lines are left as they are)."""
    from scipy import ndimage
    a = np.asarray(im).copy()
    br = (a[..., 0] == 139) & (a[..., 1] == 71) & (a[..., 2] == 38)
    H, W = br.shape
    grid = np.zeros_like(br)
    grid[np.nonzero(br.sum(1) > W * 0.25)[0], :] = True
    grid[:, np.nonzero(br.sum(0) > H * 0.25)[0]] = True
    m = ndimage.binary_dilation(br & ~grid, structure=np.ones((2, 2), bool))
    a[m] = BORDER
    return Image.fromarray(a)


def _label(ax, cs, styles, spacing=480, margin=28):
    """Put each thickness value on its line inside the map view: at least one label on
    every line segment that crosses the map, and one every `spacing` px along long lines."""
    import matplotlib.patheffects as pe
    x0, y0, x1, y1 = FRAME[0] + margin, FRAME[1] + margin, FRAME[2] - margin, FRAME[3] - margin
    placed = []
    for lev, segs, (color, _, _) in zip(cs.levels, cs.allsegs, styles):
        for seg in segs:
            inside = (seg[:, 0] > x0) & (seg[:, 0] < x1) & (seg[:, 1] > y0) & (seg[:, 1] < y1)
            # split into runs of consecutive points inside the view
            idx = np.flatnonzero(np.diff(np.r_[0, inside.astype(int), 0]))
            for a, b in zip(idx[::2], idx[1::2]):
                run = seg[a:b]
                if len(run) < 2:
                    continue
                d = np.r_[0, np.cumsum(np.hypot(*np.diff(run, axis=0).T))]
                total = d[-1]
                if total < 60:
                    continue
                n = max(1, int(total // spacing))
                for k in range(n):
                    t = total * (k + 0.5) / n
                    i = min(np.searchsorted(d, t), len(run) - 1)
                    x, y = run[i]
                    if any(abs(x - px) < 60 and abs(y - py) < 20 for px, py in placed):
                        continue
                    placed.append((x, y))
                    ax.text(x, y, f"{lev:.0f}", color=color, fontsize=10, ha="center", va="center",
                            zorder=5, path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])


def overlay(img_bytes, init, fff):
    """Return GIF bytes of the MAG map with thickness contours added."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    base = bolder_borders(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
    W, H = base.size
    if (W, H) != (1280, 1024):
        raise ValueError(f"unexpected MAG image size {W}x{H}")
    lats, lons, th = thickness(init, fff)
    X, Y = AX * lons + BX, BY - AY * _merc(lats)
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(np.asarray(base), interpolation="nearest")
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    clip = Rectangle((FRAME[0], FRAME[1]), FRAME[2] - FRAME[0], FRAME[3] - FRAME[1], transform=ax.transData)
    styles = []
    for lev in LEVELS:
        if lev == 570:
            styles.append(("#e00000", "solid", 2.4))
        elif lev == 540:
            styles.append(("#0040ff", "solid", 2.4))
        else:
            styles.append(("#e00000", (0, (5, 3)), 1.8))
    cs = ax.contour(X, Y, th, levels=LEVELS, colors=[c for c, _, _ in styles],
                    linestyles=[ls for _, ls, _ in styles], linewidths=[w for _, _, w in styles])
    cs.set_clip_path(clip)
    _label(ax, cs, styles)
    fig.canvas.draw()
    rgb = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    out = Image.fromarray(rgb).quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    out.save(buf, "GIF", optimize=True)
    return buf.getvalue()
