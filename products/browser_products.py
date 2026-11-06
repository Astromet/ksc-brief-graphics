"""Products that need a real browser: GFS/ECMWF meteograms and the SPC
sounding-climatology chart + data readout."""
import base64
import io
import json
import re

from PIL import Image, ImageChops, ImageDraw

from .common import ASSETS, font, now_local


# ------------------------------------------------------------------ meteograms
def meteograms(out, browser):
    js = (ASSETS / "meteogram.js").read_text()
    notes = []
    for model, fname in (("gfs", "meteogram_gfs.png"), ("ecmwf", "meteogram_ecmwf.png")):
        page = browser.new_page()
        page.set_default_timeout(400000)
        try:
            page.set_content("<html><body></body></html>")
            page.add_script_tag(content=js)
            data_url = page.evaluate(
                """async (m) => { const r = await buildMeteogram({model: m, W: 1600, H: 889});
                                  return r.canvas.toDataURL('image/png'); }""", model)
            png = base64.b64decode(data_url.split(",", 1)[1])
            Image.open(io.BytesIO(png)).convert("RGB").save(out / fname, optimize=True)
            notes.append(model)
        finally:
            page.close()
    return " + ".join(notes)


# ------------------------------------------------------------------ SPC sounding climatology
SPC = "https://www.spc.noaa.gov/exper/soundingclimov2/"
HDR = ["Daily Min", "Min", "10%", "25%", "Median", "Daily Mean", "75%", "90%", "Max", "Daily Max"]
COL = ["3333CC", "00008B", "4FB3B0", "8B1A1A", "000000", "404040", "8B1A1A", "C8A04A", "E03030", "B22222"]


def _trim_box(im, pad=6, full=False):
    bg = Image.new("RGB", im.size, (255, 255, 255))
    box = ImageChops.difference(im, bg).point(lambda v: 255 if v > 24 else 0).getbbox()
    if not box:
        box = (pad, pad, im.width - pad, im.height - pad)
    l, t, r, b = box
    crop = (max(0, l - pad), max(0, t - pad), min(im.width, r + pad), min(im.height, b + pad))
    return crop if full else crop[:2]


def _trim(im, pad=6):
    return im.crop(_trim_box(im, pad, full=True))


def _table(date_label, vals):
    W, H = 1600, 258
    rows = [(0, 70), (70, 170), (170, 258)]
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    cw = W / 10
    navy, grid = (31, 42, 68), (191, 191, 191)
    d.rectangle([0, 0, W - 1, 69], fill=navy)
    f = font(30, bold=True)
    t = f"Data Readout · {date_label} · PW (in)"
    l, tt, r, b = d.textbbox((0, 0), t, font=f)
    d.text(((W - (r - l)) / 2 - l, (70 - (b - tt)) / 2 - tt), t, font=f, fill="white")
    d.rectangle([0, 70, W - 1, 169], fill=(231, 234, 240))
    fh, fv = font(23, bold=True), font(36, bold=True)
    for i in range(10):
        x0 = i * cw
        words = HDR[i].split()
        lines = [" ".join(words)] if len(words) == 1 else words
        hgt = len(lines) * 28
        for k, ln in enumerate(lines):
            l, tt, r, b = d.textbbox((0, 0), ln, font=fh)
            d.text((x0 + (cw - (r - l)) / 2 - l, 120 - hgt / 2 + k * 28 - tt + 2), ln, font=fh, fill=navy)
        v = vals[i] if i < len(vals) else "-"
        l, tt, r, b = d.textbbox((0, 0), v, font=fv)
        col = tuple(int(COL[i][j:j + 2], 16) for j in (0, 2, 4))
        d.text((x0 + (cw - (r - l)) / 2 - l, 214 - (b - tt) / 2 - tt), v, font=fv, fill=col)
    for i in range(11):
        x = min(round(i * cw), W - 1)
        d.line([(x, 70), (x, H - 1)], fill=grid, width=2)
    for y in (70, 170, H - 1):
        d.line([(0, y), (W, y)], fill=grid, width=2)
    return im


