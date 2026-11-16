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
LEVELS = np.arange(480, 612, 6)      # every 6 dam, as on MAG's thickness maps
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


def overlay(img_bytes, init, fff):
    """Return GIF bytes of the MAG map with thickness contours added."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    base = Image.open(io.BytesIO(img_bytes)).convert("RGB")
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
    cs = ax.contour(X, Y, th, levels=LEVELS, colors="#e00000", linewidths=1.8, linestyles=[(0, (5, 3))])
    cs.set_clip_path(clip)
    labels = ax.clabel(cs, fmt="%d", fontsize=11, inline=True, inline_spacing=4)
    for t in labels:
        x, y = t.get_position()
        if not (FRAME[0] + 15 < x < FRAME[2] - 15 and FRAME[1] + 10 < y < FRAME[3] - 10):
            t.set_visible(False)
        t.set_fontweight("bold")
        t.set_path_effects([pe.withStroke(linewidth=2.5, foreground="white")])
    fig.canvas.draw()
    rgb = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    out = Image.fromarray(rgb).quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    out.save(buf, "GIF", optimize=True)
    return buf.getvalue()
