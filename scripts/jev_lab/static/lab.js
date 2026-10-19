/* Jev Lab page. Vanilla JS, no network beyond this server. Every mark on the sky is one datum. */
(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const KINDS = ['header_mapping', 'file_cte'];
  const KIND_NAMES = { header_mapping: 'Header fields', file_cte: 'File CTE' };
  const NO_ANSWER = new Set(['no_match', 'mixed_or_unclear']);
  const BINS = [0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0];
  const CORE_MAX = 1.2; // Jev's core at mean confidence 1, as a multiple of geom.core
  const CROWN = 1.75; // the reliability crown's radius, as a multiple of the core's
  const STAR_REACH = 14; // px a confidence-1 star's marks reach toward Jev (the twin dot: about 2.7 x size 5)
  const MIN_RING_BAND = 16; // px between the crown and the stars kept for generation rings
  const MIN_RING_STEP = 2; // px per ring; past that only the latest rings that fit are drawn

  // ---------------------------------------------------------------- storage (per-viewer conveniences only)
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private window */ } },
  };

  // ---------------------------------------------------------------- token: from the URL fragment, then out of the address bar
  function readToken() {
    let token = null;
    const match = location.hash.match(/token=([A-Za-z0-9_-]+)/);
    if (match) {
      token = match[1];
      try { sessionStorage.setItem('jevLabToken', token); } catch (e) { /* keep it in memory */ }
      history.replaceState(null, '', location.pathname + location.search);
    }
    if (!token) { try { token = sessionStorage.getItem('jevLabToken'); } catch (e) { token = null; } }
    return token;
  }
  const TOKEN = readToken();

  async function api(path, { method = 'GET', body } = {}) {
    const headers = { Authorization: 'Bearer ' + TOKEN };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let res;
    try {
      res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store', credentials: 'omit' });
    } catch (e) {
      return { ok: false, status: 0, data: { error: 'the lab server is not reachable' } };
    }
    if (res.status === 401) showGate();
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    return { ok: res.ok, status: res.status, data };
  }

  function showGate() { $('#gate').hidden = false; }

  function errorText(r) {
    const d = r.data || {};
    if (d.refused) return 'Refused, nothing was sent: ' + d.refused.join('; ');
    if (d.unavailable) return 'Jev unavailable (' + d.unavailable + ')';
    if (typeof d.detail === 'string') return d.detail;
    if (Array.isArray(d.detail)) return d.detail.map((x) => x.msg).join('; ');
    return d.error || ('request failed (' + r.status + ')');
  }

  function band(confidence) {
    if (confidence >= 0.9) return ['strong', 'strong'];
    if (confidence >= 0.5) return ['moderate', 'moderate'];
    return ['Jev is unsure', 'unsure'];
  }

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  const fmt = (v, d = 3) => (v === null || v === undefined ? '–' : Number(v).toFixed(d));
  const pct = (v) => (v === null || v === undefined ? '–' : (v * 100).toFixed(1) + '%');

  // ---------------------------------------------------------------- state
  const S = {
    status: null,
    kind: store.get('jevLabKind') === 'file_cte' ? 'file_cte' : 'header_mapping',
    motion: store.get('jevLabMotion') !== 'off',
    running: false,
    phase: 'idle',
    run: null,
    generation: 0,
    subjects: new Map(),
    rings: [],
    comets: [],
    flashes: [],
    motes: [],
    incumbentMetrics: null,
    candidateMetrics: null,
    tide: [],
    margins: null,
    noise: null,
    looks: {},
    lookCap: 12,
    claudeCost: 0,
    foresight: { predicted: 0, came_true: 0 },
    lastSummary: null,
    log: [],
    hover: null,
    pinned: null,
    answersSoFar: 0,
    lastEventAt: 0,
  };
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const animated = () => S.motion && !reducedMotion.matches;

  // ---------------------------------------------------------------- theme and motion toggles
  const THEMES = ['auto', 'light', 'dark'];
  function applyTheme(theme) {
    if (theme === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', theme);
    $('#theme-toggle').textContent = 'Theme: ' + theme;
    repaint();
  }
  // A new palette: every canvas redraws, the charts too (they return early while the Loop tab is hidden).
  function repaint() {
    palette = null;
    drawLegend();
    drawTide();
    drawReliability();
    requestDraw();
  }
  let theme = THEMES.includes(store.get('jevLabTheme')) ? store.get('jevLabTheme') : 'auto';
  $('#theme-toggle').addEventListener('click', () => {
    theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    store.set('jevLabTheme', theme);
    applyTheme(theme);
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', repaint);
  function syncMotionButton() {
    const btn = $('#motion-toggle');
    btn.setAttribute('aria-pressed', String(!S.motion));
    btn.textContent = S.motion ? 'Pause motion' : 'Resume motion';
  }
  $('#motion-toggle').addEventListener('click', () => {
    S.motion = !S.motion;
    store.set('jevLabMotion', S.motion ? 'on' : 'off');
    syncMotionButton();
    requestDraw();
  });

  // ---------------------------------------------------------------- tabs (roving tabindex)
  const tabs = $$('[role="tab"]');
  function selectTab(tab) {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      $('#' + t.getAttribute('aria-controls')).hidden = !on;
    }
    store.set('jevLabTab', tab.id);
    if (tab.id === 'tab-ledger') loadLedger();
    if (tab.id === 'tab-table') renderTable();
    if (tab.id === 'tab-loop') { drawTide(); drawReliability(); }
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => selectTab(tab));
    tab.addEventListener('keydown', (e) => {
      const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!step) return;
      const next = tabs[(i + step + tabs.length) % tabs.length];
      next.focus();
      selectTab(next);
    });
  });

  // ---------------------------------------------------------------- kind switch
  function setKind(kind) {
    S.kind = kind;
    store.set('jevLabKind', kind);
    for (const b of $$('[data-kind]')) b.setAttribute('aria-pressed', String(b.dataset.kind === kind));
    S.hover = null;
    S.pinned = null;
    $('#inspector').hidden = true;
    layoutDirty = true;
    requestDraw();
    renderTable();
    drawTide();
    drawReliability();
    renderMetrics();
    updateCaption();
  }
  for (const b of $$('[data-kind]')) b.addEventListener('click', () => setKind(b.dataset.kind));

  // ---------------------------------------------------------------- palette
  let palette = null;
  function colors() {
    if (palette) return palette;
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    palette = {
      sky0: v('--sky-0'), sky1: v('--sky-1'), grid: v('--sky-grid'), veil: v('--veil'), veilEdge: v('--veil-edge'),
      right: v('--mark-right'), wrong: v('--mark-wrong'), decline: v('--mark-decline'), none: v('--mark-none'),
      gold: v('--mark-gold'), jev: v('--mark-jev'), claude: v('--mark-claude'), nova: v('--mark-nova'),
      fix: v('--mark-fix'), brk: v('--mark-break'), mote: v('--mote'), ink: v('--ink'), muted: v('--muted'),
    };
    return palette;
  }

  // ---------------------------------------------------------------- sky geometry
  const canvas = $('#sky');
  const ctx = canvas.getContext('2d');
  let geom = null;
  let layoutDirty = true;

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(240, Math.round(rect.width));
    const h = Math.max(240, Math.round(rect.height || rect.width));
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const R = Math.min(w, h) * 0.47;
    // Radial bands from the centre out, none overlapping: Jev's core, the reliability crown (its
    // largest radius, at mean confidence 1, plus its ticks), the generation rings, then the stars.
    // A confident star's glyph, nova halo and order-check twin reach STAR_REACH px inside rMin.
    // Small skies push the stars out a little so the ring band keeps MIN_RING_BAND px.
    const core = R * 0.085;
    const crownMax = core * CORE_MAX * CROWN;
    const ringIn = crownMax + 7;
    const rMin = Math.max(R * 0.34, ringIn + MIN_RING_BAND + STAR_REACH);
    geom = { w, h, cx: w / 2, cy: h / 2, R, core, crownMax, ringIn, ringOut: rMin - STAR_REACH, rMin, rMax: R * 0.84, orbit: R * 0.97 };
    layoutDirty = true;
  }
  new ResizeObserver(() => { resize(); requestDraw(); }).observe(canvas);

  function subjectsOf(kind) {
    return Array.from(S.subjects.values()).filter((s) => s.kind === kind);
  }

  function layout() {
    if (!geom) resize();
    for (const side of ['train', 'holdout']) {
      const list = subjectsOf(S.kind).filter((s) => s.split === side)
        .sort((a, b) => (a.case_id + '\u0000' + a.subject).localeCompare(b.case_id + '\u0000' + b.subject));
      // One slot per subject, plus a half-slot gap between cases so each header row reads as a cluster.
      const slots = [];
      let cursor = 0;
      list.forEach((s, i) => {
        if (i > 0 && list[i - 1].case_id !== s.case_id) cursor += 0.6;
        slots.push(cursor);
        cursor += 1;
      });
      const span = Math.max(cursor - 1, 1);
      const pad = 0.16;
      list.forEach((s, i) => {
        const t = list.length === 1 ? 0.5 : slots[i] / span;
        const a = pad + t * (Math.PI - 2 * pad);
        s.angle = side === 'train' ? Math.PI + a : a;
      });
    }
    layoutDirty = false;
  }

  function radiusFor(obs) {
    if (!obs || obs.confidence === null || obs.confidence === undefined) return geom.rMax + geom.R * 0.05;
    return geom.rMin + (1 - obs.confidence) * (geom.rMax - geom.rMin);
  }

  function ease(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; }

  function starRadius(s, now) {
    const target = radiusFor(s.cur);
    if (!animated()) { s.fromR = undefined; return target; }
    if (s.fromR === undefined) return target;
    const t = Math.min(1, (now - s.t0) / 900);
    if (t >= 1) { s.fromR = undefined; return target; }
    return s.fromR + (target - s.fromR) * ease(t);
  }

  function glyphFor(obs) {
    if (!obs || obs.confidence === null || obs.confidence === undefined) return 'none';
    const declines = NO_ANSWER.has(obs.answer);
    if (declines) return obs.correct ? 'decline' : 'decline-wrong';
    return obs.correct ? 'right' : 'wrong';
  }

  function drawGlyph(c, kind, x, y, r, p, alpha = 1) {
    c.save();
    c.globalAlpha = alpha;
    c.lineWidth = Math.max(1.2, r * 0.35);
    switch (kind) {
      case 'right':
        c.fillStyle = p.right;
        c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill();
        break;
      case 'wrong': {
        c.fillStyle = p.wrong;
        c.beginPath();
        for (let i = 0; i < 8; i++) {
          const a = (i * Math.PI) / 4 - Math.PI / 2;
          const rr = i % 2 === 0 ? r * 1.6 : r * 0.45;
          c.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
        }
        c.closePath(); c.fill();
        break;
      }
      case 'decline':
        c.strokeStyle = p.decline;
        c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.stroke();
        c.fillStyle = p.decline;
        c.beginPath(); c.arc(x, y, r * 0.35, 0, Math.PI * 2); c.fill();
        break;
      case 'decline-wrong':
        c.strokeStyle = p.wrong;
        c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.stroke();
        c.beginPath(); c.moveTo(x - r * 0.8, y + r * 0.8); c.lineTo(x + r * 0.8, y - r * 0.8); c.stroke();
        break;
      case 'nova':
        c.strokeStyle = p.nova;
        c.setLineDash([2, 2]);
        c.beginPath(); c.arc(x, y, r * 1.9, 0, Math.PI * 2); c.stroke();
        c.setLineDash([]);
        break;
      case 'twin':
        c.fillStyle = p.decline;
        c.beginPath(); c.arc(x + r * 1.8, y - r * 1.2, r * 0.55, 0, Math.PI * 2); c.fill();
        c.strokeStyle = p.decline; c.lineWidth = 0.8;
        c.beginPath(); c.moveTo(x, y); c.lineTo(x + r * 1.8, y - r * 1.2); c.stroke();
        break;
      default:
        c.strokeStyle = p.none;
        c.setLineDash([2, 2]);
        c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.stroke();
        c.setLineDash([]);
    }
    c.restore();
  }

  function drawLegend() {
    const p = colors();
    for (const lc of $$('canvas[data-glyph]')) {
      const c = lc.getContext('2d');
      c.clearRect(0, 0, lc.width, lc.height);
      const kind = lc.dataset.glyph;
      if (kind === 'nova') { drawGlyph(c, 'wrong', 16, 16, 4, p); drawGlyph(c, 'nova', 16, 16, 6, p); }
      else if (kind === 'twin') { drawGlyph(c, 'right', 12, 18, 5, p); drawGlyph(c, 'twin', 12, 18, 5, p); }
      else drawGlyph(c, kind, 16, 16, 7, p);
    }
  }

  // ---------------------------------------------------------------- drawing
  let frameQueued = false;
  function requestDraw() {
    if (frameQueued) return;
    frameQueued = true;
    requestAnimationFrame((now) => { frameQueued = false; draw(now); });
  }

  function autoApply() { return (S.status && S.status.auto_apply_confidence) || 0.9; }
  function reviewAt() { return (S.status && S.status.review_confidence) || 0.5; }

  function draw(now) {
    if (!geom) resize();
    if (layoutDirty) layout();
    const p = colors();
    const { w, h, cx, cy, R } = geom;
    let busy = false;
    ctx.clearRect(0, 0, w, h);

    // Sky.
    const sky = ctx.createRadialGradient(cx, cy, R * 0.05, cx, cy, R * 1.25);
    sky.addColorStop(0, p.sky0);
    sky.addColorStop(1, p.sky1);
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, w, h);

    // Threshold circles: where the auto-apply and review bands begin.
    ctx.save();
    for (const conf of [autoApply(), reviewAt()]) {
      const r = geom.rMin + (1 - conf) * (geom.rMax - geom.rMin);
      ctx.strokeStyle = p.grid;
      ctx.setLineDash([4, 6]);
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();

    // The veil over the held-out half.
    ctx.save();
    ctx.fillStyle = p.veil;
    ctx.beginPath(); ctx.moveTo(cx - geom.orbit, cy); ctx.arc(cx, cy, geom.orbit, 0, Math.PI, false); ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = p.veilEdge;
    ctx.beginPath(); ctx.moveTo(cx - geom.orbit, cy); ctx.lineTo(cx - geom.rMin, cy); ctx.moveTo(cx + geom.rMin, cy); ctx.lineTo(cx + geom.orbit, cy); ctx.stroke();
    ctx.restore();

    drawAxisLabels(p);

    // Milky Way: one mote per sandbox question this session.
    S.motes.forEach((m, i) => {
      const x = 14 + (i % 40) * ((w - 28) / 40);
      const y = 14 + Math.floor(i / 40) * 7;
      ctx.save();
      ctx.globalAlpha = 0.25 + 0.75 * (m.confidence ?? 0.3);
      ctx.fillStyle = m.verdict === 'right' ? p.right : m.verdict === 'wrong' ? p.wrong : p.mote;
      ctx.beginPath(); ctx.arc(x, y, 2.2, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    });

    // Jev: the core grows with mean confidence; the crown is the reliability of the current answers.
    const current = subjectsOf(S.kind).map((s) => s.cur).filter((o) => o && o.confidence !== null && o.confidence !== undefined);
    const meanConf = current.length ? current.reduce((a, o) => a + o.confidence, 0) / current.length : 0;
    const coreR = geom.core * (0.65 + (CORE_MAX - 0.65) * meanConf);
    const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 3.2);
    glow.addColorStop(0, p.jev);
    glow.addColorStop(0.35, p.jev);
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.save();
    ctx.globalAlpha = 0.9;
    ctx.fillStyle = glow;
    ctx.beginPath(); ctx.arc(cx, cy, coreR * 3.2, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    // Generation rings around Jev, for the selected question: drawn over the glow, outside the crown.
    // The latest ones that fit at MIN_RING_STEP px each; the Loop tab's Brier chart has every generation.
    const band = geom.ringOut - geom.ringIn;
    const rings = S.rings.map((ring) => ({ generation: ring.generation, result: ring.results[S.kind] }))
      .filter((ring) => ring.result && ['holdout', 'screen'].includes(ring.result.stage))
      .slice(-Math.max(1, Math.floor(band / MIN_RING_STEP)));
    const step = rings.length ? Math.min(9, band / rings.length) : 0;
    rings.forEach((ring, i) => {
      const r = geom.ringIn + step * (i + 0.5);
      const res = ring.result;
      ctx.save();
      if (res.accepted) {
        const gain = res.holdout ? (res.holdout.incumbent.brier - res.holdout.candidate.brier) : 0;
        ctx.strokeStyle = p.gold;
        ctx.lineWidth = Math.min(step, 1.5 + Math.min(4, Math.max(0, gain) * 60));
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
      } else if (res.stage === 'holdout') {
        ctx.strokeStyle = p.decline;
        ctx.globalAlpha = 0.6;
        ctx.setLineDash([5, 4]);
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
      } else {
        ctx.strokeStyle = p.decline;
        ctx.globalAlpha = 0.5;
        ctx.setLineDash([1, 4]);
        ctx.beginPath(); ctx.arc(cx, cy, r, Math.PI, Math.PI * 2); ctx.stroke();
      }
      ctx.restore();
    });

    const binsData = reliability(current);
    const arc = (Math.PI * 2) / binsData.length;
    binsData.forEach((bin, i) => {
      const start = -Math.PI / 2 + i * arc + 0.06;
      const span = arc - 0.12;
      const r = coreR * CROWN;
      ctx.save();
      ctx.lineCap = 'round';
      ctx.strokeStyle = p.grid;
      ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(cx, cy, r, start, start + span); ctx.stroke();
      if (bin.n) {
        ctx.strokeStyle = p.gold;
        ctx.beginPath(); ctx.arc(cx, cy, r, start, start + span * bin.accuracy); ctx.stroke();
        const tick = start + span * bin.mean;
        ctx.strokeStyle = p.ink;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(tick) * (r - 4), cy + Math.sin(tick) * (r - 4));
        ctx.lineTo(cx + Math.cos(tick) * (r + 4), cy + Math.sin(tick) * (r + 4));
        ctx.stroke();
      }
      ctx.restore();
    });
    ctx.save();
    ctx.font = '600 12px ui-sans-serif, system-ui, sans-serif';
    ctx.textAlign = 'center';
    // A sky-coloured halo keeps the label readable where a generation ring passes under it.
    ctx.lineJoin = 'round';
    ctx.lineWidth = 4;
    ctx.strokeStyle = p.sky0;
    ctx.strokeText('Jev', cx, cy + coreR * 2.4 + 12);
    ctx.fillStyle = p.ink;
    ctx.fillText('Jev', cx, cy + coreR * 2.4 + 12);
    ctx.restore();

    // Stars.
    const twinkle = animated() && (S.running || now - S.lastEventAt < 10000) ? now / 1000 : 0;
    for (const s of subjectsOf(S.kind)) {
      const r = starRadius(s, now);
      if (s.fromR !== undefined) busy = true;
      const x = cx + Math.cos(s.angle) * r;
      const y = cy + Math.sin(s.angle) * r;
      s.x = x; s.y = y;
      const obs = s.cur;
      const conf = obs && obs.confidence !== null && obs.confidence !== undefined ? obs.confidence : 0;
      const size = 1.8 + 3.2 * Math.sqrt(conf);
      const shimmer = twinkle ? 0.18 * (1 - conf) * Math.sin(twinkle * 2.1 + s.angle * 7) : 0;
      // Candidate trail: from today's answer to the rewrite's answer for the same subject.
      if (s.cand && obs) {
        const cr = radiusFor(s.cand);
        const tx = cx + Math.cos(s.angle) * cr;
        const ty = cy + Math.sin(s.angle) * cr;
        const fix = !obs.correct && s.cand.correct;
        const brk = obs.correct && !s.cand.correct;
        ctx.save();
        ctx.strokeStyle = fix ? p.fix : brk ? p.brk : p.grid;
        ctx.lineWidth = fix || brk ? 1.6 : 1;
        ctx.globalAlpha = 0.85;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(tx, ty); ctx.stroke();
        drawGlyph(ctx, glyphFor(s.cand), tx, ty, Math.max(1.5, size * 0.6), p, 0.55);
        ctx.restore();
      }
      drawGlyph(ctx, glyphFor(obs), x, y, size, p, Math.min(1, 0.45 + 0.55 * conf + shimmer));
      if (obs && obs.confidence >= autoApply() && !NO_ANSWER.has(obs.answer) && !obs.correct) drawGlyph(ctx, 'nova', x, y, size, p);
      if (obs && obs.order_consistent === false) drawGlyph(ctx, 'twin', x, y, size, p);
      if (S.hover === s || S.pinned === s) {
        ctx.save();
        ctx.strokeStyle = p.ink;
        ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(x, y, size + 5, 0, Math.PI * 2); ctx.stroke();
        ctx.restore();
      }
    }

    // Claude: a moon on the outer orbit that advances one step per generation.
    const moonA = moonAngle(S.generation);
    const mx = cx + Math.cos(moonA) * geom.orbit;
    const my = cy + Math.sin(moonA) * geom.orbit;
    const moonR = Math.max(6, R * 0.035);
    ctx.save();
    if (S.phase === 'proposing') {
      const pulse = animated() ? 0.5 + 0.5 * Math.sin(now / 220) : 1;
      ctx.globalAlpha = 0.25 + 0.35 * pulse;
      ctx.fillStyle = p.claude;
      ctx.beginPath(); ctx.arc(mx, my, moonR * 2.2, 0, Math.PI * 2); ctx.fill();
      if (animated()) busy = true;
    }
    ctx.globalAlpha = 1;
    ctx.fillStyle = p.claude;
    ctx.beginPath(); ctx.arc(mx, my, moonR, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = p.sky0;
    ctx.beginPath(); ctx.arc(mx + moonR * 0.45, my - moonR * 0.25, moonR * 0.85, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = p.ink;
    ctx.font = '600 12px ui-sans-serif, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Claude', mx, my - moonR - 6);
    ctx.restore();

    // Comets: one per proposal. The tail has one bead per changed option; the ending is the decision.
    // Without motion each comet is drawn once at its ending and stays until the next one replaces it.
    const still = !animated();
    const lastComet = S.comets[S.comets.length - 1];
    S.comets = S.comets.filter((comet) => !comet.done || (still ? comet === lastComet : now - comet.endT < 1600));
    for (const comet of S.comets) {
      const target = comet.fate === 'accepted' ? [cx, cy]
        : comet.fate === 'holdout' ? [cx + (comet.sx - cx) * 0.15, cy + geom.rMin * 0.9]
        : comet.fate === 'screen' ? [cx + (comet.sx - cx) * 0.55, cy + (comet.sy - cy) * 0.55]
        : comet.fate === 'invalid' || comet.fate === 'unchanged' ? [comet.sx, comet.sy]
        : [cx + (comet.sx - cx) * 0.4, cy + (comet.sy - cy) * 0.4];
      const travel = still ? 1 : Math.min(1, (now - comet.t0) / 1400);
      if (travel < 1) busy = true;
      const hx = comet.sx + (target[0] - comet.sx) * ease(travel);
      const hy = comet.sy + (target[1] - comet.sy) * ease(travel);
      const fade = comet.done && !still ? Math.max(0, Math.min(1, 1 - (now - comet.endT) / 1600)) : 1;
      if (!still && (!comet.done || fade > 0)) busy = true;
      ctx.save();
      ctx.globalAlpha = fade;
      const color = comet.fate === 'accepted' ? p.gold : comet.fate && comet.fate !== 'pending' ? p.decline : p.claude;
      for (let i = 0; i < comet.beads; i++) {
        const back = (i + 1) / (comet.beads + 1);
        const bx = hx + (comet.sx - hx) * back * 0.6;
        const by = hy + (comet.sy - hy) * back * 0.6;
        ctx.fillStyle = color;
        ctx.globalAlpha = fade * (0.8 - back * 0.6);
        ctx.beginPath(); ctx.arc(bx, by, 2, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = fade;
      if (comet.fate === 'unchanged') {
        // Nothing to judge: a hollow ring around the moon, in the ink colour so it never merges with the crescent.
        ctx.strokeStyle = p.ink;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.arc(hx, hy, moonR + 5, 0, Math.PI * 2); ctx.stroke();
        ctx.setLineDash([]);
      } else {
        ctx.fillStyle = color;
        const burst = comet.fate === 'invalid' ? (still ? 6 : 3 + 6 * (1 - fade)) : 3.5;
        ctx.beginPath(); ctx.arc(hx, hy, burst, 0, Math.PI * 2); ctx.fill();
      }
      ctx.restore();
    }

    // Flashes at Jev when a rewrite is kept.
    S.flashes = S.flashes.filter((f) => now - f.t0 < 1400);
    for (const f of S.flashes) {
      const t = animated() ? (now - f.t0) / 1400 : 1;
      if (t < 1) busy = true;
      if (t < 0) continue;
      ctx.save();
      ctx.globalAlpha = Math.max(0, 1 - t);
      ctx.strokeStyle = p.gold;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(cx, cy, coreR * (1.5 + 5 * t), 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
    }

    // Twinkle (uncertainty) only while something is happening, so an idle tab costs no CPU.
    const lively = S.running || now - S.lastEventAt < 10000;
    if (busy || (animated() && lively && subjectsOf(S.kind).length)) requestDraw();
  }

  // The four labels along the horizontal axis, drawn under the stars (a datum is never hidden by
  // a label) with a sky-coloured halo that keeps them clear of the circle and veil lines.
  // Right of Jev: the threshold labels, auto-apply above the axis and review below it. Left: the
  // split labels on the same two lines. A split label is written out in full only when it ends
  // before the threshold label on its line (where that is actually drawn, after clamping to the
  // sky) and before Jev's crown; otherwise the short form.
  function drawAxisLabels(p) {
    const { w, cx, cy } = geom;
    const thresholds = [[autoApply(), 'auto-apply ≥ ' + autoApply().toFixed(2), -5], [reviewAt(), 'review ≥ ' + reviewAt().toFixed(2), 14]];
    const splits = [['▲ Training: Claude sees these misses', '▲ Training', -8], ['▼ Held out: Claude never sees this half', '▼ Held out', 18]];
    const label = (text, x, y) => { ctx.strokeText(text, x, y); ctx.fillText(text, x, y); };
    ctx.save();
    ctx.textAlign = 'left';
    ctx.lineJoin = 'round';
    ctx.lineWidth = 3;
    ctx.strokeStyle = p.sky0;
    ctx.fillStyle = p.muted;
    thresholds.forEach(([conf, text, dy], i) => {
      ctx.font = '11px ui-sans-serif, system-ui, sans-serif';
      const r = geom.rMin + (1 - conf) * (geom.rMax - geom.rMin);
      const x = Math.min(cx + r + 4, w - 4 - ctx.measureText(text).width);
      label(text, x, cy + dy);
      const [full, short, sdy] = splits[i];
      ctx.font = '12px ui-sans-serif, system-ui, sans-serif';
      const end = Math.min(x - 10, cx - geom.crownMax - 8);
      label(10 + ctx.measureText(full).width <= end ? full : short, 10, cy + sdy);
    });
    ctx.restore();
  }

  // Claude walks down the right-hand arc of its orbit, one step per generation.
  function moonAngle(generation) { return -1.15 + (generation % 9) * 0.27; }

  function reliability(observations) {
    const out = [];
    for (let i = 0; i < BINS.length - 1; i++) {
      const lo = BINS[i];
      const hi = BINS[i + 1];
      const members = observations.filter((o) => o.confidence >= lo && (o.confidence < hi || (hi === 1 && o.confidence === 1)));
      const n = members.length;
      out.push({
        lo, hi, n,
        accuracy: n ? members.filter((o) => o.correct).length / n : 0,
        mean: n ? members.reduce((a, o) => a + o.confidence, 0) / n : (lo + hi) / 2,
      });
    }
    return out;
  }

  // ---------------------------------------------------------------- hover, inspector
  function nearest(x, y) {
    let best = null;
    let bestD = 14 * 14;
    for (const s of subjectsOf(S.kind)) {
      if (s.x === undefined) continue;
      const d = (s.x - x) ** 2 + (s.y - y) ** 2;
      if (d < bestD) { best = s; bestD = d; }
    }
    return best;
  }

  function describe(s) {
    const obs = s.cur;
    const lines = [
      el('div', {}, el('b', { text: s.subject === '(file)' ? 'File: ' + s.case_id : s.subject }), ' · ', s.case_id),
      el('div', { text: (s.split === 'train' ? 'Training split' : 'Held out (Claude never sees it)') + ' · expected ' + s.expected.join(' or ') }),
    ];
    if (obs && obs.answer) {
      const [word] = band(obs.confidence);
      lines.push(el('div', {}, 'Jev: ', el('b', { text: obs.answer }), ` (confidence ${fmt(obs.confidence, 2)}, ${word}) `, obs.correct ? '✓ right' : '✗ wrong'));
      const top = Object.entries(obs.top || {}).map(([k, v]) => `${k} ${fmt(v, 2)}`).join(', ');
      if (top) lines.push(el('div', { class: 'small', text: 'Top: ' + top }));
      if (obs.order_consistent === false) lines.push(el('div', { class: 'small', text: 'Order check: the answer changed when the options were reversed.' }));
    } else {
      lines.push(el('div', { text: 'No answer (' + ((obs && obs.status) || 'not asked yet') + ')' }));
    }
    if (s.cand && s.cand.answer) {
      lines.push(el('div', { class: 'small' }, 'Rewrite: ', el('b', { text: s.cand.answer }), ` (${fmt(s.cand.confidence, 2)}) `, s.cand.correct ? '✓' : '✗'));
    }
    return lines;
  }

  const tooltip = $('#tooltip');
  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const s = nearest(x, y);
    if (s !== S.hover) { S.hover = s; requestDraw(); }
    if (!s) { tooltip.hidden = true; return; }
    tooltip.replaceChildren(...describe(s));
    tooltip.hidden = false;
    const left = Math.min(x + 18, rect.width - 220);
    tooltip.style.left = Math.max(8, left) + 'px';
    tooltip.style.top = Math.max(8, y + 12) + 'px';
  });
  canvas.addEventListener('mouseleave', () => { tooltip.hidden = true; S.hover = null; requestDraw(); });
  canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const s = nearest(e.clientX - rect.left, e.clientY - rect.top);
    S.pinned = s;
    const box = $('#inspector');
    if (s) { box.replaceChildren(...describe(s)); box.hidden = false; } else { box.hidden = true; }
    requestDraw();
  });

  // ---------------------------------------------------------------- events from the server
  function resetRun() {
    S.subjects.clear();
    S.rings = [];
    S.comets = [];
    S.flashes = [];
    S.incumbentMetrics = null;
    S.candidateMetrics = null;
    S.tide = [];
    S.margins = null;
    S.noise = null;
    S.generation = 0;
    S.claudeCost = 0;
    S.foresight = { predicted: 0, came_true: 0 };
    S.log = [];
    S.answersSoFar = 0;
    layoutDirty = true;
  }

  // Follow new lines inside the log box only, and only while it is scrolled to the end: the page
  // itself never moves away from the sky.
  function logLine(text, cls) {
    S.log.push({ text, cls });
    const log = $('#log');
    const atEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 8;
    log.append(el('li', { class: cls || '', text }));
    if (atEnd) log.scrollTop = log.scrollHeight;
  }

  // Screen-reader announcements. History is redrawn but never read out again: on the first
  // connection that is everything before the page loaded (hello's replay_until); on a reconnect,
  // only what this page already dispatched (lastSeenId), so results missed while disconnected are
  // still announced. Messages that arrive together (a run's last generation and its end) are
  // joined, never overwritten; at most the latest three are read.
  let lastSeenId = 0;
  let quietUntil = 0;
  let replaying = false;
  let pendingAnnouncements = [];
  let announceTimer = null;
  function announce(text) {
    if (replaying) return;
    pendingAnnouncements.push(text);
    clearTimeout(announceTimer);
    announceTimer = setTimeout(() => {
      $('#announce').textContent = pendingAnnouncements.slice(-3).join(' ');
      pendingAnnouncements = [];
    }, 150);
  }

  const handlers = {
    hello(d) {
      resetRun();
      S.motes = []; // the backlog replays every Ask Jev question of this server session
      const until = d.replay_until || 0;
      if (until < lastSeenId) lastSeenId = 0; // the server restarted and its ids began again
      quietUntil = lastSeenId || until;
      $('#log').replaceChildren();
      applyStatus(d.status);
    },
    run_started(d) {
      resetRun();
      $('#log').replaceChildren();
      S.run = d;
      S.running = true;
      S.phase = 'incumbent';
      S.looks = { ...((d.epoch && d.epoch.looks) || {}) };
      if (d.epoch && d.epoch.cap) S.lookCap = d.epoch.cap;
      logLine(`Run ${d.run_id}: ${d.cases} labelled cases, ${d.split.train.length} training and ${d.split.holdout.length} held out. Claude: ${d.proposer}.`);
    },
    parity(d) {
      if (!d.ok) logLine('Parity check failed: the lab no longer scores like scripts/jev_eval.py. ' + d.problems.slice(0, 3).join('; '), 'failed');
    },
    observation(d) {
      const key = d.kind + '|' + d.case_id + '|' + d.subject;
      let s = S.subjects.get(key);
      if (!s) {
        s = { key, kind: d.kind, case_id: d.case_id, subject: d.subject, split: d.split, expected: d.expected, cur: null, cand: null };
        S.subjects.set(key, s);
        layoutDirty = true;
      }
      if (d.role === 'incumbent') setCurrent(s, d);
      else s.cand = d;
      S.answersSoFar += 1;
      if (S.answersSoFar % 8 === 0) updateNow();
    },
    evaluated(d) {
      if (d.role === 'incumbent') {
        S.incumbentMetrics = d.metrics;
        S.tide.push({ generation: 0, incumbent: d.metrics, candidate: null, accepted: [] });
        const m = d.metrics[S.kind];
        logLine(`Incumbent wording: ${KIND_NAMES[S.kind]} training Brier ${fmt(m.train.brier)}, held-out ${fmt(m.holdout.brier)}.`);
      } else {
        S.candidateMetrics = d.metrics;
      }
      renderMetrics();
      drawTide();
      drawReliability();
    },
    noise(d) {
      S.noise = d.noise;
      S.margins = d.margins;
      const parts = KINDS.map((k) => `${KIND_NAMES[k]} ${fmt(d.noise[k].brier_delta, 4)} (margin ${fmt(d.margins[k], 4)})`);
      logLine('Noise floor from a repeat of the training split: ' + parts.join('; ') + '.');
    },
    generation_started(d) {
      S.generation = d.generation;
      S.phase = 'proposing';
      S.answersSoFar = 0;
      for (const s of S.subjects.values()) s.cand = null;
      logLine(`Generation ${d.generation}: Claude is reading the training misses.`);
    },
    proposal(d) {
      if (!geom) resize();
      S.phase = 'evaluating';
      S.claudeCost += d.cost_usd || 0;
      const changes = KINDS.reduce((n, k) => n + (d.patches[k] ? (d.patches[k].criteria || []).length + (d.patches[k].task ? 1 : 0) + (d.patches[k].guidance ? 1 : 0) : 0), 0);
      const moonA = moonAngle(S.generation);
      S.comets.push({ generation: d.generation, sx: geom.cx + Math.cos(moonA) * geom.orbit, sy: geom.cy + Math.sin(moonA) * geom.orbit, t0: performance.now(), beads: changes, fate: 'pending', done: false });
      const who = d.backend === 'offline' ? 'The offline heuristic (not Claude)' : `Claude (${d.backend}${d.model ? ', ' + d.model : ''})`;
      logLine(`${who} proposed ${changes} change(s). ${d.rationale ? d.rationale.slice(0, 280) : ''}`);
    },
    generation_done(d) {
      S.phase = 'idle-gen';
      const results = d.decisions || {};
      S.rings.push({ generation: d.generation, results });
      if (d.foresight) {
        S.foresight.predicted += d.foresight.predicted || 0;
        S.foresight.came_true += d.foresight.came_true || 0;
      }
      for (const kind of KINDS) {
        const res = results[kind];
        if (res && res.stage === 'holdout') S.looks[kind] = (S.looks[kind] || 0) + 1;
      }
      const accepted = d.accepted || [];
      for (const s of S.subjects.values()) {
        if (accepted.includes(s.kind) && s.cand) setCurrent(s, s.cand);
        s.cand = null;
      }
      if (accepted.length && S.candidateMetrics) {
        const merged = JSON.parse(JSON.stringify(S.incumbentMetrics || {}));
        for (const kind of accepted) merged[kind] = S.candidateMetrics[kind];
        S.incumbentMetrics = merged;
      }
      S.tide.push({ generation: d.generation, incumbent: S.incumbentMetrics, candidate: S.candidateMetrics, accepted, results });
      S.candidateMetrics = null;
      // A generation Jev never judged (no proposal, Jev unavailable, no decisions) bursts at the moon.
      const fate = accepted.length ? 'accepted'
        : d.outcome === 'no_proposal' || d.outcome === 'jev_unavailable' || !d.decisions ? 'invalid'
        : KINDS.some((k) => results[k] && results[k].stage === 'holdout') ? 'holdout'
        : KINDS.some((k) => results[k] && results[k].stage === 'screen') ? 'screen'
        : KINDS.some((k) => results[k] && results[k].stage === 'invalid') ? 'invalid' : 'unchanged';
      const comet = S.comets.find((c) => c.generation === d.generation && !c.done);
      if (comet) { comet.fate = fate; comet.done = true; comet.endT = performance.now() + 1400; comet.t0 = performance.now(); }
      if (fate === 'accepted') S.flashes.push({ t0: performance.now() + 1200 });
      const parts = KINDS.map((k) => {
        const r = results[k];
        if (!r) return null;
        const head = r.accepted ? 'kept' : r.stage === 'unchanged' ? 'unchanged' : 'not kept';
        const why = r.accepted || r.stage === 'unchanged' ? '' : ': ' + (r.reasons || []).slice(0, 2).join('; ');
        return `${KIND_NAMES[k]} ${head}${why}`;
      }).filter(Boolean);
      const text = d.reason ? `Generation ${d.generation}: ${d.reason}` : `Generation ${d.generation}: ${parts.join('. ')}.`;
      logLine(text, accepted.length ? 'accepted' : d.outcome === 'no_proposal' ? 'failed' : 'rejected');
      announce(text);
      renderMetrics();
      drawTide();
      drawReliability();
      updateGauges();
    },
    run_done(d) {
      S.running = false;
      S.phase = 'idle';
      endPendingComets();
      S.lastSummary = d;
      const summary = `Run finished: ${d.accepted} rewrite(s) kept in ${d.generations} generation(s). Stopped: ${d.stopped}.`;
      logLine(summary, d.accepted ? 'accepted' : '');
      announce(summary);
      refreshStatus();
    },
    run_failed(d) {
      S.running = false;
      S.phase = 'idle';
      endPendingComets();
      logLine('Run failed: ' + d.error, 'failed');
      announce('Run failed');
      refreshStatus();
    },
    sandbox(d) {
      S.motes.push({ confidence: d.confidence, ask_id: d.ask_id, question_id: d.question_id, verdict: null });
      if (S.motes.length > 400) S.motes.shift();
    },
    feedback(d) {
      const mote = S.motes.find((m) => m.ask_id === d.ask_id && m.question_id === d.question_id);
      if (mote) mote.verdict = d.verdict;
    },
  };

  // A run that ends between a proposal and its judgement leaves that comet with no ending: it burst.
  function endPendingComets() {
    for (const comet of S.comets) {
      if (comet.done) continue;
      comet.done = true;
      comet.fate = 'invalid';
      comet.t0 = performance.now();
      comet.endT = performance.now();
    }
  }

  function setCurrent(s, obs) {
    if (s.cur && geom) { s.fromR = radiusFor(s.cur); s.t0 = performance.now(); }
    s.cur = obs;
  }

  function dispatch(event, data, id) {
    const handler = handlers[event];
    if (!handler) return;
    S.lastEventAt = performance.now();
    replaying = event !== 'hello' && id > 0 && id <= quietUntil;
    try { handler(data); } finally { replaying = false; }
    if (id > lastSeenId) lastSeenId = id;
    updateNow();
    updateCaption();
    requestDraw();
    if (event === 'observation' && !$('#panel-table').hidden) scheduleTable();
  }

  async function connect() {
    if (!TOKEN) { showGate(); return; }
    try {
      const res = await fetch('/api/events', { headers: { Authorization: 'Bearer ' + TOKEN }, cache: 'no-store', credentials: 'omit' });
      if (res.status === 401) { showGate(); return; }
      if (!res.ok || !res.body) throw new Error('stream ' + res.status);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let cut;
        while ((cut = buffer.indexOf('\n\n')) >= 0) {
          const chunk = buffer.slice(0, cut);
          buffer = buffer.slice(cut + 2);
          let event = 'message';
          let id = 0;
          const data = [];
          for (const line of chunk.split('\n')) {
            if (line.startsWith('event: ')) event = line.slice(7);
            else if (line.startsWith('id: ')) id = parseInt(line.slice(4), 10) || 0;
            else if (line.startsWith('data: ')) data.push(line.slice(6));
          }
          if (data.length) {
            try { dispatch(event, JSON.parse(data.join('\n')), id); } catch (e) { /* a malformed event is skipped */ }
          }
        }
      }
    } catch (e) {
      $('#now-text').textContent = 'Lost the connection to the lab. Retrying…';
    }
    // Without the stream nothing will judge a pending comet or end the run: settle the sky so it
    // stops redrawing. A reconnect's hello and backlog replay rebuild whatever is still going on.
    S.running = false;
    S.phase = 'idle';
    endPendingComets();
    requestDraw();
    setTimeout(connect, 2000);
  }

  // ---------------------------------------------------------------- status, now card, gauges
  function applyStatus(status) {
    if (!status) return;
    S.status = status;
    S.running = status.loop.running;
    // split.json is the truth for held-out wear; a run's own events take over only while it runs.
    if (status.epoch) {
      S.lookCap = status.epoch.cap || S.lookCap;
      if (!S.running) S.looks = { ...(status.epoch.looks || {}) };
    }
    const fake = status.mode === 'fake';
    const pillJev = $('#pill-jev');
    pillJev.className = 'pill ' + (fake ? 'fake' : 'live');
    pillJev.textContent = fake ? 'Jev: OFFLINE FAKE' : `Jev: live, ${status.jev.model}`;
    $('#fake-banner').hidden = !fake;
    // Header check asks both questions: a caption under the short "Lab incumbent" choice says whose
    // wording each one gets (a production version or a lab rewrite) and who judged it.
    const note = $('#hdr-wording-note');
    if (status.incumbents && note) {
      const label = (kind) => (status.incumbents[kind] ? status.incumbents[kind].label : 'production');
      note.textContent = `Lab incumbent${fake ? ', from the offline fake ledger' : ''}: header fields ${label('header_mapping')}; file CTE ${label('file_cte')}.`;
    }
    // Promotion only ever starts from wording live Jev judged. (Guarded: a cached older page may lack them.)
    for (const [id, hide] of [['#ledger-promote', fake], ['#ledger-promote-fake', !fake]]) {
      const node = $(id);
      if (node) node.hidden = hide;
    }
    $('#pill-claude').textContent = 'Claude: ' + status.proposer.backend + (status.proposer.backend === 'offline' ? ' (heuristic)' : '');
    $('#pill-budget').textContent = `Requests: ${status.jev.sent}/${status.jev.max_requests}` + (status.jev.cache_hits ? ` · ${status.jev.cache_hits} cached` : '');
    const select = $('#loop-proposer');
    if (!select.options.length) {
      for (const backend of status.proposer.backends) select.append(el('option', { value: backend, text: backend + (backend === 'offline' ? ' (heuristic, not Claude)' : '') }));
      select.value = status.proposer.backend;
    }
    if (status.loop.last && !S.lastSummary) S.lastSummary = status.loop.last;
    updateNow();
    updateGauges();
    $('#now-primary').disabled = false;
  }

  async function refreshStatus() {
    const r = await api('/api/status');
    if (r.ok) applyStatus(r.data);
  }

  function updateNow() {
    const text = $('#now-text');
    const primary = $('#now-primary');
    const stop = $('#now-stop');
    $('#loop-stop').disabled = !S.running;
    $('#loop-start').disabled = S.running;
    $('#loop-score').disabled = S.running;
    stop.hidden = !S.running;
    if (!S.status) { text.textContent = 'Connecting to the lab…'; return; }
    const left = S.status.jev.max_requests - S.status.jev.sent;
    if (S.running) {
      primary.hidden = true;
      if (S.phase === 'incumbent') text.textContent = `Scoring the current wording: ${S.answersSoFar} answers so far.`;
      else if (S.phase === 'proposing') text.textContent = `Generation ${S.generation}: Claude is rewriting the wording from the training misses.`;
      else if (S.phase === 'evaluating') text.textContent = `Generation ${S.generation}: Jev is answering Claude's rewrite (${S.answersSoFar} answers).`;
      else text.textContent = `Generation ${S.generation} judged. Next one starting.`;
      return;
    }
    primary.hidden = false;
    if (S.lastSummary) {
      text.textContent = `Last run kept ${S.lastSummary.accepted} rewrite(s) in ${S.lastSummary.generations} generation(s); it stopped on "${S.lastSummary.stopped}". ${left} Jev requests left.`;
      primary.textContent = 'Start loop';
      primary.dataset.action = 'loop';
    } else {
      text.textContent = `Jev is ready. Light the sky to see how it answers every labelled header (${left} requests left), or ask it anything on the right.`;
      primary.textContent = 'Light the sky';
      primary.dataset.action = 'score';
    }
  }

  function gauge(label, value, max, note) {
    const box = el('div', { class: 'gauge' }, el('div', { class: 'small', text: label }), el('div', { class: 'n', text: max ? `${value}/${max}` : String(value) }));
    if (max) {
      const meter = el('div', { class: 'meter' });
      const fill = el('span');
      fill.style.width = Math.min(100, (100 * value) / max) + '%';
      meter.append(fill);
      box.append(meter);
    }
    if (note) box.append(el('div', { class: 'small', text: note }));
    return box;
  }

  function updateEstimate() {
    const est = S.status && S.status.estimate;
    if (!est) return;
    const gens = Math.max(1, Math.min(25, parseInt($('#loop-gens').value, 10) || est.generations));
    const base = est.jev_requests_max - est.generations * est.jev_requests_per_generation_max;
    const jev = base + gens * est.jev_requests_per_generation_max;
    const claude = $('#loop-proposer').value === 'offline' ? 'no Claude calls (offline heuristic)' : `up to ${gens} Claude call(s)`;
    $('#loop-estimate').textContent = `This run sends at most ${jev} Jev requests (answers already in the cache are free; held-out cases are asked only when the training split improves) and ${claude}.`;
  }
  $('#loop-gens').addEventListener('input', updateEstimate);
  $('#loop-proposer').addEventListener('change', updateEstimate);

  function updateGauges() {
    if (!S.status) return;
    updateEstimate();
    const cap = S.lookCap;
    const fs = S.foresight;
    $('#gauges').replaceChildren(
      gauge('Jev requests sent', S.status.jev.sent, S.status.jev.max_requests, S.status.jev.cache_hits + ' answered from cache'),
      gauge('Held-out looks, header fields', S.looks.header_mapping || 0, cap, 'rotate the split at the cap'),
      gauge('Held-out looks, file CTE', S.looks.file_cte || 0, cap),
      gauge('Claude cost this run', '$' + S.claudeCost.toFixed(2), 0),
      gauge('Claude foresight', fs.predicted ? `${fs.came_true}/${fs.predicted}` : '–', 0, 'predicted fixes that came true'),
    );
  }

  function updateCaption() {
    const list = subjectsOf(S.kind);
    const answered = list.filter((s) => s.cur && s.cur.confidence !== null && s.cur.confidence !== undefined);
    if (!list.length) { $('#sky-caption').textContent = 'No answers yet. Light the sky to ask Jev every labelled subject.'; return; }
    const right = answered.filter((s) => s.cur.correct).length;
    const novas = answered.filter((s) => s.cur.confidence >= autoApply() && !NO_ANSWER.has(s.cur.answer) && !s.cur.correct).length;
    $('#sky-caption').textContent = `${KIND_NAMES[S.kind]}: ${list.length} labelled subjects, ${right} answered right, ${answered.length - right} wrong, ${novas} wrong at auto-apply confidence.`;
  }

  $('#now-primary').addEventListener('click', () => {
    if ($('#now-primary').dataset.action === 'loop') startLoop(false); else startLoop(true);
  });
  $('#now-stop').addEventListener('click', stopLoop);

  // ---------------------------------------------------------------- loop controls
  async function startLoop(scoreOnly) {
    const generations = scoreOnly ? 0 : Math.max(1, Math.min(25, parseInt($('#loop-gens').value, 10) || 5));
    const margin = parseFloat($('#loop-margin').value);
    const r = await api('/api/loop/start', { method: 'POST', body: { generations, margin: Number.isFinite(margin) ? margin : 0.01, proposer: $('#loop-proposer').value || undefined } });
    if (!r.ok) { logLine('Could not start: ' + errorText(r), 'failed'); announce('Could not start: ' + errorText(r)); }
    else S.running = true;
    updateNow();
  }
  async function stopLoop() {
    await api('/api/loop/stop', { method: 'POST', body: {} });
    logLine('Stop requested: the run ends after the current step.');
  }
  $('#loop-start').addEventListener('click', () => startLoop(false));
  $('#loop-score').addEventListener('click', () => startLoop(true));
  $('#loop-stop').addEventListener('click', stopLoop);

  function renderMetrics() {
    const box = $('#metrics');
    const inc = S.incumbentMetrics;
    if (!inc) { box.replaceChildren(); return; }
    const cand = S.candidateMetrics;
    const rows = [['accuracy', 'Accuracy', pct], ['brier', 'Brier (lower better)', (v) => fmt(v, 4)], ['ece', 'ECE', (v) => fmt(v, 4)], ['wrong_at_auto_apply', 'Wrong at auto-apply', (v) => v ?? '–'], ['order_inconsistent_at_auto_apply', 'Order flips at auto-apply', (v) => v ?? '–'], ['safe_coverage', 'Safe coverage', pct]];
    const head = el('tr', {}, el('th', { text: KIND_NAMES[S.kind] }), el('th', { class: 'num', text: 'Train' }), el('th', { class: 'num', text: 'Held out' }), cand ? el('th', { class: 'num', text: 'Rewrite train' }) : null, cand ? el('th', { class: 'num', text: 'Rewrite held out' }) : null);
    const body = rows.map(([key, label, f]) => el('tr', {},
      el('td', { text: label }),
      el('td', { class: 'num', text: f(inc[S.kind].train[key]) }),
      el('td', { class: 'num', text: f(inc[S.kind].holdout[key]) }),
      cand ? el('td', { class: 'num', text: cand[S.kind].train.subjects ? f(cand[S.kind].train[key]) : '–' }) : null,
      cand ? el('td', { class: 'num', text: cand[S.kind].holdout.subjects ? f(cand[S.kind].holdout[key]) : 'not asked' }) : null,
    ));
    box.replaceChildren(el('table', {}, el('thead', {}, head), el('tbody', {}, body)));
  }

  function chartCanvas(id) {
    const c = $(id);
    const rect = c.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = Math.max(200, Math.round(rect.width * dpr));
    c.height = Math.max(120, Math.round(rect.height * dpr));
    const g = c.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { g, w: c.width / dpr, h: c.height / dpr };
  }

  function drawTide() {
    if ($('#panel-loop').hidden) return;
    const { g, w, h } = chartCanvas('#tide');
    const p = colors();
    g.clearRect(0, 0, w, h);
    const points = S.tide.map((t) => ({
      gen: t.generation,
      train: t.incumbent && t.incumbent[S.kind].train.brier,
      hold: t.incumbent && t.incumbent[S.kind].holdout.brier,
      candTrain: t.candidate && t.candidate[S.kind].train.subjects ? t.candidate[S.kind].train.brier : null,
      candHold: t.candidate && t.candidate[S.kind].holdout.subjects ? t.candidate[S.kind].holdout.brier : null,
      kept: (t.accepted || []).includes(S.kind),
    }));
    const values = points.flatMap((pt) => [pt.train, pt.hold, pt.candTrain, pt.candHold]).filter((v) => v !== null && v !== undefined);
    g.fillStyle = p.muted;
    g.font = '11px ui-sans-serif, system-ui, sans-serif';
    if (!values.length) { g.fillText('No generations yet.', 10, 20); return; }
    const top = Math.max(...values) * 1.15 || 0.3;
    const maxGen = Math.max(1, ...points.map((pt) => pt.gen));
    const X = (gen) => 34 + (gen / maxGen) * (w - 46);
    const Y = (v) => 10 + (1 - v / top) * (h - 30);
    g.strokeStyle = p.grid;
    g.beginPath(); g.moveTo(34, 10); g.lineTo(34, h - 20); g.lineTo(w - 10, h - 20); g.stroke();
    g.fillText(top.toFixed(2), 2, 14);
    g.fillText('0', 22, h - 20);
    for (let gen = 0; gen <= maxGen; gen++) g.fillText(String(gen), X(gen) - 3, h - 6);
    const line = (key, dash, color) => {
      g.save(); g.strokeStyle = color; g.setLineDash(dash); g.lineWidth = 1.6; g.beginPath();
      let started = false;
      for (const pt of points) { const v = pt[key]; if (v === null || v === undefined) continue; if (!started) { g.moveTo(X(pt.gen), Y(v)); started = true; } else g.lineTo(X(pt.gen), Y(v)); }
      g.stroke(); g.restore();
    };
    line('train', [], p.right);
    line('hold', [5, 4], p.claude);
    for (const pt of points) {
      for (const [key, color] of [['candTrain', p.right], ['candHold', p.claude]]) {
        if (pt[key] === null || pt[key] === undefined) continue;
        g.strokeStyle = color; g.beginPath(); g.arc(X(pt.gen), Y(pt[key]), 3, 0, Math.PI * 2); g.stroke();
      }
      if (pt.kept && pt.hold !== null) { g.fillStyle = p.gold; g.beginPath(); g.arc(X(pt.gen), Y(pt.hold), 4.5, 0, Math.PI * 2); g.fill(); }
    }
  }

  function drawReliability() {
    if ($('#panel-loop').hidden) return;
    const { g, w, h } = chartCanvas('#reliability');
    const p = colors();
    g.clearRect(0, 0, w, h);
    const obs = subjectsOf(S.kind).map((s) => s.cur).filter((o) => o && o.confidence !== null && o.confidence !== undefined);
    g.fillStyle = p.muted;
    g.font = '11px ui-sans-serif, system-ui, sans-serif';
    if (!obs.length) { g.fillText('No answers yet.', 10, 20); return; }
    const size = Math.min(w - 50, h - 30);
    const X = (v) => 34 + v * size;
    const Y = (v) => 10 + (1 - v) * size;
    g.strokeStyle = p.grid;
    g.strokeRect(X(0), Y(1), size, size);
    g.setLineDash([3, 4]); g.beginPath(); g.moveTo(X(0), Y(0)); g.lineTo(X(1), Y(1)); g.stroke(); g.setLineDash([]);
    g.fillText('confidence →', X(0.62), Y(0) + 14);
    g.fillText('right', 2, Y(1) + 8);
    for (const bin of reliability(obs)) {
      if (!bin.n) continue;
      const bw = (bin.hi - bin.lo) * size;
      g.fillStyle = p.right;
      g.globalAlpha = 0.35;
      g.fillRect(X(bin.lo) + 1, Y(bin.accuracy), bw - 2, bin.accuracy * size);
      g.globalAlpha = 1;
      g.fillStyle = p.ink;
      g.beginPath(); g.arc(X(bin.mean), Y(bin.accuracy), 3, 0, Math.PI * 2); g.fill();
      if (bw >= 34) { g.fillStyle = p.muted; g.fillText('n=' + bin.n, X(bin.lo) + 2, Y(0) - 4); }
    }
    $('#reliability-note').textContent = 'Answers per confidence bin: ' + reliability(obs).map((b) => `${b.lo.toFixed(1)}–${b.hi.toFixed(1)}: ${b.n}`).join(' · ');
    g.fillText(`${obs.length} answers, ${KIND_NAMES[S.kind]}`, X(1) + 4 > w - 90 ? X(0) + 4 : X(1) + 4, Y(1) + 10);
  }

  // ---------------------------------------------------------------- table view
  let tableTimer = null;
  function scheduleTable() { if (!tableTimer) tableTimer = setTimeout(() => { tableTimer = null; renderTable(); }, 400); }
  let sortKey = 'case';
  function renderTable() {
    const box = $('#subject-table');
    const list = subjectsOf(S.kind);
    if (!list.length) { box.replaceChildren(el('p', { class: 'small', text: 'No answers yet.' })); return; }
    const value = (s, key) => ({
      case: s.case_id + s.subject, split: s.split, conf: -(s.cur && s.cur.confidence !== null ? s.cur.confidence : -1), right: s.cur && s.cur.correct ? 1 : 0,
    }[key]);
    list.sort((a, b) => { const va = value(a, sortKey); const vb = value(b, sortKey); return va < vb ? -1 : va > vb ? 1 : 0; });
    // Confidence sorts highest first (its key is negated); every other column sorts ascending.
    const direction = (key) => (key === 'conf' ? 'descending' : 'ascending');
    // Re-rendering replaces the buttons: keep keyboard focus on the one that was pressed.
    const sortBtn = (key, label) => el('th', { 'aria-sort': sortKey === key ? direction(key) : 'none', 'data-key': key }, el('button', { type: 'button', text: label, onclick: () => {
      sortKey = key;
      renderTable();
      const again = $(`#subject-table th[data-key="${key}"] button`);
      if (again) again.focus();
    } }));
    const head = el('tr', {}, sortBtn('case', 'Case · subject'), sortBtn('split', 'Split'), el('th', { text: 'Expected' }), el('th', { text: 'Jev' }), sortBtn('conf', 'Confidence'), sortBtn('right', 'Right?'), el('th', { text: 'Order check' }));
    const rows = list.map((s) => {
      const o = s.cur || {};
      return el('tr', {},
        el('td', { text: `${s.case_id} · ${s.subject}` }),
        el('td', { text: s.split === 'train' ? 'training' : 'held out' }),
        el('td', { text: s.expected.join(' or ') }),
        el('td', { text: o.answer || '–' }),
        el('td', { class: 'num', text: fmt(o.confidence, 2) }),
        el('td', { class: o.correct ? 'good' : 'bad', text: o.answer ? (o.correct ? 'right' : 'wrong') : '–' }),
        el('td', { text: o.order_consistent === false ? 'changed' : o.order_consistent === true ? 'held' : '–' }),
      );
    });
    box.replaceChildren(el('table', {}, el('thead', {}, head), el('tbody', {}, rows)));
  }

  // ---------------------------------------------------------------- Ask Jev (sandbox)
  let questionCount = 0;
  function addQuestion(q = {}) {
    questionCount += 1;
    const type = q.type || 'choice';
    const card = el('div', { class: 'qcard' });
    const kind = el('select', { 'aria-label': 'Question kind' },
      el('option', { value: 'choice', text: 'Which of these (choice)' }),
      el('option', { value: 'noul', text: 'Is this true (yes/no)' }),
      el('option', { value: 'score', text: 'How much (score)' }));
    kind.value = type;
    const id = el('input', { type: 'text', value: q.id || 'q' + questionCount, 'aria-label': 'Question id', size: '8' });
    const text = el('input', { type: 'text', value: q.text || '', placeholder: 'The exact question', 'aria-label': 'Question text', class: 'grow' });
    const options = el('textarea', { 'aria-label': 'Options or levels', spellcheck: 'false' });
    options.value = q.options || '';
    const hint = el('div', { class: 'small' });
    const remove = el('button', { type: 'button', class: 'ghost', text: 'Remove', onclick: () => card.remove() });
    const sync = () => {
      options.hidden = kind.value === 'noul';
      hint.textContent = kind.value === 'choice' ? 'One option per line: name=description. Include an "unclear" option so Jev can say nothing fits.'
        : kind.value === 'score' ? 'One level per line, lowest first (2 to 10 levels).' : 'Ask a direct yes/no question without negations. The answer is p(yes).';
    };
    kind.addEventListener('change', sync);
    sync();
    card.append(el('div', { class: 'row' }, kind, id, remove), text, options, hint);
    card._read = () => ({ type: kind.value, id: id.value.trim(), text: text.value.trim(), options: options.value });
    $('#questions').append(card);
  }

  const EXAMPLES = {
    cte: { state: '{"headers": ["Ship Dte", "Cust Name", "Lot No.", "Qty Shpd"]}', questions: [{ type: 'choice', id: 'cte', text: 'Which FSMA 204 critical tracking event do rows with these CSV headers record?', options: 'shipping=the sender records goods leaving its location\nreceiving=the recipient records goods arriving at its location\ntransformation=inputs are combined or processed into new lots\nunclear=the headers do not identify one event' }] },
    lot: { state: '{"headers": ["Ship Dte", "Cust Name", "Lot No.", "Qty Shpd"]}', questions: [{ type: 'noul', id: 'has_lot', text: 'Does one of the headers name a traceability lot code column?' }] },
    risk: { state: '{"headers": ["Date", "Item", "Qty"], "declared_cte": null}', questions: [{ type: 'score', id: 'risk', text: 'How likely is this file to be rejected as-is by an FSMA 204 importer that needs a lot code and a CTE?', options: 'low\nmedium\nhigh' }] },
  };
  $('#example-select').addEventListener('change', (e) => {
    const ex = EXAMPLES[e.target.value];
    if (!ex) return;
    $('#ask-state').value = ex.state;
    $('#questions').replaceChildren();
    questionCount = 0;
    ex.questions.forEach(addQuestion);
    e.target.value = '';
  });
  $('#add-question').addEventListener('click', () => addQuestion());
  EXAMPLES.cte.questions.forEach(addQuestion);
  addQuestion(EXAMPLES.lot.questions[0]);

  function buildQuestions() {
    const questions = {};
    for (const card of $$('#questions .qcard')) {
      const q = card._read();
      if (!q.id) throw new Error('every question needs an id');
      if (questions[q.id]) throw new Error('duplicate question id ' + q.id);
      if (!q.text) throw new Error('question ' + q.id + ' has no text');
      const lines = q.options.split('\n').map((l) => l.trim()).filter(Boolean);
      if (q.type === 'choice') {
        const criteria = {};
        for (const line of lines) {
          const at = line.indexOf('=');
          const name = (at >= 0 ? line.slice(0, at) : line).trim();
          const desc = at >= 0 ? line.slice(at + 1).trim() : null;
          if (!name) throw new Error('an option in ' + q.id + ' has no name');
          criteria[name] = desc || null;
        }
        if (Object.keys(criteria).length < 2) throw new Error(q.id + ' needs at least two options');
        questions[q.id] = { type: 'choice', instructions: q.text, criteria };
      } else if (q.type === 'score') {
        if (lines.length < 2 || lines.length > 10) throw new Error(q.id + ' needs 2 to 10 levels');
        questions[q.id] = { type: 'score', instructions: q.text, criteria: lines };
      } else {
        questions[q.id] = { type: 'noul', instructions: q.text };
      }
    }
    if (!Object.keys(questions).length) throw new Error('add a question');
    return questions;
  }

  function bars(entries) {
    return el('div', { class: 'bars' }, entries.map(([name, value]) => {
      const fill = el('div', { class: 'fill' });
      fill.style.width = Math.round(100 * value) + '%';
      return el('div', { class: 'barrow' }, el('span', { text: name }), el('div', { class: 'track' }, fill), el('span', { class: 'num', text: fmt(value, 2) }));
    }));
  }

  // How sure Jev was of the answer it gave (a confident "no" is as sure as a confident "yes").
  function answerConfidence(answer) {
    if (answer.type === 'noul' && typeof answer.probability_yes === 'number') return Math.max(answer.probability_yes, 1 - answer.probability_yes);
    return typeof answer.confidence === 'number' ? answer.confidence : null;
  }

  async function sendFeedback(report, questionId, answer, verdict, buttons) {
    const r = await api('/api/adhoc-feedback', { method: 'POST', body: { request_id: report.request_id, ask_id: report.ask_id, question_id: questionId, type: answer.type, confidence: answerConfidence(answer), verdict } });
    for (const b of buttons) b.disabled = true;
    if (!r.ok) announce('Feedback not saved: ' + errorText(r));
    else announce('Saved: Jev was ' + verdict);
  }

  $('#ask-send').addEventListener('click', async () => {
    const out = $('#ask-result');
    let questions;
    try { questions = buildQuestions(); } catch (e) { out.replaceChildren(el('p', { class: 'error', text: e.message })); return; }
    const raw = $('#ask-state').value;
    let state = raw;
    try { state = JSON.parse(raw); } catch (e) { state = raw; }
    out.replaceChildren(el('p', { class: 'small', text: 'Asking…' }));
    const r = await api('/api/ask', { method: 'POST', body: { state, questions } });
    if (!r.ok) { out.replaceChildren(el('p', { class: 'error', text: errorText(r) })); return; }
    const report = r.data;
    const cards = [el('p', { class: 'small', text: `${report.mode === 'fake' ? 'OFFLINE FAKE, not Jev: ' : ''}${report.model}, request ${report.request_id || 'n/a'}, ${report.latency_ms} ms` })];
    for (const [qid, a] of Object.entries(report.answers)) {
      const card = el('div', { class: 'answer' });
      if (a.missing) { card.append(el('h3', { text: qid + ': no answer in the response' })); cards.push(card); continue; }
      if (a.type === 'choice') {
        const [word, cls] = band(a.confidence);
        card.append(el('h3', {}, `${qid}: ${a.choice}`, el('span', { class: 'chip ' + cls, text: `${fmt(a.confidence, 2)} · ${word}` })));
        card.append(bars(Object.entries(a.probabilities).sort((x, y) => y[1] - x[1]).slice(0, 6)));
      } else if (a.type === 'noul') {
        const yes = a.probability_yes >= 0.5;
        card.append(el('h3', {}, `${qid}: ${yes ? 'yes' : 'no'}`, el('span', { class: 'chip', text: `p(yes) ${fmt(a.probability_yes, 2)}` })));
        card.append(bars([['yes', a.probability_yes], ['no', 1 - a.probability_yes]]));
      } else {
        const [word, cls] = band(a.confidence);
        const nearest = a.legend[String(Math.round(a.score))] || '';
        card.append(el('h3', {}, `${qid}: ${fmt(a.score, 2)} on 0..${Object.keys(a.legend).length - 1}${nearest ? ' ~ ' + nearest : ''}`, el('span', { class: 'chip ' + cls, text: `${fmt(a.confidence, 2)} · ${word}` })));
        card.append(bars(Object.entries(a.probabilities).map(([k, v]) => [a.legend[k] || k, v])));
      }
      const right = el('button', { type: 'button', class: 'ghost', text: 'Jev was right' });
      const wrong = el('button', { type: 'button', class: 'ghost', text: 'Jev was wrong' });
      right.addEventListener('click', () => sendFeedback(report, qid, a, 'right', [right, wrong]));
      wrong.addEventListener('click', () => sendFeedback(report, qid, a, 'wrong', [right, wrong]));
      card.append(el('div', { class: 'row' }, right, wrong));
      cards.push(card);
    }
    out.replaceChildren(...cards);
  });

  // ---------------------------------------------------------------- Header check
  function parseRow(text) {
    const sep = text.includes('\t') ? '\t' : ',';
    return text.split(sep).map((h) => h.trim()).filter(Boolean);
  }

  $('#hdr-send').addEventListener('click', async () => {
    const out = $('#hdr-result');
    const headers = parseRow($('#hdr-row').value);
    if (!headers.length) { out.replaceChildren(el('p', { class: 'error', text: 'Paste a header row first.' })); return; }
    out.replaceChildren(el('p', { class: 'small', text: 'Asking…' }));
    const r = await api('/api/headers', { method: 'POST', body: { headers, wording: $('#hdr-wording').value } });
    if (!r.ok) { out.replaceChildren(el('p', { class: 'error', text: errorText(r) })); return; }
    const d = r.data;
    const vocab = (S.status && S.status.vocabulary) || { header_mapping: [], file_cte: [] };
    const parts = [];
    if (d.mode === 'fake') parts.push(el('p', { class: 'small', text: 'OFFLINE FAKE, not Jev.' }));
    if (d.file_cte) {
      const [word, cls] = band(d.file_cte.confidence);
      parts.push(el('p', {}, 'File CTE: ', el('b', { text: d.file_cte.answer }), el('span', { class: 'chip ' + cls, text: `${fmt(d.file_cte.confidence, 2)} · ${word}` }),
        d.file_cte.order_consistent === false ? ' · changed when the options were reversed' : d.file_cte.order_consistent ? ' · held with options reversed' : ''));
    } else if (d.per_row_cte_column) {
      parts.push(el('p', { class: 'small', text: `Not asked: column "${d.per_row_cte_column}" gives each row its CTE.` }));
    }
    if (d.recognized.length) parts.push(el('p', { class: 'small', text: 'The parser already reads: ' + d.recognized.join(', ') }));
    const selects = [];
    const rows = d.columns.map((c) => {
      const select = el('select', { 'aria-label': 'Correct field for ' + c.header }, el('option', { value: '', text: '(not labelled)' }), vocab.header_mapping.map((f) => el('option', { value: f, text: f })), el('option', { value: 'no_match', text: 'no_match' }));
      selects.push([c.header, select]);
      const [word] = c.confidence === undefined ? ['–'] : band(c.confidence);
      return el('tr', {},
        el('td', { text: c.header }),
        el('td', {}, el('b', { text: c.answer || '–' })),
        el('td', { class: 'num', text: fmt(c.confidence, 2) }),
        el('td', { text: c.band ? `${c.band} (${word})` : '–' }),
        el('td', { class: 'small', text: Object.entries(c.top || {}).map(([k, v]) => `${k} ${fmt(v, 2)}`).join(', ') }),
        el('td', {}, select));
    });
    if (rows.length) {
      parts.push(el('div', { class: 'table-wrap' }, el('table', {},
        el('thead', {}, el('tr', {}, ['Header', 'Jev', 'Conf.', 'Band', 'Top 3', 'Your label'].map((t) => el('th', { text: t })))),
        el('tbody', {}, rows))));
    }
    const cteSelect = el('select', { 'aria-label': 'Correct CTE for the file' }, el('option', { value: '', text: '(not labelled)' }), [...vocab.file_cte, 'mixed_or_unclear'].filter((v, i, a) => a.indexOf(v) === i).map((f) => el('option', { value: f, text: f })));
    const msg = el('p', { class: 'small' });
    const save = el('button', { type: 'button', class: 'primary', text: 'Save as a labelled row' });
    save.addEventListener('click', async () => {
      const mappings = {};
      for (const [header, select] of selects) if (select.value) mappings[header] = select.value;
      if (!Object.keys(mappings).length && !cteSelect.value) { msg.className = 'error'; msg.textContent = 'Pick at least one label.'; return; }
      const res = await api('/api/labels', { method: 'POST', body: { headers, cte: cteSelect.value || null, mappings } });
      if (!res.ok) { msg.className = 'error'; msg.textContent = errorText(res); return; }
      msg.className = 'okmsg';
      msg.textContent = `Saved as ${res.data.id}. The next run asks it too (${res.data.local_cases} rows labelled here).`;
      refreshStatus();
    });
    parts.push(el('div', { class: 'row' }, el('label', { class: 'small', text: 'File CTE label' }), cteSelect, save), msg);
    parts.push(el('p', { class: 'small', text: 'Labels stay on this machine (cases.local.json in the lab directory) and feed the next run.' }));
    out.replaceChildren(...parts);
  });

  // ---------------------------------------------------------------- Ledger
  async function loadLedger() {
    const r = await api('/api/ledger');
    const box = $('#ledger-list');
    if (!r.ok) { box.replaceChildren(el('p', { class: 'error', text: errorText(r) })); return; }
    const gens = r.data.rows.filter((row) => row.type === 'generation').reverse();
    if (!gens.length) { box.replaceChildren(el('p', { class: 'small', text: 'No generations recorded yet.' })); return; }
    const items = gens.map((row) => {
      const kept = (row.accepted || []).map((k) => KIND_NAMES[k]).join(', ');
      const btn = el('button', { type: 'button', class: 'ghost', text: `${row.at} · run ${row.run_id} · g${row.generation} · ${row.outcome}${kept ? ' (' + kept + ')' : ''}` });
      btn.addEventListener('click', () => showGeneration(row));
      return el('li', {}, btn, judgedByFake(row) ? el('span', { class: 'chip fake', text: 'OFFLINE FAKE' }) : null);
    });
    box.replaceChildren(el('ul', { class: 'log' }, items));
  }

  // Rows judged by the offline fake are word overlap, not Jev: never a candidate for promotion.
  function judgedByFake(row) { return row.mode === 'fake' || Boolean(row.jev && row.jev.mode === 'fake'); }

  async function showGeneration(row) {
    const box = $('#ledger-detail');
    const fake = judgedByFake(row);
    const parts = [el('h3', { text: `Run ${row.run_id}, generation ${row.generation}: ${row.outcome}` })];
    if (fake) parts.push(el('p', { class: 'small', text: 'Judged by the OFFLINE FAKE (word overlap), not Jev. Not for promotion: run it again against live Jev.' }));
    if (row.reason) parts.push(el('p', { text: row.reason }));
    if (row.proposal) parts.push(el('p', { class: 'small', text: `${row.proposal.backend}${row.proposal.model ? ', ' + row.proposal.model : ''}: ${row.proposal.rationale}` }));
    if (row.foresight && row.foresight.predicted) parts.push(el('p', { class: 'small', text: `Foresight: ${row.foresight.came_true} of ${row.foresight.predicted} predicted fixes came true; ${row.foresight.breaks} right answers broke.` }));
    for (const [kind, res] of Object.entries(row.decisions || {})) {
      parts.push(el('p', {}, el('b', { text: KIND_NAMES[kind] + ': ' }), res.accepted ? 'kept' : `${res.stage}: ${(res.reasons || []).join('; ')}`));
      const digest = (row.candidates || {})[kind];
      if (digest) {
        const check = el('button', { type: 'button', class: 'ghost', text: 'Confirm on fresh rows' });
        const verdict = el('p', { class: 'small' });
        check.addEventListener('click', async () => {
          verdict.textContent = 'Asking Jev about rows labelled after the split began…';
          const c = await api('/api/confirm', { method: 'POST', body: { digest } });
          if (!c.ok) { verdict.className = 'error'; verdict.textContent = errorText(c); return; }
          const d = c.data;
          verdict.className = 'small';
          const holds = d.decision && !d.decision.reasons.length;
          verdict.textContent = `${d.fresh_subjects} fresh subjects in ${d.fresh_cases} rows${d.sufficient ? '' : ' (not enough: label at least 5 in Header check)'}. `
            + `Production Brier ${fmt(d.production.brier, 4)}, rewrite ${fmt(d.rewrite.brier, 4)}. `
            + (d.decision ? (holds ? 'Holds on fresh rows.' : 'Does not hold: ' + d.decision.reasons.join('; ')) : '');
        });
        parts.push(el('div', { class: 'row' }, check), verdict);
        const btn = el('button', { type: 'button', class: 'ghost', text: 'Show the wording diff' });
        const holder = el('div', { class: 'diff' });
        btn.addEventListener('click', async () => {
          const d = await api('/api/question-sets/' + digest + '/diff');
          if (!d.ok) { holder.replaceChildren(el('p', { class: 'error', text: errorText(d) })); return; }
          const blocks = [fake
            ? el('p', { class: 'small', text: `Against production ${d.data.baseline}. Judged by the offline fake, so there is nothing to export.` })
            : el('p', { class: 'small' }, `Against production ${d.data.baseline}. Export: `, el('code', { text: `venv/bin/python scripts/jev_lab export ${digest}` }))];
          for (const ch of d.data.changes) {
            blocks.push(el('div', {}, el('b', { text: ch.name })), el('div', { class: 'old', text: JSON.stringify(ch.production, null, 1) }), el('div', { class: 'new', text: JSON.stringify(ch.candidate, null, 1) }));
          }
          holder.replaceChildren(...blocks);
        });
        parts.push(btn, holder);
      }
    }
    box.replaceChildren(...parts);
  }

  $('#ledger-refresh').addEventListener('click', loadLedger);
  $('#ledger-reset').addEventListener('click', async () => {
    const r = await api('/api/ledger/reset', { method: 'POST', body: {} });
    announce(r.ok ? 'The next run starts from the production wording.' : errorText(r));
    loadLedger();
    refreshStatus();
  });
  $('#ledger-rotate').addEventListener('click', async () => {
    const r = await api('/api/ledger/rotate', { method: 'POST', body: {} });
    announce(r.ok ? 'New split: fresh held-out cases, production wording.' : errorText(r));
    loadLedger();
    refreshStatus();
  });

  // ---------------------------------------------------------------- start
  applyTheme(theme);
  syncMotionButton();
  setKind(S.kind);
  const savedTab = $('#' + (store.get('jevLabTab') || 'tab-ask'));
  if (savedTab && savedTab.getAttribute('role') === 'tab') selectTab(savedTab);
  if (!TOKEN) showGate();
  else {
    refreshStatus();
    connect();
    setInterval(() => { refreshStatus(); }, 5000);
  }
  reducedMotion.addEventListener('change', requestDraw);
})();