def sounding_climo(out, browser):
    ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, device_scale_factor=2.25,
                              user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                          "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"))
    page = ctx.new_page()
    try:
        resp = page.goto(SPC, wait_until="domcontentloaded", timeout=120000)
        try:
            page.wait_for_selector("#stn", state="attached", timeout=60000)
        except Exception:
            page.screenshot(path=str(out / "debug_sounding.png"))
            raise RuntimeError(f"SPC page not usable (HTTP {resp.status if resp else '?'}): "
                               f"{page.title()!r} {page.inner_text('body')[:300]!r}")
        page.wait_for_timeout(3000)
        page.select_option("#stn", "XMR")
        page.wait_for_function("document.getElementById('svg-title') && "
                               "document.getElementById('svg-title').innerText.includes('XMR')", timeout=120000)
        page.select_option("#sndparam", "PW")
        page.wait_for_timeout(4000)
        page.wait_for_function("document.querySelector('#loading-page') == null || "
                               "getComputedStyle(document.querySelector('#loading-page')).display == 'none'",
                               timeout=120000)
        # redraw the main chart wider (less elongated), then mark today's 12Z values
        page.evaluate("() => { const c = dc.chartRegistry.list()[0]; c.width(520).height(390); c.render(); }")
        page.wait_for_timeout(2500)
        page.click("#gototoday12 a")
        page.wait_for_timeout(2500)
        txt = page.inner_text("#chart-sample")
        lines = [ln for ln in txt.splitlines() if ln.strip()]
        m = re.match(r"\s*([A-Z][a-z]{2} \d{1,2} \(\d{2}Z\))", lines[0])
        date_label = m.group(1) if m else now_local().strftime("%b %d (12Z)")
        vals = re.findall(r"-?\d+\.\d+|-", lines[-1])
        if len([v for v in vals if v != "-"]) < 5:
            raise RuntimeError(f"data readout not populated: {lines[-1]!r}")
        page.evaluate("() => { const s = document.querySelector('#line-chart svg'); s.style.background = '#fff'; "
                      "s.style.backgroundColor = '#fff'; }")
        # where today's dots sit and how PW maps to the vertical axis (SVG px), so the
        # latest KXMR PW can be starred on the chart (see ksc_sounding.star_chart)
        geo = page.evaluate("""() => {
            const c = dc.chartRegistry.list()[0], svg = document.querySelector('#line-chart svg');
            const sb = svg.getBoundingClientRect();
            const dots = [...svg.querySelectorAll('circle.dot')].filter(e =>
                +getComputedStyle(e).fillOpacity > 0.5 && getComputedStyle(e).display != 'none');
            if (!dots.length) return null;
            const b = dots[0].getBoundingClientRect();
            const y = c.y(), top = c.margins().top;
            return {x: b.x + b.width / 2 - sb.x, dot_d: b.width,
                    y0: top + y(0) + svg.getBoundingClientRect().y - sb.y,
                    y_per_in: y(0) - y(1), ymax: y.domain()[1]};
        }""")
        png = page.locator("#line-chart svg").first.screenshot(omit_background=False)
        raw = Image.open(io.BytesIO(png)).convert("RGB")
        chart = _trim(raw)
        chart.save(out / "snd_pw_climo_base.png", optimize=True)
        if geo:
            k = raw.width / page.evaluate("document.querySelector('#line-chart svg').getBoundingClientRect().width")
            l, t = _trim_box(raw)
            (out / "snd_pw_climo_geo.json").write_text(json.dumps({
                "x": geo["x"] * k - l, "y0": geo["y0"] * k - t, "px_per_in": geo["y_per_in"] * k,
                "dot_d": geo["dot_d"] * k, "ymax": geo["ymax"], "date": now_local().strftime("%Y-%m-%d")}))
        from .ksc_sounding import star_chart
        star_chart(out)
        _table(date_label, vals).save(out / "snd_pw_table.png", optimize=True)
        return f"{date_label}: {' '.join(vals)}"
    finally:
        ctx.close()
