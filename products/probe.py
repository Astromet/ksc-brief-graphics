"""Debug: which launch-schedule sites list Sunday's launch."""
import json
import re

from .common import get

URLS = {
    "ll2_api": "https://ll.thespacedevs.com/2.3.0/launches/upcoming/?location__ids=12,27&limit=25&mode=list",
    "rocketlaunch_live_api": "https://fdo.rocketlaunch.live/json/launches/next/5",
    "rocketlaunch_live": "https://www.rocketlaunch.live/?filter=florida",
    "nextspaceflight": "https://nextspaceflight.com/launches/",
    "spacelaunchnow": "https://spacelaunchnow.app/launch/upcoming/florida",
    "spaceflightnow": "https://spaceflightnow.com/launch-schedule/",
    "rocketlaunch_org": "https://rocketlaunch.org/launch-schedule",
    "floridatoday": "https://www.floridatoday.com/launches/",
    "spacecoastlaunches": "https://www.spacecoastlaunches.com/launch-list.php",
    "ksc_visitor": "https://www.kennedyspacecenter.com/launches-and-events",
    "spacelaunchschedule": "https://www.spacelaunchschedule.com/category/florida/",
}
PAT = re.compile(r"(Nov(?:ember)?\.?\s*29|11/29|2026-11-29|29\s*Nov)", re.I)


def run(out):
    lines = []
    for k, u in URLS.items():
        try:
            r = get(u, tries=1, timeout=40)
            txt = r.text
            (out / f"probe_{k}.txt").write_text(txt)
            hits = []
            for m in PAT.finditer(txt):
                s = re.sub(r"<[^>]+>", " ", txt[max(0, m.start() - 300):m.end() + 300])
                hits.append(re.sub(r"\s+", " ", s)[:400])
            lines.append(f"== {k}: {r.status_code} {len(txt)} chars, {len(hits)} hits")
            lines += ["   " + h for h in hits[:4]]
        except Exception as e:  # noqa: BLE001
            lines.append(f"== {k}: FAILED {e}")
    (out / "probe.txt").write_text("\n".join(lines))
    return f"{len(URLS)} checked"
