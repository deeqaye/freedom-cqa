// Pure (DOM-free) alignment of a mono call recording with its transcript. Used by player.js.
//   * loudness per BIN seconds from raw samples (true volume, robust normalisation)
//   * transcript time -> recording time, with "recording paused" intervals cut out
//   * per-call offset calibration + per-bin speaker attribution
export const BIN = 0.1;

const REC_START = /запись и транскрибирование запущены|жазу және транскрипция басталды|recording .*started/i;
const PAUSE = /приостановлен|тоқтатыл|paused/i;
const RESUME = /возобновлен|жалғастырыл|resumed/i;

/** Time of the "recording started" event (s from first message), or 0. */
export const recordingStart = transcript =>
  (transcript.find(m => m.speaker === "system" && REC_START.test(m.text)) || {}).t || 0;

/** Transcript time (s from first message) -> recording time (before calibration). */
export function buildTimeline(transcript) {
  const recStart = recordingStart(transcript);
  const pauses = [];
  let p = null;
  for (const m of transcript) {
    if (m.speaker !== "system" || m.t == null) continue;
    if (PAUSE.test(m.text)) p = m.t;
    else if (RESUME.test(m.text) && p != null) { pauses.push([p, m.t]); p = null; }
  }
  return t => t - recStart - pauses.reduce((s, [a, b]) => s + (t > a ? Math.min(t, b) - a : 0), 0);
}

/** Estimated utterance length from text (≈14 chars/s), clamped. */
export const utterDur = m => Math.min(15, Math.max(0.6, m.text.length / 14));

/** Loudness envelope from samples: env 0..1 per BIN and a voiced flag per BIN. */
export function loudness(samples, sampleRate) {
  const hop = Math.max(1, Math.round(sampleRate * BIN)), n = Math.ceil(samples.length / hop);
  const rms = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let s = 0, k = 0;
    for (let j = i * hop; j < Math.min(samples.length, (i + 1) * hop); j += 2) { s += samples[j] * samples[j]; k++; }
    rms[i] = Math.sqrt(s / (k || 1));
  }
  const sorted = Array.from(rms).sort((a, b) => a - b);
  const floor = sorted[Math.floor(n * 0.2)] || 0;   // background noise
  const top = sorted[Math.floor(n * 0.98)] || 1;    // loud speech, robust to clicks
  const thr = floor + (top - floor) * 0.12;
  const env = new Float32Array(n), voiced = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    env[i] = Math.min(1, Math.max(0, (rms[i] - floor) / (top - floor || 1)));
    voiced[i] = rms[i] > thr ? 1 : 0;
  }
  return { env, voiced };
}

/**
 * Calibrate the offset and attribute voiced bins to speakers.
 * Returns { shift, span(m) -> [start, end] in recording seconds, owner: per-bin speaker | "none", score }.
 */
export function align(transcript, voiced) {
  const toRec = buildTimeline(transcript);
  const turns = transcript.filter(m => m.t != null && ["client", "operator", "bot"].includes(m.speaker));
  const people = turns.filter(m => m.speaker !== "bot");
  let shift = 0;
  const span = m => { const e = toRec(m.t) + shift; return [e - utterDur(m), e]; };
  const vf = (a, b) => {
    const i = Math.max(0, Math.floor(a / BIN)), j = Math.min(voiced.length, Math.ceil(b / BIN));
    let s = 0;
    for (let k = i; k < j; k++) s += voiced[k];
    return j > i ? s / (j - i) : 0;
  };
  let best = [-1, 0];
  for (let c = -8; c <= 8.001; c += 0.5) {
    shift = c;
    const score = people.reduce((s, m) => { const [a, b] = span(m); return s + vf(a, b); }, 0) / (people.length || 1);
    if (score > best[0] + 1e-6 || (Math.abs(score - best[0]) < 1e-6 && Math.abs(c) < Math.abs(best[1]))) best = [score, c];
  }
  shift = best[1];
  const spans = turns.map(m => [...span(m), m.speaker]);
  const owner = new Array(voiced.length).fill("none");
  for (let i = 0; i < voiced.length; i++) {
    if (!voiced[i]) continue;
    const t = i * BIN;
    let bestD = 1.5, who = "none";
    for (const [a, b, sp] of spans) {
      const d = t < a ? a - t : t > b ? t - b : 0;
      if (d < bestD) { bestD = d; who = sp; }
    }
    owner[i] = who;
  }
  return { shift, span, owner, score: best[0], toRec };
}
