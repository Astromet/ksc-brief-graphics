"""Products captured from interactive web viewers:
  * TPW loop from the TPWViewer (KSC marker, inches) with CIMSS MIMIC-TPW2 fallback
  * SPC REFS member composite reflectivity, valid 18Z (4 members side by side)
"""
import datetime as dt

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
import io
import json
import re

from PIL import Image, ImageDraw

from .common import font, get, now_utc

# ====================================================================== TPW
TPW_URL = ("https://nluchetti1.github.io/TPWViewer/#dom=se&base=tpw&pal=nrl&units=in&ovl=none"
           "&span=24&op=1.00&mode=loop&fc=hrrr")
CIMSS_GIF = ("https://tropic.ssec.wisc.edu/real-time/mtpw2/webAnims/tpw_nrl_colors/global2/"
             "mimictpw_global2_latest.gif")
KSC = {"name": "KSC", "lat": 28.5729, "lon": -80.6490}
OUT_W, OUT_H = 800, 592
MAX_OBS_AGE_H = 6


def _save_gif(frames, path, ms=170, last_ms=1500):
    pal = [f.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT,
                                     dither=Image.Dither.NONE) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:],
                duration=[ms] * (len(pal) - 1) + [last_ms], loop=0, optimize=True)


def _tpw_viewer(out, browser):
    ctx = browser.new_context(viewport={"width": 1300, "height": 900}, device_scale_factor=1,
                              user_agent=BROWSER_UA)
    page = ctx.new_page()

    def patch_manifest(route):
        resp = route.fetch()
        man = resp.json()
        man["markers"] = [KSC]
        route.fulfill(response=resp, body=json.dumps(man), headers={**resp.headers, "content-type": "application/json"})

    page.route(re.compile(r".*/data/manifest\.json.*"), patch_manifest)
    try:
        page.goto(TPW_URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_function(
            "() => { const f = document.getElementById('frameinfo'); const l = document.getElementById('loading');"
            " return f && /^\\d+\\/\\d+$/.test(f.textContent.trim()) && (!l || getComputedStyle(l).display == 'none'); }",
            timeout=180000)
        page.wait_for_timeout(3000)
        info = re.search(r"Latest MIMIC[^\n]*", page.inner_text("body"))
        m = re.search(r"(\d+)\s*h old", info.group(0)) if info else None
        if m and int(m.group(1)) > MAX_OBS_AGE_H:
            raise RuntimeError(f"TPWViewer data stale: {info.group(0)}")
        if "KSC" not in page.inner_text("#marks"):
            raise RuntimeError("KSC marker not applied")
        # pause playback
        if "h3.5" in (page.get_attribute("#playicon path", "d") or ""):
            page.click("#play")
            page.wait_for_timeout(300)

        def pos():
            a, b = page.inner_text("#frameinfo").strip().split("/")
            return int(a), int(b)

        i, n = pos()
        for _ in range(n):
            if pos()[0] == 1:
                break
            page.click("#next")
            page.wait_for_timeout(120)
        clock = page.locator("#clock").bounding_box()
        stage = page.locator("#stage").bounding_box()
        y0 = clock["y"] - 4
        x0 = min(clock["x"], stage["x"]) - 2
        clip = {"x": x0, "y": y0, "width": stage["x"] + stage["width"] - x0,
                "height": stage["y"] + stage["height"] - y0}
        # blank the header band to the right of the clock (status text etc.)
        band = (round(clock["x"] + clock["width"] - x0 + 10), 0, round(clip["width"]), round(stage["y"] - y0 - 1))
        frames = []
        for k in range(n):
            page.wait_for_timeout(450)
            png = page.screenshot(clip=clip)
            fr = Image.open(io.BytesIO(png)).convert("RGB")
            if band[2] > band[0] and band[3] > 0:
                ImageDraw.Draw(fr).rectangle(band, fill=fr.getpixel((band[0], 2)))
            frames.append(fr.resize((OUT_W, OUT_H), Image.LANCZOS))
            page.click("#next")
        _save_gif(frames, out / "tpw_loop.gif")
        return f"TPWViewer {n} frames; {info.group(0) if info else ''}"
    finally:
        ctx.close()


def _tpw_cimss(out):
    src = Image.open(io.BytesIO(get(CIMSS_GIF).content))
    frames = []
    f_b = font(20, bold=True)
    for k in range(getattr(src, "n_frames", 1)):
        src.seek(k)
        fr = src.convert("RGB")
        fr = fr.resize((OUT_W, round(fr.height * OUT_W / fr.width)), Image.LANCZOS)
        canvas = Image.new("RGB", (OUT_W, OUT_H), (11, 31, 51))
        canvas.paste(fr, (0, (OUT_H - fr.height) // 2 + 20))
        d = ImageDraw.Draw(canvas)
        d.text((14, 14), "BACKUP: CIMSS MIMIC-TPW2 (mm) - TPWViewer unavailable", font=f_b, fill=(255, 181, 71))
        frames.append(canvas)
    _save_gif(frames, out / "tpw_loop.gif", ms=120)
    return f"CIMSS fallback, {len(frames)} frames"


def tpw(out, browser):
    try:
        return _tpw_viewer(out, browser)
    except Exception as e:  # noqa: BLE001
        print(f"  TPWViewer failed ({e}); using CIMSS MIMIC-TPW2 fallback")
        return _tpw_cimss(out) + f" (viewer error: {e})"


# ====================================================================== REFS
REFS = "https://www.spc.noaa.gov/exper/refs/viewer/"
# map center chosen so the cropped panel matches the deck's KSC-centered view
REFS_VIEW = "-80.8200:28.5000:6.87"
MEMBERS = [("HRRR", 0), ("HRRR -12h", 12), ("RRFS Ctl", 0), ("RRFS Ctl -12h", 12)]
DISPLAY = {"HRRR": "HRRR", "HRRR -12h": "HRRR −12h", "RRFS Ctl": "RRFS Ctl", "RRFS Ctl -12h": "RRFS Ctl −12h"}
VW, VH = 800, 1048
CROP = (96, 84, 800, 978)  # css px: drops the colorbar and header; 704 x 894


def _refs_compose(panels, cycle, valid, out):
    # layout mirrors the slide: 4 panels 2647000 EMU wide, 120000 gaps, at 5000 EMU/px
    S = 5000
    pw, ph, gap = 2647000 // S, 3361000 // S, 120000 // S
    W = 4 * pw + 3 * gap
    lab_h, pan_y, src_y = 460000 // S, 500000 // S, (5274000 - 1250000) // S
    H = src_y + 300000 // S
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    f1, f2, f3 = font(38, bold=True), font(25), font(22)
    vtxt = valid.strftime("%a %d %b")
    for k, ((name, lag), pan) in enumerate(zip(MEMBERS, panels)):
        x = k * (pw + gap)
        run = cycle - dt.timedelta(hours=lag)
        fh = int((valid - run).total_seconds() // 3600)
        t1, t2 = DISPLAY[name], f"{run:%H}Z run (F{fh:02d}) · Valid 18Z {vtxt}"
        for txt, f, col, yb in ((t1, f1, (31, 42, 68), lab_h - 34), (t2, f2, (64, 64, 64), lab_h)):
            l, t, r, b = d.textbbox((0, 0), txt, font=f)
            d.text((x + (pw - (r - l)) / 2 - l, yb - (b - t) - t), txt, font=f, fill=col)
        im.paste(pan.resize((pw, ph), Image.LANCZOS), (x, pan_y))
        d.rectangle([x, pan_y, x + pw - 1, pan_y + ph - 1], outline=(127, 127, 127), width=2)
    src = (f"Composite Reflectivity valid 18Z {valid:%a %d %b %Y} · REFS {cycle:%H}Z cycle · "
           f"Source: SPC REFS Ensemble Viewer (spc.noaa.gov/exper/refs/viewer) · "
           f"Updated {now_utc():%H%MZ}")
    d.text((0, H - 34), src, font=f3, fill=(89, 89, 89))
    im.save(out / "refs_18z.png", optimize=True)


def refs(out, browser):
    ctx = browser.new_context(viewport={"width": VW, "height": VH}, device_scale_factor=2, user_agent=BROWSER_UA)
    page = ctx.new_page()
    try:
        page.goto(f"{REFS}#viewport={REFS_VIEW}&fieldset=members:cref", wait_until="domcontentloaded",
                  timeout=120000)
        msgs = []
        codes = {}

        def on_resp(r):
            if "/data/" in r.url or ".zarr" in r.url:
                codes[r.status] = codes.get(r.status, 0) + 1
                if r.status >= 400 and len(msgs) < 40:
                    msgs.append(f"{r.status} {r.url[-90:]}")
        ctx.on("response", on_resp)
        page.on("console", lambda m: msgs.append(f"{m.type}: {m.text}"[:200]))
        page.on("pageerror", lambda e: msgs.append(f"pageerror: {e}"[:200]))
        try:
            page.wait_for_function("() => { const t = document.querySelector('.mpv-time');"
                                   " const c = document.querySelector('.cal-text');"
                                   " return t && c && /\\(F\\d+\\)/.test(t.textContent) && /\\d{2}Z/.test(c.value); }",
                                   timeout=120000)
        except Exception:
            page.screenshot(path=str(out / "debug_refs.png"))
            webgl = page.evaluate("() => !!document.createElement('canvas').getContext('webgl2')")
            raise RuntimeError(f"REFS viewer did not initialise (webgl2={webgl}); "
                               f"text={page.inner_text('body')[:200]!r}; console={msgs[-6:]}")
        page.wait_for_timeout(12000)
        gl = page.evaluate("""() => { const g = document.createElement('canvas').getContext('webgl2');
            if (!g) return 'no webgl2'; const d = g.getExtension('WEBGL_debug_renderer_info');
            return [d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : '?',
                    !!g.getExtension('EXT_color_buffer_float'), !!g.getExtension('OES_texture_float_linear')].join(' '); }""")
        msgs.append(f"GL: {gl}")
        cyc_txt = page.eval_on_selector(".cal-text", "e => e.value")  # e.g. 2026-10-31 12Z
        cycle = dt.datetime.strptime(cyc_txt.strip(), "%Y-%m-%d %HZ").replace(tzinfo=dt.timezone.utc)
        valid = cycle.replace(hour=18)
        target_f = int((valid - cycle).total_seconds() // 3600)

        def key(k, times=1):
            for _ in range(times):
                page.evaluate("k => window.dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true}))", k)
                page.wait_for_timeout(120)

        def fhour():
            return int(re.search(r"\(F(\d+)\)", page.inner_text(".mpv-time")).group(1))

        for _ in range(80):
            f = fhour()
            if f == target_f:
                break
            key("ArrowRight" if f < target_f else "ArrowLeft")
        if fhour() != target_f or "18Z" not in page.inner_text(".mpv-time"):
            raise RuntimeError(f"could not set forecast hour: {page.inner_text('.mpv-time')}")

        def member():
            return page.eval_on_selector(".mpv-field-header", "e => e.parentElement.innerText") \
                .replace("Member:", "").replace("▼", "").strip()

        panels = []
        for name, _ in MEMBERS:
            for _ in range(16):
                if member() == name:
                    break
                key("ArrowDown")
                page.wait_for_timeout(400)
            if member() != name:
                raise RuntimeError(f"member {name!r} not found (at {member()!r})")
            page.wait_for_timeout(20000)
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(1500)
            png = page.screenshot()
            shot = Image.open(io.BytesIO(png)).convert("RGB")
            s = shot.width / VW
            panels.append(shot.crop(tuple(round(v * s) for v in CROP)))
        _refs_compose(panels, cycle, valid, out)
        return f"cycle {cycle:%d/%HZ} F{target_f:02d}; data responses {codes}; {msgs[-8:]}"
    finally:
        ctx.close()
