"""Build a ready-to-present copy of the briefing deck with every linked picture's
current image saved inside it.

The template (assets/deck_template.pptx) keeps its links, so the downloaded copy
still refreshes itself when PowerPoint is allowed to; the embedded images just
make it current even when links are blocked or the computer is offline.
"""
import io
import posixpath
import re
import zipfile

from PIL import Image

import datetime as dt
from email.utils import parsedate_to_datetime

import requests

from .common import ASSETS, UA, get, now_local

BASE = "https://astromet.github.io/ksc-brief-graphics/"
OUT_NAME = "KSC_Morning_Brief.pptx"
REL_RE = re.compile(r"<Relationship\b[^>]*?/>")
BLIP_RE = re.compile(r'<a:blip r:embed="([^"]+)" r:link="([^"]+)"')
LINK_ONLY_RE = re.compile(r'<a:blip r:link="([^"]+)"')
IMG_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
FMT = {".png": "PNG", ".gif": "GIF", ".jpg": "JPEG", ".jpeg": "JPEG"}


def _attr(tag, name):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m.group(1) if m else None


# ---------------------------------------------------------------- GFS map slides
GFS_RE = re.compile(r"https://mag\.ncep\.noaa\.gov/data/gfs/(\d{2})/west-atl/10m_wnd_precip/"
                    r"gfs_west-atl_(\d{3})_10m_wnd_precip\.gif")
GFS_URL = ("https://mag.ncep.noaa.gov/data/gfs/{cc:02d}/west-atl/10m_wnd_precip/"
           "gfs_west-atl_{fff:03d}_10m_wnd_precip.gif")
WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"


