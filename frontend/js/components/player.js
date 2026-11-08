// Call player over one mono recording.
// Bar HEIGHT is the real loudness of the recording (RMS per 0.1 s), so indicators match what you hear.
// The transcript only COLOURS bars by speaker (mono audio, approximate timestamps); see align.js.
import { icon } from "../icons.js";
import { cssVar, fmtTime } from "../ui.js";
import { BIN, align, buildTimeline, loudness, utterDur } from "./align.js";

// Each lane shows sound only where its own speaker talks. "other" = IVR bot + sound no transcript line
// covers (e.g. hold music), so no audio is hidden and every bar is in exactly one lane.
const LANES = [["client", "Клиент"], ["operator", "Оператор"], ["other", "Бот / прочее"]];
const laneOf = who => (who === "client" || who === "operator" ? who : "other");
// Colors come from CSS tokens (--wave-*) so the waveform follows the light/dark theme.
// [played, unplayed]; "none" = speech that no transcript line covers.
let COLORS = null;
function readColors() {
  const v = n => cssVar(`--wave-${n}`);
  COLORS = {
    client: [v("client"), v("client-2")], operator: [v("operator"), v("operator-2")],
    bot: [v("bot"), v("bot-2")], none: [v("none"), v("none-2")],
    empty: v("empty"), cursor: v("cursor"), region: v("region"), regionEdge: cssVar("--hl-border"),
  };
}

