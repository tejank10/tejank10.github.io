/**
 * ocean-bg.js — Bay-themed background animation with wind interaction.
 * Mouse movement acts as wind: horizontal velocity speeds/slows waves,
 * fast movement spawns a local gust that ripples outward from the cursor.
 */
(function () {
  "use strict";

  const OPACITY = 0.1;

  // Colour palette from the SF Bay photo
  const SKY_TOP = "#8fafc4";
  const SKY_BTM = "#c0d4df";
  const SEA_TOP = "#2f6ea3";
  const SEA_MID = "#1b4e7c";
  const SEA_BTM = "#122f4d";

  // Wave layers  { y, amp, freq, spd }
  // y   — resting vertical position (0–1 of viewport height)
  // amp — peak amplitude as fraction of viewport height
  // freq — horizontal frequency multiplier
  // spd  — base scroll speed (radians / second)
  const LAYERS = [
    { y: 0.58, amp: 0.022, freq: 0.70, spd: 0.28, alpha: 0.55 },
    { y: 0.66, amp: 0.016, freq: 1.00, spd: 0.20, alpha: 0.50 },
    { y: 0.74, amp: 0.012, freq: 1.40, spd: 0.34, alpha: 0.44 },
    { y: 0.82, amp: 0.009, freq: 1.90, spd: 0.42, alpha: 0.38 },
    { y: 0.90, amp: 0.006, freq: 2.60, spd: 0.52, alpha: 0.30 },
  ];

  // ── Canvas setup ──────────────────────────────────────────────────────────
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  Object.assign(canvas.style, {
    position: "fixed", top: "0", left: "0",
    width: "100%", height: "100%",
    zIndex: "-1", pointerEvents: "none",
  });
  document.body.insertBefore(canvas, document.body.firstChild);

  const ctx = canvas.getContext("2d");
  let W = 0, H = 0;

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  window.addEventListener("resize", resize, { passive: true });
  resize();

  // ── Wind state ────────────────────────────────────────────────────────────
  // windVx: signed horizontal wind velocity, –1 … +1
  //   positive = rightward wind = waves pushed right = phase advances
  // windMag: |windVx|, used for amplitude swell and gust strength
  let mouseX = -1;
  let windVx  = 0;          // current wind (decays each frame)
  let windTarget = 0;       // injected from mouse events, bleeds into windVx

  const WIND_INJECT_GAIN = 12;   // how strongly a mouse swipe injects wind
  const WIND_LERP        = 0.12; // how fast windVx tracks windTarget
  const WIND_DECAY       = 0.94; // per-frame decay of windTarget

  // Per-layer accumulated phase offset driven by wind
  // We shift phase continuously so the effect persists smoothly.
  const phaseOffset = LAYERS.map(() => 0);

  // Gusts — local ripple disturbances spawned by fast mouse movement
  // Each: { nx: normalised X, t0: birth time (s), str: strength 0–1 }
  const gusts = [];
  const MAX_GUSTS    = 8;
  const GUST_LIFE    = 2.2; // seconds before fully faded
  const GUST_SPEED   = 0.18; // how fast gust front travels (in normalised X/s)
  const GUST_SIGMA   = 0.09; // spatial spread of gust

  // Track mouse to derive instantaneous velocity
  let prevMouseX = -1, prevMouseTime = 0;

  window.addEventListener("mousemove", function (e) {
    const now = performance.now() * 0.001;
    const nx  = e.clientX / window.innerWidth;

    if (prevMouseX >= 0) {
      const dt = Math.max(0.001, now - prevMouseTime);
      const dx = nx - prevMouseX;
      const vx = dx / dt;                               // normalised px/s

      // Inject wind proportional to horizontal swipe speed
      windTarget += vx * WIND_INJECT_GAIN;
      windTarget  = Math.max(-1, Math.min(1, windTarget));

      // Spawn a gust when swiping fast enough
      const speed = Math.abs(vx);
      if (speed > 0.15 && gusts.length < MAX_GUSTS) {
        gusts.push({ nx, t0: now, str: Math.min(1, speed * 0.6) });
      }
    }

    mouseX     = e.clientX;
    prevMouseX = nx;
    prevMouseTime = now;
  }, { passive: true });

  // ── Gradient builders ─────────────────────────────────────────────────────
  function skyGrad() {
    const g = ctx.createLinearGradient(0, 0, 0, LAYERS[0].y * H);
    g.addColorStop(0, SKY_TOP);
    g.addColorStop(1, SKY_BTM);
    return g;
  }

  function seaGrad(topY) {
    const g = ctx.createLinearGradient(0, topY, 0, H);
    g.addColorStop(0,   SEA_TOP);
    g.addColorStop(0.4, SEA_MID);
    g.addColorStop(1,   SEA_BTM);
    return g;
  }

  // ── Gaussian helper ───────────────────────────────────────────────────────
  function gauss(x, mu, sigma) {
    const d = (x - mu) / sigma;
    return Math.exp(-0.5 * d * d);
  }

  // ── Wave path ─────────────────────────────────────────────────────────────
  // Builds a closed path for layer i at elapsed time t.
  // Incorporates wind-driven phase offset + active gusts.
  function wavePath(i, layer, t) {
    const baseY  = layer.y * H;
    const amp    = layer.amp * H;
    // Wind slightly swells amplitude of upper layers more
    const windSwell = 1 + Math.abs(windVx) * 0.45 * (1 - (layer.y - 0.55));
    const step  = Math.max(2, Math.ceil(W / 420));

    // Current gusts as an array we'll sample per-pixel
    const liveGusts = gusts.filter(g => (t - g.t0) < GUST_LIFE);

    ctx.beginPath();
    for (let x = 0; x <= W + step; x += step) {
      const nx = x / W;

      // Base two-harmonic wave
      let y = baseY
        + Math.sin(nx * layer.freq * Math.PI * 2 + t * layer.spd + phaseOffset[i]) * amp * windSwell
        + Math.sin(nx * layer.freq * Math.PI * 3.236 - t * layer.spd * 0.618 + phaseOffset[i] * 0.7)
          * amp * windSwell * 0.38;

      // Add gust contributions
      for (let g = 0; g < liveGusts.length; g++) {
        const gust = liveGusts[g];
        const age  = t - gust.t0;
        const life = age / GUST_LIFE;          // 0 → 1 over lifetime
        const fade = Math.sin(life * Math.PI); // bell curve: 0→1→0

        // Gust front travels in wind direction
        const front = gust.nx + windVx * GUST_SPEED * age;
        const spread = GUST_SIGMA + age * 0.04; // gust widens over time
        const spatial = gauss(nx, front, spread);

        // Higher layers (smaller y index) get more of the gust
        const layerFactor = 1 - (i / LAYERS.length) * 0.5;

        y -= gust.str * amp * 1.6 * fade * spatial * layerFactor;
      }

      x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.lineTo(W, H);
    ctx.lineTo(0, H);
    ctx.closePath();
  }

  // Sample Y of a wave at normalised position nx
  function sampleWaveY(i, layer, nx, t) {
    const amp = layer.amp * H;
    const windSwell = 1 + Math.abs(windVx) * 0.45 * (1 - (layer.y - 0.55));
    return layer.y * H
      + Math.sin(nx * layer.freq * Math.PI * 2 + t * layer.spd + phaseOffset[i]) * amp * windSwell
      + Math.sin(nx * layer.freq * Math.PI * 3.236 - t * layer.spd * 0.618 + phaseOffset[i] * 0.7)
        * amp * windSwell * 0.38;
  }

  // ── Sailboat ──────────────────────────────────────────────────────────────
  let boatNx = 0.38;

  function drawBoat(t) {
    // Boat drifts with the wind — faster when wind is strong
    boatNx = (boatNx + 0.000055 + windVx * 0.00018) % 1.0;
    if (boatNx < 0) boatNx += 1;

    const bx = boatNx * W;
    const by = sampleWaveY(0, LAYERS[0], boatNx, t);
    const s  = Math.min(W, H) * 0.016;

    ctx.save();
    ctx.translate(bx, by);
    ctx.globalAlpha = OPACITY * 4;
    ctx.strokeStyle = "#c8dde8";
    ctx.fillStyle   = "rgba(210, 232, 248, 0.75)";
    ctx.lineWidth   = Math.max(0.7, s * 0.055);
    ctx.lineCap     = "round";
    ctx.lineJoin    = "round";

    // Hull
    ctx.beginPath();
    ctx.moveTo(-s, 0);
    ctx.bezierCurveTo(-s, s * 0.4, s, s * 0.4, s, 0);
    ctx.stroke();

    // Mast (tilts slightly in the wind)
    const tilt = windVx * 0.18;
    ctx.beginPath();
    ctx.moveTo(s * 0.05, 0);
    ctx.lineTo(s * 0.05 + tilt * s, -s * 2.4);
    ctx.stroke();

    // Main sail (billows with wind — widens when wind is strong)
    const bellySx = s * 0.9 + Math.abs(windVx) * s * 0.5;
    ctx.beginPath();
    ctx.moveTo(s * 0.05 + tilt * s, -s * 2.2);
    ctx.quadraticCurveTo(bellySx, -s * 1.0, s * 0.05, -s * 0.05);
    ctx.fill();

    ctx.restore();
  }

  // ── Render loop ───────────────────────────────────────────────────────────
  let prevTs = 0, elapsed = 0;

  function frame(ts) {
    const dt = Math.min(ts - prevTs, 50) * 0.001;  // seconds, capped
    prevTs   = ts;
    elapsed += dt;

    // ── Wind physics ──────────────────────────────────────────────────────
    windTarget *= WIND_DECAY;
    windVx += (windTarget - windVx) * WIND_LERP;

    // Advance per-layer phase offsets based on wind
    // Upper layers (lower y index) are more wind-sensitive
    LAYERS.forEach(function (layer, i) {
      const sensitivity = 2.8 * (1 - i / (LAYERS.length - 1) * 0.5);
      phaseOffset[i] += windVx * sensitivity * dt;
    });

    // Prune expired gusts
    for (let i = gusts.length - 1; i >= 0; i--) {
      if (elapsed - gusts[i].t0 >= GUST_LIFE) gusts.splice(i, 1);
    }

    // ── Draw ──────────────────────────────────────────────────────────────
    ctx.clearRect(0, 0, W, H);

    const horizY = sampleWaveY(0, LAYERS[0], 0.5, elapsed) - LAYERS[0].amp * H * 0.8;

    // Sky
    ctx.save();
    ctx.globalAlpha = OPACITY * 1.2;
    ctx.fillStyle   = skyGrad();
    ctx.fillRect(0, 0, W, horizY + 4);
    ctx.restore();

    // Sea base
    ctx.save();
    ctx.globalAlpha = OPACITY;
    ctx.fillStyle   = seaGrad(horizY);
    ctx.fillRect(0, horizY, W, H - horizY);
    ctx.restore();

    // Wave layers
    LAYERS.forEach(function (layer, i) {
      wavePath(i, layer, elapsed);
      ctx.save();
      ctx.globalAlpha = OPACITY * layer.alpha;
      ctx.fillStyle   = seaGrad(layer.y * H - layer.amp * H * 1.5);
      ctx.fill();
      ctx.restore();

      // Foam crest — brighter in strong wind
      ctx.save();
      wavePath(i, layer, elapsed);
      ctx.globalAlpha = OPACITY * (0.22 + Math.abs(windVx) * 0.15);
      ctx.strokeStyle = "rgba(205, 235, 255, 0.9)";
      ctx.lineWidth   = Math.max(0.6, H * 0.0012 * (1 + Math.abs(windVx) * 0.6));
      ctx.stroke();
      ctx.restore();
    });

    drawBoat(elapsed);

    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
})();
