// Call player: two speaker lanes (client / operator+bot) over one mono recording.
// Lanes are derived from transcript timing: the recording is mono, so a bar is drawn in a lane when
// that speaker's turn covers the moment. Supports seek, speed, jump-to-start, region highlight.
import { fmtTime } from "../ui.js";

const REC_START = /запись и транскрибирование запущены|жазу және транскрипция басталды|recording .*started/i;
const LANES = [["client", "Клиент"], ["operator", "Оператор"]];

export function createPlayer(root, { src, transcript }) {
  // Audio time 0 == the "recording started" system event (if present), not the first transcript line.
  const recStart = (transcript.find(m => m.speaker === "system" && REC_START.test(m.text)) || {}).t || 0;
  const segs = { client: [], operator: [] };
  transcript.forEach((m, i) => {
    const lane = m.speaker === "client" ? "client" : (m.speaker === "operator" || m.speaker === "bot") ? "operator" : null;
    if (!lane || m.t == null) return;
    const next = transcript.slice(i + 1).find(x => x.t != null && x.t > m.t);
    const start = m.t - recStart;
    // A turn's timestamp marks its end of utterance in STT logs; approximate the span backwards, capped.
    segs[lane].push([Math.max(0, start - Math.min(8, 1 + m.text.length / 14)), next ? Math.min(start + 0.5, next.t - recStart) : start + 2]);
  });

  root.innerHTML = `
    <div class="lanes">
      ${LANES.map(([k, l]) => `<div class="lane-label">${l}</div><canvas data-lane="${k}" aria-label="Дорожка: ${l}"></canvas>`).join("")}
    </div>
    <div class="controls">
      <button class="play" data-play aria-label="Воспроизвести">▶</button>
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
  let peaks = null, region = null, raf = 0;
  const canvases = [...root.querySelectorAll("canvas")];
  const $ = s => root.querySelector(s);

  function draw() {
    const dur = audio.duration || 1;
    for (const cv of canvases) {
      const dpr = devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
      if (!w) continue;
      cv.width = w * dpr; cv.height = h * dpr;
      const g = cv.getContext("2d");
      g.scale(dpr, dpr);
      if (region) {
        g.fillStyle = "rgba(240,184,102,.28)";
        const x0 = region[0] / dur * w, x1 = Math.max(region[1] / dur * w, x0 + 6);
        g.fillRect(x0, 0, x1 - x0, h);
        g.fillStyle = "#f0b866"; g.fillRect(x0, 0, 1.5, h); g.fillRect(x1 - 1.5, 0, 1.5, h);
      }
      const lane = cv.dataset.lane, step = 4, n = Math.floor(w / step), pos = audio.currentTime / dur;
      for (let i = 0; i < n; i++) {
        const t = (i / n) * dur;
        const active = segs[lane].some(([a, b]) => t >= a && t <= b);
        const amp = peaks ? peaks[Math.floor((i / n) * peaks.length)] : 0.15;
        const bh = active ? Math.max(3, amp * (h - 6)) : 2;
        const played = i / n <= pos;
        g.fillStyle = active ? (lane === "client" ? (played ? "#0e3b2a" : "#3d6b50") : (played ? "#1f7a3a" : "#7cc08a")) : "#c9d3cc";
        g.fillRect(i * step, (h - bh) / 2, 2, bh);
      }
      g.fillStyle = "#145c2a";
      g.fillRect(pos * w, 0, 1.5, h);
    }
    const p = (audio.currentTime / (audio.duration || 1)) * 100;
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
        const decoded = await ctx.decodeAudioData(buf.slice(0));
        const ch = decoded.getChannelData(0), N = 1200, size = Math.floor(ch.length / N);
        peaks = new Float32Array(N);
        let max = 0;
        for (let i = 0; i < N; i++) {
          let s = 0;
          for (let j = i * size; j < (i + 1) * size; j += 8) s = Math.max(s, Math.abs(ch[j]));
          peaks[i] = s; max = Math.max(max, s);
        }
        peaks = peaks.map(x => x / (max || 1));
        ctx.close();
      } catch { /* waveform optional */ }
      draw();
    } catch (e) {
      $("[data-status]").textContent = `Запись недоступна: ${e.message}`;
    }
  }

  let pending = null; // seek requested before metadata loaded
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
    const op = transcript.find(m => m.speaker === "operator");
    if (op) seekTo(op.t - recStart - 2);
  };
  $("[data-rate]").onchange = e => { audio.playbackRate = +e.target.value; };
  audio.addEventListener("play", () => { $("[data-play]").textContent = "❚❚"; loop(); });
  audio.addEventListener("pause", () => { $("[data-play]").textContent = "▶"; draw(); });
  audio.addEventListener("loadedmetadata", () => {
    if (pending != null) { const p = pending; pending = null; seekTo(p); if (wantPlay) audio.play().catch(() => {}); }
    draw();
  });
  let wantPlay = false;
  const onResize = () => draw();
  addEventListener("resize", onResize);
  load();

  return {
    /** Audio position (s) for a transcript message. */
    timeOf: m => (m.t == null ? null : Math.max(0, m.t - recStart)),
    /** Seek to a message (with ~2s lead-in) and highlight [from, to] messages. */
    focus(fromMsg, toMsg, play = true) {
      const a = this.timeOf(fromMsg), b = this.timeOf(toMsg || fromMsg);
      if (a == null) return;
      region = [Math.max(0, a - 6), b + 1];
      wantPlay = play;
      seekTo(Math.max(0, a - 6));
      if (play && audio.readyState >= 1) audio.play().catch(() => {});
      draw();
    },
    destroy() { audio.pause(); cancelAnimationFrame(raf); removeEventListener("resize", onResize); },
  };
}
