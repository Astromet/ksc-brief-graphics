// GFS time-height meteogram (RH shaded green, isotherms, wind barbs) from Open-Meteo GFS data.
async function buildMeteogram(opts) {
  const o = Object.assign({ lat: 28.4676, lon: -80.5668, site: 'KXMR', name: 'Cape Canaveral SFS', days: 7, W: 1600, H: 900, model: 'gfs' }, opts || {});
  const M = o.model === 'ecmwf'
    ? { label: 'ECMWF', api: 'ecmwf', mdl: 'ecmwf_ifs025', meta: 'ecmwf_ifs025', src: 'ECMWF IFS 0.25° open data', L: [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150] }
    : { label: 'GFS', api: 'gfs', mdl: 'gfs_global', meta: 'ncep_gfs025', src: 'NOAA GFS 0.25°', L: [1000, 975, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 350, 300, 250, 200, 150] };
  const L = M.L;
  const ISO = [5, -5, -10, -15, -20];
  const V = ['temperature', 'relative_humidity', 'wind_speed', 'wind_direction', 'geopotential_height'];
  const hourly = V.flatMap(v => L.map(l => `${v}_${l}hPa`)).join(',');
  const url = `https://api.open-meteo.com/v1/${M.api}?latitude=${o.lat}&longitude=${o.lon}&hourly=${hourly}&models=${M.mdl}&forecast_days=${o.days + 1}&wind_speed_unit=kn&timezone=GMT`;
  let d = null, lastErr = '';
  for (let k = 0; k < 4 && !d; k++) {
    if (k) await new Promise(r => setTimeout(r, 10000 * k));
    try {
      const ac = new AbortController(); const tm = setTimeout(() => ac.abort(), 60000);
      const r = await fetch(url, {cache: 'no-store', signal: ac.signal}); const t = await r.text(); clearTimeout(tm);
      try { const j = JSON.parse(t); if (j.error) lastErr = `HTTP ${r.status}: ${j.reason}`; else d = j; }
      catch (e) { lastErr = `HTTP ${r.status}: ${t.slice(0, 160)}`; }
    } catch (e) { lastErr = String(e); }
  }
  if (!d) throw new Error(`Open-Meteo ${M.api} failed after retries - ${lastErr}`);
  if (d.error) throw new Error(d.reason || 'Open-Meteo error');
  let run = null;
  try { const ac2 = new AbortController(); setTimeout(() => ac2.abort(), 30000); const m = await fetch(`https://api.open-meteo.com/data/${M.meta}/static/meta.json`, {signal: ac2.signal}).then(r => r.json()); run = new Date(m.last_run_initialisation_time * 1000); } catch (e) {}
  // 3-hourly from run time (or start of day) for `days` days
  const times = d.hourly.time.map(t => new Date(t + ':00Z'));
  const t0 = run ? run.getTime() : times[0].getTime();
  const idx = [];
  times.forEach((t, i) => { const dt = (t.getTime() - t0) / 3600e3; if (dt >= 0 && dt <= o.days * 24 && t.getUTCHours() % 3 === 0 && d.hourly[`temperature_850hPa`][i] != null) idx.push(i); });
  const T = idx.map(i => times[i]);
  const g = v => L.map(l => idx.map(i => d.hourly[`${v}_${l}hPa`][i]));
  const F = { t: g('temperature'), rh: g('relative_humidity'), ws: g('wind_speed'), wd: g('wind_direction'), z: g('geopotential_height') };

  const cv = document.createElement('canvas'); cv.width = o.W; cv.height = o.H;
  const c = cv.getContext('2d');
  c.fillStyle = '#fff'; c.fillRect(0, 0, o.W, o.H);
  const X0 = 70, X1 = o.W - 95, Y0 = 62, Y1 = o.H - 70;
  const nT = T.length, nL = L.length;
  const xOf = j => X0 + (X1 - X0) * j / (nT - 1);
  const lp = p => Math.log(p);
  const yOfP = p => Y1 - (Y1 - Y0) * (lp(1000) - lp(p)) / (lp(1000) - lp(150));
  // fractional level index -> pressure (interpolate in log p)
  const pOfK = k => { const a = Math.floor(Math.min(k, nL - 2)), f = k - a; return Math.exp(lp(L[a]) + (lp(L[a + 1]) - lp(L[a])) * f); };
  const kOfY = y => { // invert yOfP then find fractional level
    const p = Math.exp(lp(1000) - (Y1 - y) / (Y1 - Y0) * (lp(1000) - lp(150)));
    for (let a = 0; a < nL - 1; a++) if (p <= L[a] && p >= L[a + 1]) return a + (lp(L[a]) - lp(p)) / (lp(L[a]) - lp(L[a + 1]));
    return p > 1000 ? 0 : nL - 1;
  };
  const bil = (A, k, j) => { // A[level][time]
    const a = Math.max(0, Math.min(nL - 2, Math.floor(k))), b = Math.max(0, Math.min(nT - 2, Math.floor(j)));
    const fk = k - a, fj = j - b;
    const v00 = A[a][b], v01 = A[a][b + 1], v10 = A[a + 1][b], v11 = A[a + 1][b + 1];
    if ([v00, v01, v10, v11].some(v => v == null)) return null;
    return v00 * (1 - fk) * (1 - fj) + v01 * (1 - fk) * fj + v10 * fk * (1 - fj) + v11 * fk * fj;
  };

  // --- RH shading (raster, bilinear) ---
  const img = c.getImageData(X0, Y0, X1 - X0 + 1, Y1 - Y0 + 1);
  const cols = [[255, 255, 255], [152, 222, 140], [86, 180, 82], [40, 120, 50]]; // <70, 70-80, 80-90, >=90
  const kRow = []; for (let y = Y0; y <= Y1; y++) kRow.push(kOfY(y));
  for (let yy = 0; yy <= Y1 - Y0; yy++) {
    const k = kRow[yy];
    for (let xx = 0; xx <= X1 - X0; xx++) {
      const j = xx / (X1 - X0) * (nT - 1);
      const v = bil(F.rh, k, j); const cl = v == null ? 0 : v >= 90 ? 3 : v >= 80 ? 2 : v >= 70 ? 1 : 0;
      const p = (yy * img.width + xx) * 4; const col = cols[cl];
      img.data[p] = col[0]; img.data[p + 1] = col[1]; img.data[p + 2] = col[2]; img.data[p + 3] = 255;
    }
  }
  c.putImageData(img, X0, Y0);

  // --- marching squares contour lines on refined grid ---
  const R = 4, gk = (nL - 1) * R + 1, gj = (nT - 1) * R + 1;
  const grid = A => { const G = []; for (let a = 0; a < gk; a++) { const row = []; for (let b = 0; b < gj; b++) row.push(bil(A, a / R, b / R)); G.push(row); } return G; };
  const px = (a, b) => [xOf(b / R), yOfP(pOfK(a / R))];
  function contour(G, lev) {
    const segs = [];
    for (let a = 0; a < gk - 1; a++) for (let b = 0; b < gj - 1; b++) {
      const v = [G[a][b], G[a][b + 1], G[a + 1][b + 1], G[a + 1][b]];
      if (v.some(x => x == null)) continue;
      const P = [[a, b], [a, b + 1], [a + 1, b + 1], [a + 1, b]];
      const pts = [];
      for (let e = 0; e < 4; e++) {
        const v1 = v[e], v2 = v[(e + 1) % 4];
        if ((v1 < lev) !== (v2 < lev)) { const f = (lev - v1) / (v2 - v1); const p1 = P[e], p2 = P[(e + 1) % 4]; pts.push(px(p1[0] + (p2[0] - p1[0]) * f, p1[1] + (p2[1] - p1[1]) * f)); }
      }
      if (pts.length >= 2) segs.push([pts[0], pts[1]]);
      if (pts.length === 4) segs.push([pts[2], pts[3]]);
    }
    return segs;
  }
  const strokeSegs = (segs, color, w, dash) => { c.save(); c.strokeStyle = color; c.lineWidth = w; c.setLineDash(dash || []); c.beginPath(); for (const [p, q] of segs) { c.moveTo(p[0], p[1]); c.lineTo(q[0], q[1]); } c.stroke(); c.restore(); };
  c.save(); c.beginPath(); c.rect(X0, Y0, X1 - X0, Y1 - Y0); c.clip();
  const GR = grid(F.rh); for (const lev of [70, 80, 90]) strokeSegs(contour(GR, lev), '#1d5a26', 1);
  // isotherms
  const GT = grid(F.t);
  for (const lev of ISO) strokeSegs(contour(GT, lev), '#d7191c', 1.4, [7, 5]);
  strokeSegs(contour(GT, 0), '#1f3fd6', 2.2);
  c.restore();
  // isotherm labels: every 12 columns, label where T crosses each 5C value
  c.font = '12px Arial'; c.textAlign = 'center'; c.textBaseline = 'middle';
  for (let j = 4; j < nT - 1; j += 12) {
    for (let a = 0; a < nL - 1; a++) {
      const t1 = F.t[a][j], t2 = F.t[a + 1][j]; if (t1 == null || t2 == null) continue;
      const lo = Math.min(t1, t2), hi = Math.max(t1, t2);
      for (const lev of [5, 0, -5, -10, -15, -20]) {
        if (lev < lo || lev > hi || (lev === hi && lev === lo)) continue;
        const f = (lev - t1) / (t2 - t1); const y = yOfP(Math.exp(lp(L[a]) + (lp(L[a + 1]) - lp(L[a])) * f)); const x = xOf(j);
        const s = lev > 0 ? '+' + lev : String(lev); const w = c.measureText(s).width + 4;
        c.fillStyle = 'rgba(255,255,255,0.85)'; c.fillRect(x - w / 2, y - 7, w, 14);
        c.fillStyle = lev === 0 ? '#1f3fd6' : '#d7191c'; c.fillText(s, x, y);
      }
    }
  }
  // time grid
  c.strokeStyle = 'rgba(0,0,0,0.35)'; c.lineWidth = 1;
  T.forEach((t, j) => { if (t.getUTCHours() % 6 === 0) { c.beginPath(); c.moveTo(xOf(j), Y0); c.lineTo(xOf(j), Y1); c.stroke(); } });
  // wind barbs every 6h, every level
  const barbColor = s => s >= 60 ? '#7b2fbe' : s >= 40 ? '#c8102e' : s >= 20 ? '#f07800' : '#111';
  function barb(x, y, spd, dir) {
    const col = barbColor(spd); c.save(); c.strokeStyle = col; c.fillStyle = col; c.lineWidth = 1.4;
    const len = 26, th = (dir) * Math.PI / 180; // staff points toward where wind comes FROM
    const ux = Math.sin(th), uy = -Math.cos(th);
    const ex = x + ux * len, ey = y + uy * len;
    if (spd < 2.5) { c.beginPath(); c.arc(x, y, 3.5, 0, 2 * Math.PI); c.stroke(); c.restore(); return; }
    c.beginPath(); c.moveTo(x, y); c.lineTo(ex, ey); c.stroke();
    // feathers on the clockwise side (NH)
    const fx = -uy, fy = ux; // perpendicular
    let s = Math.round(spd / 5) * 5, pos = 0;
    const step = 4.5;
    while (s >= 50) { const bx = ex - ux * pos, by = ey - uy * pos; c.beginPath(); c.moveTo(bx, by); c.lineTo(bx + fx * 11 - ux * 3, by + fy * 11 - uy * 3); c.lineTo(bx - ux * 7, by - uy * 7); c.closePath(); c.fill(); pos += 8.5; s -= 50; }
    while (s >= 10) { const bx = ex - ux * pos, by = ey - uy * pos; c.beginPath(); c.moveTo(bx, by); c.lineTo(bx + fx * 11 + ux * 3, by + fy * 11 + uy * 3); c.stroke(); pos += step; s -= 10; }
    if (s >= 5) { if (pos === 0) pos = step; const bx = ex - ux * pos, by = ey - uy * pos; c.beginPath(); c.moveTo(bx, by); c.lineTo(bx + fx * 6 + ux * 1.5, by + fy * 6 + uy * 1.5); c.stroke(); }
    c.restore();
  }
  T.forEach((t, j) => { if (t.getUTCHours() % 6 !== 0) return; L.forEach((p, a) => { const s = F.ws[a][j], dr = F.wd[a][j]; if (s == null || dr == null) return; barb(xOf(j), yOfP(p), s, dr); }); });
  // frame & axes
  // present-time marker
  const tS = T[0].getTime(), tE = T[nT - 1].getTime(), tNow = Date.now();
  if (tNow >= tS && tNow <= tE) {
    const xn = X0 + (X1 - X0) * (tNow - tS) / (tE - tS);
    c.save(); c.strokeStyle = '#e00000'; c.lineWidth = 5; c.setLineDash([]);
    c.beginPath(); c.moveTo(xn, Y0); c.lineTo(xn, Y1); c.stroke();
    c.font = 'bold 20px Arial'; c.textAlign = 'center'; c.textBaseline = 'bottom';
    const lw = c.measureText('NOW').width + 10;
    c.fillStyle = '#fff'; c.fillRect(xn - lw / 2, Y1 - 25, lw, 23);
    c.strokeStyle = '#e00000'; c.lineWidth = 1.5; c.strokeRect(xn - lw / 2, Y1 - 25, lw, 23);
    c.fillStyle = '#e00000'; c.fillText('NOW', xn, Y1 - 4); c.restore();
  }
  c.strokeStyle = '#000'; c.lineWidth = 1.5; c.setLineDash([]); c.strokeRect(X0, Y0, X1 - X0, Y1 - Y0);
  c.fillStyle = '#000'; c.font = 'bold 13px Arial'; c.textAlign = 'right'; c.textBaseline = 'middle';
  const skip = L.length > 12 ? [975, 925, 650, 550, 450] : [];
  L.forEach((p, a) => { if (skip.includes(p)) return; c.fillText(String(p), X0 - 8, yOfP(p)); });
  c.textAlign = 'left';
  L.forEach((p, a) => { if (skip.includes(p)) return; const zs = F.z[a].filter(v => v != null); const ft = Math.round(zs.reduce((s, v) => s + v, 0) / zs.length * 3.28084); c.fillText(ft.toLocaleString('en-US'), X1 + 8, yOfP(p)); });
  c.save(); c.translate(18, (Y0 + Y1) / 2); c.rotate(-Math.PI / 2); c.textAlign = 'center'; c.font = 'bold 13px Arial'; c.fillText('Pressure (mb)', 0, 0); c.restore();
  c.save(); c.translate(o.W - 14, (Y0 + Y1) / 2); c.rotate(Math.PI / 2); c.textAlign = 'center'; c.font = 'bold 13px Arial'; c.fillText('Approx. height (ft MSL)', 0, 0); c.restore();
  c.textAlign = 'center'; c.textBaseline = 'top'; c.font = 'bold 13px Arial';
  const pad = n => String(n).padStart(2, '0');
  T.forEach((t, j) => { if (t.getUTCHours() % 12 === 0) c.fillText(`${pad(t.getUTCDate())}/${pad(t.getUTCHours())}Z`, xOf(j), Y1 + 8); });
  // title + legend
  const mon = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const rs = run ? `${pad(run.getUTCHours())}Z ${pad(run.getUTCDate())} ${mon[run.getUTCMonth()]} ${run.getUTCFullYear()}` : 'latest run';
  c.textAlign = 'left'; c.textBaseline = 'alphabetic'; c.font = 'bold 19px Arial'; c.fillStyle = '#000';
  c.fillText(`${M.label} ${rs}  |  ${o.site} ${o.name}  |  ${o.days}-Day Time-Height Section`, X0, 26);
  c.font = '13px Arial'; c.fillStyle = '#333';
  c.fillText(`Grid point ${d.latitude.toFixed(2)}N ${Math.abs(d.longitude).toFixed(2)}W  •  Times UTC  •  Data: ${M.src} via Open-Meteo`, X0, 46);
  // legend (right of title)
  let lx = X1 - 560; const ly = 34;
  const sw = (fill, label) => { c.fillStyle = fill; c.fillRect(lx, ly - 10, 16, 12); c.strokeStyle = '#1d5a26'; c.lineWidth = 1; c.strokeRect(lx, ly - 10, 16, 12); c.fillStyle = '#000'; c.font = '12px Arial'; c.fillText(label, lx + 20, ly); lx += 20 + c.measureText(label).width + 12; };
  sw('rgb(152,222,140)', 'RH ≥70%'); sw('rgb(86,180,82)', '≥80%'); sw('rgb(40,120,50)', '≥90%');
  c.strokeStyle = '#d7191c'; c.setLineDash([7, 5]); c.lineWidth = 1.2; c.beginPath(); c.moveTo(lx, ly - 4); c.lineTo(lx + 24, ly - 4); c.stroke(); c.setLineDash([]); c.fillStyle = '#000'; c.fillText('+5 to -20 °C', lx + 28, ly); lx += 28 + c.measureText('+5 to -20 °C').width + 12;
  c.strokeStyle = '#1f3fd6'; c.lineWidth = 2.2; c.beginPath(); c.moveTo(lx, ly - 4); c.lineTo(lx + 24, ly - 4); c.stroke(); c.fillStyle = '#000'; c.fillText('0°C', lx + 28, ly); lx += 28 + c.measureText('0°C').width + 14;
  for (const [col, lab] of [['#111', '<20'], ['#f07800', '20-39'], ['#c8102e', '40-59'], ['#7b2fbe', '60+ kt']]) { c.fillStyle = col; c.font = 'bold 12px Arial'; c.fillText(lab, lx, ly); lx += c.measureText(lab).width + 8; }
  return { canvas: cv, run, url };
}
