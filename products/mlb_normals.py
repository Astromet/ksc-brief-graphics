"""Melbourne (MLB) normal high/low for today, from the newest NWS Melbourne Climate
Report (CLI) — the 'THE MELBOURNE CLIMATE NORMALS FOR TODAY' block, as shown on
weather.gov/wrh/climate?wfo=mlb&tab=observed."""
import json
import re

from .common import get, now_utc

LIST = "https://api.weather.gov/products/types/CLI/locations/MLB"
OUT_NAME = "mlb_normals.json"


def parse(text):
    m = re.search(r"CLIMATE NORMALS FOR (TODAY|TOMORROW)(.*?)(?:\n[ \t]*\n|SUNRISE)", text, re.S)
    if not m:
        return None
    blk = m.group(2)
    hi = re.search(r"MAXIMUM TEMPERATURE \(F\)\s+(-?\d+|MM)", blk)
    lo = re.search(r"MINIMUM TEMPERATURE \(F\)\s+(-?\d+|MM)", blk)
    if not hi or not lo or "MM" in (hi.group(1), lo.group(1)):
        return None
    res = {}
    lines = blk.splitlines()
    for key, label in (("rec_hi", "MAXIMUM"), ("rec_lo", "MINIMUM")):
        for k, ln in enumerate(lines):
            mm = re.match(rf"\s*{label} TEMPERATURE \(F\)\s+\S+\s+(-?\d+)\s+(\d{{4}})", ln)
            if mm:
                years = [mm.group(2)]
                for nxt in lines[k + 1:]:  # tied years continue on the following lines
                    ty = re.fullmatch(r"\s+(\d{4})\s*", nxt)
                    if not ty:
                        break
                    years.append(ty.group(1))
                res[key] = int(mm.group(1))
                res[key + "_years"] = years
    issued = re.search(r"\n(\d{3,4} [AP]M E[SD]T \w{3} \w{3} +\d{1,2} \d{4})", text)
    return {"for": m.group(1).lower(), "normal_hi": int(hi.group(1)), "normal_lo": int(lo.group(1)),
            "issued": issued.group(1) if issued else "", **res}


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
