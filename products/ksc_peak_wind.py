"""Highest peak wind (gust) in the prior 24 hours from KSC-side weather towers,
taken from the KSC Spaceport Weather Archive tower search (all heights)."""
import csv
import datetime as dt
import io
import json
import re

import requests

from .common import UA, now_utc

BASE = "https://kscweather.ksc.nasa.gov"
FORM = BASE + "/wxarchive/WeatherTower"

# Tower sensor sites on the Kennedy Space Center side (Merritt Island and the
# barrier island north of CCSFS). Cape Canaveral SFS and mainland towers are left out.
KSC_SITES = {
    "64": "0011 (RSA)", "65": "0015", "67": "0019", "68": "0022",
    "74": "0211", "75": "0211 DROP PT", "78": "0311",
    "866": "0313 NE NE", "79": "0313 NE SW", "867": "0313 SW NE", "865": "0313 SW SW",
    "80": "0316 (RSA)", "86": "0412", "87": "0415", "88": "0418", "89": "0421",
    "90": "0506", "91": "0509", "92": "0511", "93": "0512", "94": "0513",
    "95": "0714", "97": "0805",
    "81": "39 A NW(60ft)", "82": "39 A SE(60ft)", "83": "39 B NW(60ft)", "84": "39 B SE(60ft)",
    "910": "LC39 A NW", "911": "LC39 A NE", "912": "LC39 A SE",
    "913": "LC39 B NE", "914": "LC39 B NW", "915": "LC39 B SW",
    "907": "VAB_IN1", "921": "Corrosion Lab",
}
OUT_NAME = "ksc_peak_wind.json"


def _form_fields(html):
    form = re.search(r'<form[^>]*action="[^"]*WeatherTower/Search"[^>]*>(.*?)</form>', html, re.S | re.I)
    if not form:
        raise RuntimeError("tower search form not found")
    fields = []
    for tag in re.findall(r"<input\b[^>]*>", form.group(1), re.I):
        name = re.search(r'\bname="([^"]+)"', tag)
        if not name:
            continue
        typ = (re.search(r'\btype="([^"]+)"', tag) or [None, "text"])[1].lower()
        val = re.search(r'\bvalue="([^"]*)"', tag)
        val = val.group(1) if val else ""
        if typ in ("radio", "checkbox") and "checked" not in tag.lower():
            continue
        if typ in ("submit", "button"):
            continue
        fields.append((name.group(1), val))
    fields.append(("btnSearch", "Search"))
    return fields


def build(out):
    end = now_utc().replace(second=0, microsecond=0)
    start = end - dt.timedelta(hours=24)
    s = requests.Session()
    s.headers.update(UA)
    page = s.get(FORM, timeout=60)
    page.raise_for_status()
    fields = [(k, v) for k, v in _form_fields(page.text) if k not in ("startDate", "startTime", "endDate", "endTime")]
    fields += [("startDate", f"{start:%m/%d/%Y}"), ("startTime", f"{start:%H:%M:%S}"),
               ("endDate", f"{end:%m/%d/%Y}"), ("endTime", f"{end:%H:%M:%S}")]
    fields += [("sites", v) for v in KSC_SITES]
    res = s.post(FORM + "/Search", data=fields, timeout=120)
    res.raise_for_status()
    ex = re.search(r'/wxarchive/WeatherTower/Export/[A-Za-z0-9]+', res.text)
    if not ex:
        raise RuntimeError("search returned no export link")
    data = s.get(BASE + ex.group(0), timeout=180)
    data.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(data.text)))
    best, n = None, 0
    for r in rows:
        try:
            v = float(r.get("Peak Wind Speed") or "nan")
        except ValueError:
            continue
        if not (0 <= v < 150):  # skip blanks and obviously bad values
            continue
        n += 1
        if best is None or v > best[0]:
            best = (v, r.get("SiteName", "").strip(), r.get("Height", "").strip(), r.get("Date", ""), r.get("Time", ""))
    result = {"window_start": f"{start:%Y-%m-%d %H:%MZ}", "window_end": f"{end:%Y-%m-%d %H:%MZ}",
              "reports": n, "updated": f"{now_utc():%Y-%m-%d %H:%MZ}"}
    if best:
        result.update({"kt": int(round(best[0])), "site": best[1], "height_ft": best[2], "time": f"{best[3]} {best[4]}"})
    (out / OUT_NAME).write_text(json.dumps(result, indent=1))
    if not best:
        return f"no peak-wind reports in window ({len(rows)} rows)"
    return f"{result['kt']} KT at {best[1]} {best[2]} ft {best[3]} {best[4]} ({n} reports)"
