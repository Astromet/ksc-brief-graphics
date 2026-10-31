# KSC Morning Weather Briefing graphics

A scheduled GitHub Action (every 30 minutes) rebuilds the auto-updating images used by the
KSC Morning Weather Briefing PowerPoint and publishes them with GitHub Pages at
`https://astromet.github.io/ksc-brief-graphics/<file>`. The deck links to those addresses, so
opening it pulls the latest images.

| File | Slide | What it is |
|---|---|---|
| `tpw_loop.gif` | Precipitable Water | TPWViewer 24-h loop (inches, KSC marker); falls back to CIMSS MIMIC-TPW2 if the viewer fails or its data is >6 h old |
| `refs_18z.png` | Modeled Future Radar | SPC REFS composite reflectivity valid 18Z: HRRR, HRRR −12h, RRFS Ctl, RRFS Ctl −12h |
| `goes19_se_2h.gif` | Satellite & Radar | GOES-19 SE GeoColor, last 2 hours |
| `nws_mlb_lead.png` | Tidbits | Lead graphicast on weather.gov/mlb |
| `snd_pw_climo.png`, `snd_pw_table.png` | 10Z KXMR Balloon Sounding | SPC sounding climatology (XMR, PW) + today's 12Z data readout |
| `meteogram_gfs.png`, `meteogram_ecmwf.png` | 7-Day Meteograms | Time-height sections for KXMR with NOW line (Open-Meteo data) |
| `precip_ltg_climo_now.png` | Precipitation & Lightning Climatology | 45 WS climatology with NOW line |
| `tc_activity_now.png` | Tropical Cyclone Climatology | NHC activity chart with NOW! line |
| `tc_origin_current.png` | Tropical Cyclone Climatology | NHC 10-day points-of-origin map for the current period |

Status of every product (last good update, errors): `https://astromet.github.io/ksc-brief-graphics/`.
If a source is down, the last good image stays in place.

Run by hand: **Actions → Update briefing graphics → Run workflow**.