def _gfs_run(day):
    """Newest GFS run on MAG that can show 18Z on `day` (UTC date): (init datetime, cycle hour)."""
    v18 = dt.datetime(day.year, day.month, day.day, 18, tzinfo=dt.timezone.utc)
    for back in range(0, 30, 6):
        init = (v18 - dt.timedelta(hours=6 + back)).replace(minute=0)
        init = init.replace(hour=init.hour - init.hour % 6)
        url = GFS_URL.format(cc=init.hour, fff=int((v18 - init).total_seconds() // 3600))
        try:
            r = requests.head(url, headers=UA, timeout=30, allow_redirects=True)
            mod = parsedate_to_datetime(r.headers["Last-Modified"])
        except Exception:  # noqa: BLE001
            continue
        if r.status_code == 200 and init + dt.timedelta(hours=2) <= mod <= init + dt.timedelta(hours=20):
            return init
    return None


def _gfs_slides(files, order):
    """Point each GFS map at the newest run's image valid 18Z on its day, and retitle the slides."""
    gfs = []
    for name in order:
        rels_name = posixpath.join("ppt/slides/_rels", posixpath.basename(name) + ".rels")
        rels = files.get(rels_name, b"").decode("utf-8")
        if GFS_RE.search(rels):
            gfs.append((name, rels_name))
    if not gfs:
        return "no GFS slides"
    today = now_local().date()
    init = _gfs_run(today)
    for i, (name, rels_name) in enumerate(gfs):
        day = today + dt.timedelta(days=i)
        label = "This Afternoon" if i == 0 else "Tomorrow Afternoon" if i == 1 else f"{day:%A} Afternoon"
        xml = files[name].decode("utf-8")
        xml = re.sub(rf"(GFS Model\s*:\s*)(?:This|Tomorrow|{WEEKDAYS}) Afternoon", rf"\g<1>{label}", xml, count=1)
        files[name] = xml.encode("utf-8")
        if init:
            v18 = dt.datetime(day.year, day.month, day.day, 18, tzinfo=dt.timezone.utc)
            fff = int((v18 - init).total_seconds() // 3600)
            rels = files[rels_name].decode("utf-8")
            files[rels_name] = GFS_RE.sub(GFS_URL.format(cc=init.hour, fff=fff), rels).encode("utf-8")
    return f"GFS {init:%d/%HZ} run" if init else "GFS run not verified; kept links"


def _slide_order(files):
    pres = files["ppt/presentation.xml"].decode("utf-8")
    rels = files["ppt/_rels/presentation.xml.rels"].decode("utf-8")
    tgt = {_attr(t, "Id"): _attr(t, "Target") for t in REL_RE.findall(rels)}
    return ["ppt/" + tgt[r] for r in re.findall(r'<p:sldId [^>]*r:id="([^"]+)"', pres)]


def _peak_wind(files, out):
    """Write the KSC peak wind into the slide whose table has the 'KSC Peak Wind' row."""
    import json
    value = "M"
    try:
        pw = json.loads((out / "ksc_peak_wind.json").read_text())
        upd = dt.datetime.strptime(pw["updated"], "%Y-%m-%d %H:%MZ").replace(tzinfo=dt.timezone.utc)
        if "kt" in pw and dt.datetime.now(dt.timezone.utc) - upd < dt.timedelta(hours=3):
            value = f"{pw['kt']} KT"
    except Exception:  # noqa: BLE001
        pass
    temps = "M/M F"
    try:
        if dt.datetime.now(dt.timezone.utc) - upd < dt.timedelta(hours=3) and "tmax_f" in pw:
            temps = f"{pw['tmax_f']}/{pw['tmin_f']} F"
    except Exception:  # noqa: BLE001
        pass
    for name in [n for n in files if re.match(r"ppt/slides/slide\d+\.xml$", n)]:
        xml = files[name].decode("utf-8")
        if "Max/Min" in xml:
            xml = re.sub(r"(<a:t>)xx/xx F(</a:t>)", lambda m: f"{m.group(1)}{temps}{m.group(2)}", xml, count=1)
            files[name] = xml.encode("utf-8")
        if "Peak Wind" not in xml:
            continue
        new, c = re.subn(r"(<a:t>)xx KT(</a:t>)", lambda m: f"{m.group(1)}{value}{m.group(2)}", xml, count=1)
        if c:
            files[name] = new.encode("utf-8")
            return f"{value}, temps {temps}"
    return value + " (cell not found)"


def _convert(data, ext):
    """Return image bytes in the format implied by ext (keeps animation for GIF)."""
    im = Image.open(io.BytesIO(data))
    want = FMT.get(ext)
    if want is None or im.format == want:
        return data
    buf = io.BytesIO()
    if want == "GIF" and getattr(im, "n_frames", 1) > 1:
        im.save(buf, "GIF", save_all=True, loop=0)
    elif want == "JPEG":
        im.convert("RGB").save(buf, "JPEG", quality=90)
    else:
        im.seek(0)
        im.convert("RGBA" if want == "PNG" else "RGB").save(buf, want)
    return buf.getvalue()


def build(out):
    src = zipfile.ZipFile(ASSETS / "deck_template.pptx")
    files = {n: src.read(n) for n in src.namelist()}
    cache, ok, failed = {}, 0, []
    gfs_note = _gfs_slides(files, _slide_order(files))

    def fetch(url):
        if url not in cache:
            try:
                if url.startswith(BASE):
                    data = (out / url[len(BASE):].split("?")[0]).read_bytes()
                else:
                    data = get(url, tries=2, timeout=40).content
                Image.open(io.BytesIO(data)).verify()
                cache[url] = data
            except Exception as e:  # noqa: BLE001
                cache[url] = None
                failed.append(f"{url.rsplit('/', 1)[-1]}: {type(e).__name__}")
        return cache[url]

    for name in sorted(n for n in files if re.match(r"ppt/slides/slide\d+\.xml$", n)):
        rels_name = posixpath.join(posixpath.dirname(name), "_rels", posixpath.basename(name) + ".rels")
        if rels_name not in files:
            continue
        xml = files[name].decode("utf-8")
        rels = files[rels_name].decode("utf-8")
        tags = {_attr(t, "Id"): t for t in REL_RE.findall(rels)}
        slide_no = re.search(r"slide(\d+)\.xml", name).group(1)
        for embed_id, link_id in BLIP_RE.findall(xml):
            etag, ltag = tags.get(embed_id), tags.get(link_id)
            if not etag or not ltag or _attr(ltag, "TargetMode") != "External":
                continue
            data = fetch(_attr(ltag, "Target").replace("&amp;", "&"))
            if data is None:
                continue
            old = _attr(etag, "Target")
            ext = posixpath.splitext(old)[1].lower()
            try:
                data = _convert(data, ext)
            except Exception as e:  # noqa: BLE001
                failed.append(f"convert {old}: {e}")
                continue
            # give every picture its own media file (some fallbacks are shared)
            new = f"../media/live_s{slide_no}_{embed_id}{ext}"
            files[posixpath.normpath(posixpath.join("ppt/slides", new))] = data
            new_tag = etag.replace(f'Target="{old}"', f'Target="{new}"')
            rels = rels.replace(etag, new_tag)
            tags[embed_id] = new_tag
            ok += 1
        # pictures that are link-only (no saved image): add an embedded copy
        added = {}
        for link_id in sorted(set(LINK_ONLY_RE.findall(xml))):
            ltag = tags.get(link_id)
            if not ltag or _attr(ltag, "TargetMode") != "External":
                continue
            data = fetch(_attr(ltag, "Target").replace("&amp;", "&"))
            if data is None:
                continue
            ext = {"PNG": ".png", "GIF": ".gif", "JPEG": ".jpg"}.get(Image.open(io.BytesIO(data)).format)
            if not ext:
                continue
            new_id = f"rIdLive{link_id}"
            target = f"../media/live_s{slide_no}_{new_id}{ext}"
            files[posixpath.normpath(posixpath.join("ppt/slides", target))] = data
            rels = rels.replace("</Relationships>", f'<Relationship Id="{new_id}" Type="{IMG_REL}" '
                                                    f'Target="{target}"/></Relationships>')
            added[link_id] = new_id
            ok += 1
        if added:
            xml = LINK_ONLY_RE.sub(lambda m: f'<a:blip r:embed="{added[m.group(1)]}" r:link="{m.group(1)}"'
                                   if m.group(1) in added else m.group(0), xml)
            files[name] = xml.encode("utf-8")
        files[rels_name] = rels.encode("utf-8")

    # title slide date
    s1 = "ppt/slides/slide1.xml"
    today = now_local()
    files[s1] = re.sub(rf"<a:t>\d{{1,2}} (?:{MONTHS}) \d{{4}}</a:t>".encode(),
                       f"<a:t>{today.day} {today:%B %Y}</a:t>".encode(), files[s1], count=1)

    # KSC peak wind (prior 24 h, KSC-side towers) into the observations table; "M" if missing
    peak_note = _peak_wind(files, out)

    # drop media no longer referenced by any relationship
    used = set()
    for n, b in files.items():
        if n.endswith(".rels"):
            base = posixpath.dirname(posixpath.dirname(n))
            for t in REL_RE.findall(b.decode("utf-8", "ignore")):
                if _attr(t, "TargetMode") != "External" and _attr(t, "Target"):
                    used.add(posixpath.normpath(posixpath.join(base, _attr(t, "Target"))))
    for n in [n for n in files if n.startswith("ppt/media/") and n not in used]:
        del files[n]

    ct = files["[Content_Types].xml"].decode("utf-8")
    for ext, mime in (("png", "image/png"), ("gif", "image/gif"), ("jpg", "image/jpeg")):
        if f'Extension="{ext}"' not in ct:
            ct = ct.replace("<Default ", f'<Default Extension="{ext}" ContentType="{mime}"/><Default ', 1)
    files["[Content_Types].xml"] = ct.encode("utf-8")

    order = ["[Content_Types].xml"] + [n for n in files if n != "[Content_Types].xml"]
    tmp = out / (OUT_NAME + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n in order:
            z.writestr(n, files[n], compress_type=zipfile.ZIP_STORED if n.endswith((".gif", ".png", ".jpg", ".jpeg"))
                       else zipfile.ZIP_DEFLATED)
    tmp.replace(out / OUT_NAME)
    note = f"{ok} pictures refreshed; {gfs_note}; peak wind {peak_note}"
    if failed:
        note += f"; kept previous image for: {', '.join(failed[:8])}"
    return note