export function createPlayer(root, { src, transcript }) {
  const toRec = buildTimeline(transcript);
  let env = null;         // Float32Array loudness per BIN, normalised 0..1
  let voiced = null;      // Uint8Array per BIN
  let owner = null;       // per BIN: "client" | "operator" | "bot" | "none"
  // Predicted [start, end] of a message in the recording; replaced by the calibrated one once audio is decoded.
  let span = m => { const e = toRec(m.t); return [e - utterDur(m), e]; };

  root.innerHTML = `
    <div class="lanes">
      ${LANES.map(([k, l]) => `<div class="lane-label${k === "other" ? " small muted" : ""}">${l}</div><canvas data-lane="${k}" aria-label="Дорожка: ${l}"${k === "other" ? ' class="short"' : ""}></canvas>`).join("")}
    </div>
    <div class="controls">
      <button class="play" data-play aria-label="Воспроизвести">${icon("play", 18)}</button>
      <span class="time" data-time>00:00 / --:--</span>
      <div class="progress" data-prog><i></i><b></b></div>
      <button class="btn ghost sm" data-start title="К началу записи">⏮ Начало</button>
      <button class="btn ghost sm" data-op title="К первой реплике оператора">↦ Оператор</button>
      <select data-rate aria-label="Скорость">
        ${[0.75, 1, 1.25, 1.5, 2].map(r => `<option value="${r}" ${r === 1 ? "selected" : ""}>${r}×</option>`).join("")}
      </select>
    </div>
    <div class="small muted" data-status>Загрузка записи…</div>`;

  const audio = new Audio();
  audio.preload = "auto";
  let region = null, raf = 0;
  const canvases = [...root.querySelectorAll("canvas")];
  const $ = s => root.querySelector(s);

  function analyse(decoded) {
    ({ env, voiced } = loudness(decoded.getChannelData(0), decoded.sampleRate));
    const al = align(transcript, voiced);
    owner = al.owner;
    span = al.span;
  }

  function draw() {
    if (!COLORS) readColors();
    const dur = audio.duration || (env ? env.length * BIN : 1);
    const pos = (audio.currentTime || 0) / dur;
    for (const cv of canvases) {
      const dpr = devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
      if (!w) continue;
      cv.width = w * dpr; cv.height = h * dpr;
      const g = cv.getContext("2d");
      g.scale(dpr, dpr);
      if (region) {
        g.fillStyle = COLORS.region;
        const x0 = region[0] / dur * w, x1 = Math.max(region[1] / dur * w, x0 + 6);
        g.fillRect(x0, 0, x1 - x0, h);
        g.fillStyle = COLORS.regionEdge; g.fillRect(x0, 0, 1.5, h); g.fillRect(x1 - 1.5, 0, 1.5, h);
      }
      const lane = cv.dataset.lane, step = 3, n = Math.floor(w / step);
      for (let i = 0; i < n; i++) {
        const played = i / n <= pos;
        if (!env) { g.fillStyle = COLORS.empty; g.fillRect(i * step, h / 2 - 1, 2, 2); continue; }
        // loudest bin inside this bar's time range -> bar height (true loudness)
        const a = Math.floor((i / n) * dur / BIN), b = Math.max(a + 1, Math.floor(((i + 1) / n) * dur / BIN));
        // loudest voiced bin of THIS lane's speaker within the bar
        let amp = 0, who = null;
        for (let k = a; k < Math.min(b, env.length); k++) {
          if (voiced[k] && laneOf(owner[k]) === lane && env[k] > amp) { amp = env[k]; who = owner[k]; }
        }
        if (!who) { g.fillStyle = COLORS.empty; g.fillRect(i * step, h / 2 - 1, 2, 2); continue; } // not this speaker
        const bh = Math.max(3, Math.sqrt(amp) * (h - 4));
        g.fillStyle = COLORS[who][played ? 0 : 1];
        g.fillRect(i * step, (h - bh) / 2, 2, bh);
      }
      g.fillStyle = COLORS.cursor;
      g.fillRect(pos * w, 0, 1.5, h);
    }
    const p = pos * 100;
    $("[data-prog] i").style.width = p + "%";
    $("[data-prog] b").style.left = p + "%";
    $("[data-time]").textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
  }
  const loop = () => { draw(); if (!audio.paused) raf = requestAnimationFrame(loop); };

  async function load() {
    try {
      const r = await fetch(src);
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
      const buf = await r.arrayBuffer();
      audio.src = URL.createObjectURL(new Blob([buf], { type: "audio/mpeg" }));
      $("[data-status]").textContent = "";
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        analyse(await ctx.decodeAudioData(buf.slice(0)));
        ctx.close();
        $("[data-status]").textContent = "Высота — громкость записи. Дорожка говорящего определяется по расшифровке (приблизительно, ±несколько секунд).";
      } catch { /* waveform optional; playback still works */ }
      draw();
    } catch (e) {
      $("[data-status]").textContent = `Запись недоступна: ${e.message}`;
    }
  }

  let pending = null, wantPlay = false; // seek requested before metadata loaded
  const seekTo = s => {
    s = Math.max(0, s);
    if (audio.readyState < 1) { pending = s; return; }
    audio.currentTime = Math.min(s, audio.duration || s);
    draw();
  };
  const seekFromEvent = (e, el) => {
    const r = el.getBoundingClientRect();
    seekTo(((e.clientX - r.left) / r.width) * (audio.duration || 0));
  };
  canvases.forEach(cv => cv.addEventListener("click", e => seekFromEvent(e, cv)));
  $("[data-prog]").addEventListener("click", e => seekFromEvent(e, $("[data-prog]")));
  $("[data-play]").onclick = () => (audio.paused ? audio.play() : audio.pause());
  $("[data-start]").onclick = () => seekTo(0);
  $("[data-op]").onclick = () => {
    // first operator line that is actually in the recording (some calls start recording late)
    const op = transcript.find(m => m.speaker === "operator" && m.t != null && span(m)[1] > 0);
    if (op) seekTo(span(op)[0] - 1.5);
  };
  $("[data-rate]").onchange = e => { audio.playbackRate = +e.target.value; };
  const playBtn = $("[data-play]");
  audio.addEventListener("play", () => { playBtn.innerHTML = icon("pause", 18); playBtn.setAttribute("aria-label", "Пауза"); loop(); });
  audio.addEventListener("pause", () => { playBtn.innerHTML = icon("play", 18); playBtn.setAttribute("aria-label", "Воспроизвести"); draw(); });
  audio.addEventListener("loadedmetadata", () => {
    if (pending != null) { const p = pending; pending = null; seekTo(p); if (wantPlay) audio.play().catch(() => {}); }
    draw();
  });
  const onResize = () => draw();
  const onTheme = () => { readColors(); draw(); };
  addEventListener("resize", onResize);
  addEventListener("cqa:theme", onTheme);
  load();

  return {
    /** Predicted start (s) of a message in the recording. */
    timeOf: m => (m.t == null ? null : Math.max(0, span(m)[0])),
    /** Seek to a message (1.5 s lead-in) and highlight [from, to]. */
    focus(fromMsg, toMsg, play = true) {
      if (fromMsg.t == null) return;
      const a = span(fromMsg)[0], b = span(toMsg || fromMsg)[1];
      if (b <= 0) {
        $("[data-status]").textContent = `Реплика #${fromMsg.turn} прозвучала до начала записи — в аудио её нет.`;
        return;
      }
      region = [Math.max(0, a - 1.5), b + 1];
      wantPlay = play;
      seekTo(Math.max(0, a - 1.5));
      if (play && audio.readyState >= 1) audio.play().catch(() => {});
      draw();
    },
    destroy() { audio.pause(); cancelAnimationFrame(raf); removeEventListener("resize", onResize); removeEventListener("cqa:theme", onTheme); },
  };
}
