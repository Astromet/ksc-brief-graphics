"""Melbourne (MLB) normal high/low for today, from the newest NWS Melbourne Climate
Report (CLI) — the 'THE MELBOURNE CLIMATE NORMALS FOR TODAY' block, as shown on
weather.gov/wrh/climate?wfo=mlb&tab=observed."""
import json
import re

from .common import get, now_utc

LIST = "https://api.weather.gov/products/types/CLI/locations/MLB"
OUT_NAME = "mlb_normals.json"


def parse(text):
    m = re.search(r"CLIMATE NORMALS FOR (TODAY|TOMORROW)(.*?)(?:\n\s*\n|SUNRISE)", text, re.S)
    if not m:
        return None
    blk = m.group(2)
    hi = re.search(r"MAXIMUM TEMPERATURE \(F\)\s+(-?\d+|MM)", blk)
    lo = re.search(r"MINIMUM TEMPERATURE \(F\)\s+(-?\d+|MM)", blk)
    if not hi or not lo or "MM" in (hi.group(1), lo.group(1)):
        return None
    issued = re.search(r"\n(\d{3,4} [AP]M E[SD]T \w{3} \w{3} +\d{1,2} \d{4})", text)
    return {"for": m.group(1).lower(), "normal_hi": int(hi.group(1)), "normal_lo": int(lo.group(1)),
            "issued": issued.group(1) if issued else ""}


def build(out):
    items = get(LIST).json().get("@graph", [])
    items.sort(key=lambda g: g.get("issuanceTime", ""), reverse=True)
    for g in items[:6]:
        text = get(g["@id"]).json().get("productText", "")
        res = parse(text)
        if res and res["for"] == "today":
            res["updated"] = f"{now_utc():%Y-%m-%d %H:%MZ}"
            (out / OUT_NAME).write_text(json.dumps(res, indent=1))
            return f"normal {res['normal_hi']}/{res['normal_lo']} F (CLI issued {res['issued']})"
    raise RuntimeError("no CLI with today's normals found")
