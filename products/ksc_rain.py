"""Highest 24-hour rainfall at KSC-side field-mill rain gauges, from the KSC
Spaceport Weather Archive 'Past 24 Hour' rainfall report."""
import html as htmlmod
import json
import re

from .common import get, now_utc

URL = "https://kscweather.ksc.nasa.gov/wxarchive/Rainfall/Past24hr"
# LPLWS field-mill gauges on the Kennedy Space Center side (Merritt Island and the
# barrier island north of CCSFS). Cape Canaveral SFS gauges (16, 26-34) and FM25
# (south Merritt Island, off KSC) are left out.
KSC_GAUGES = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 17, 18, 19, 20, 21, 22, 23, 24, 35}
OUT_NAME = "ksc_rain.json"


def _cells(row):
    return [htmlmod.unescape(re.sub(r"<[^>]+>", "", c)).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def build(out):
    page = get(URL).text
    table = re.search(r"<table.*?</table>", page, re.S)
    if not table:
        raise RuntimeError("rainfall table not found")
    best, n, wet = None, 0, 0
    for row in re.findall(r"<tr.*?</tr>", table.group(0), re.S):
        c = _cells(row)
        if len(c) < 3 or not c[0].isdigit():
            continue
        g = int(c[0])
        if g not in KSC_GAUGES:
            continue
        try:
            total = float(c[-1])
        except ValueError:
            continue
        if not 0 <= total < 30:
            continue
        n += 1
        if round(total, 2) > 0:
            wet += 1
        if best is None or total > best[0]:
            best = (total, g)
    result = {"updated": f"{now_utc():%Y-%m-%d %H:%MZ}", "gauges": n, "wet_gauges": wet}
    if best:
        result.update({"inches": round(best[0], 2), "gauge": best[1]})
        # a lone 0.01" tip at a single gauge is treated as no rain
        if wet == 1 and round(best[0], 2) == 0.01:
            result.update({"inches": 0.0, "lone_tip_gauge": best[1]})
            best = (0.0, best[1])
    (out / OUT_NAME).write_text(json.dumps(result, indent=1))
    if not best:
        raise RuntimeError("no KSC gauge totals in the report")
    return f'{best[0]:.2f}" at gauge {best[1]} ({n} KSC gauges reporting)'
