import { api } from "./api.js";
import { icon } from "./icons.js";

export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const SPEAKER = { client: "Клиент", operator: "Оператор", bot: "Бот", system: "Система" };
export const LANG = { RU: "Русский", KZ: "Қазақша", EN: "English" };
export const CHANNEL = { "agent chat": "Чат", "voice call": "Звонок" };

export function fmtNum(x, d = 2) {
  if (x === null || x === undefined) return "—";
  return Number(x).toLocaleString("ru-RU", { maximumFractionDigits: d });
}
export function fmtTime(s) {
  if (s == null || isNaN(s)) return "--:--";
  s = Math.max(0, Math.floor(s));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
export function fmtTs(m) {
  // chats keep MM:SS; calls show HH:MM:SS of the original ISO timestamp
  const ts = m.timestamp || "";
  if (ts.includes("T")) return ts.slice(11, 19);
  return ts;
}

/** Human value of a criterion answer. */
export function fmtValue(v, c) {
  if (v === null || v === undefined) return "N/A";
  if (v === true) return "Да";
  if (v === false) return "Нет";
  if (c && c.steps) return `${v} / ${Math.max(...c.steps)}`;
  return String(v);
}

/** Tone of a criterion result: good / warn / bad / na. */
export function tone(row) {
  const v = row.final_value !== undefined ? row.final_value : row.value;
  if (row.type === "flag") return v ? "bad" : "good";
  if (v === null || v === undefined) return "na";
  if (v === true) return "good";
  if (v === false) return "bad";
  const max = Math.max(...(row.steps || [v]));
  return v >= max ? "good" : v > 0 ? "warn" : "bad";
}
export const MARK = { good: "✓", bad: "✕", warn: "~", na: "—" };

export function scoreTone(s) {
  if (s == null) return "na";
  return s >= 85 ? "good" : s >= 65 ? "warn" : "bad";
}

/** Value options for a criterion (used by appeal + decision forms). */
export function valueOptions(c) {
  const opts = c.type === "scale" ? c.steps.map(s => [s, String(s)]) : [[true, "Да"], [false, "Нет"]];
  if (c.na_allowed) opts.push([null, "N/A"]);
  return opts;
}
export const optionsHtml = (opts, selected) =>
  opts.map(([v, l]) => `<option value='${esc(JSON.stringify(v))}' ${JSON.stringify(v) === JSON.stringify(selected) ? "selected" : ""}>${esc(l)}</option>`).join("");

let toastTimer;
export function toast(msg, isErr = false) {
  const el = document.getElementById("toast");
  el.innerHTML = `${icon(isErr ? "alert" : "check", 18)}<span>${esc(msg)}</span>`;
  el.className = "toast show" + (isErr ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = "toast"; }, isErr ? 6000 : 3000);
}

export function modal(html, onMount) {
  const bg = document.createElement("div");
  bg.className = "modal-bg";
  bg.innerHTML = `<div class="modal" role="dialog" aria-modal="true">${html}</div>`;
  const close = () => bg.remove();
  bg.addEventListener("click", e => { if (e.target === bg || e.target.closest("[data-close]")) close(); });
  document.addEventListener("keydown", function onKey(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", onKey); }
  });
  document.body.appendChild(bg);
  onMount && onMount(bg.querySelector(".modal"), close);
  bg.querySelector(".modal input:not([type=checkbox]), .modal select, .modal textarea, .modal button:not([data-close])")?.focus();
  return close;
}

/**
 * Runs an evaluation batch and renders progress into `el`. Resolves when all jobs finished.
 * body: {group_id | conversation_ids, checklist_id?, checklist_version?}
 */
export async function runBatch(el, body) {
  const res = await api.post("/api/evaluations", body);
  const ids = res.evaluation_ids;
  el.innerHTML = `<div class="row"><div class="pbar"><i style="width:0"></i></div><span class="small muted" data-p>0 / ${ids.length}</span></div>`;
  const bar = el.querySelector("i"), lbl = el.querySelector("[data-p]");
  while (true) {
    await new Promise(r => setTimeout(r, 1200));
    const p = await api.get(`/api/evaluations/progress?ids=${ids.join(",")}`);
    const done = (p.ok || 0) + (p.error || 0);
    bar.style.width = `${(done / ids.length) * 100}%`;
    lbl.textContent = `${done} / ${ids.length}` + (p.error ? ` · ошибок: ${p.error}` : "");
    if (done >= ids.length) {
      const cost = await api.get(`/api/stats/cost?ids=${ids.join(",")}`).catch(() => null);
      if (cost) el.insertAdjacentHTML("beforeend", `<div class="small muted mt-1">${costLine(cost)}</div>`);
      return { ...p, cost };
    }
  }
}

/** USD with enough digits for sub-cent amounts. */
export function fmtUsd(x) {
  if (x == null) return "—";
  if (x === 0) return "$0";
  return "$" + (x < 0.01 ? x.toPrecision(2) : x.toFixed(x < 1 ? 4 : 2));
}

/** Seconds -> "4.2 с" / "3 мин 12 с". */
export function fmtDur(s) {
  if (s == null) return "—";
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} с`;
  return `${Math.floor(s / 60)} мин ${Math.round(s % 60)} с`;
}

/** One-line summary of /api/stats/cost. */
export function costLine(c) {
  const parts = [`${c.evaluations} оценок`];
  if (c.time.wall_clock_s != null) parts.push(`за ${fmtDur(c.time.wall_clock_s)}`);
  if (c.time.avg_s != null) parts.push(`≈${fmtDur(c.time.avg_s)} на диалог`);
  if (c.tokens.avg_per_evaluation != null) parts.push(`≈${c.tokens.avg_per_evaluation.toLocaleString("ru")} токенов`);
  if (c.cost.total_usd != null) parts.push(`${fmtUsd(c.cost.total_usd)} всего, ${fmtUsd(c.cost.avg_per_evaluation_usd)} на диалог`);
  else parts.push("стоимость не сообщена оценщиком");
  return parts.join(" · ");
}

/** Hover tooltip for chart marks with data-tip. */
export function attachTips(root) {
  let tip = document.querySelector(".tip");
  if (!tip) { tip = document.createElement("div"); tip.className = "tip"; document.body.appendChild(tip); }
  root.addEventListener("mousemove", e => {
    const t = e.target.closest("[data-tip]");
    if (!t) { tip.style.display = "none"; return; }
    tip.innerHTML = t.dataset.tip;
    tip.style.display = "block";
    tip.style.left = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8) + "px";
    tip.style.top = e.clientY + 14 + "px";
  });
  root.addEventListener("mouseleave", () => { tip.style.display = "none"; });
}

/** Current value of a CSS custom property (theme-aware colors for canvas drawing). */
export const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/** Shimmer placeholders while data loads: "page" | "table" | "card" | "tiles". */
export function skeleton(kind = "page", n = 8) {
  const line = (w, h = 12) => `<span class="skel" style="width:${w};height:${h}px"></span>`;
  const table = `<div class="skel-table">${Array.from({ length: n }, (_, i) =>
    `<div class="skel-row">${line("14%")}${line("10%")}${line("6%")}${line(`${18 + (i % 3) * 6}%`)}${line("8%")}</div>`).join("")}</div>`;
  const tiles = `<div class="tiles">${Array.from({ length: 4 }, () => `<div class="card tile">${line("50%", 10)}${line("40%", 26)}</div>`).join("")}</div>`;
  const card = `<div class="skel-card"><span class="skel skel-ring"></span><div class="skel-lines">${line("90%")}${line("75%")}${line("82%")}${line("60%")}</div></div>`;
  if (kind === "table") return table;
  if (kind === "tiles") return tiles;
  if (kind === "card") return card;
  return `<div class="skel-page" aria-busy="true" aria-label="Загрузка">
    <div class="page-head"><div>${line("220px", 26)}<div class="mt-2">${line("320px", 14)}</div></div></div>
    <div class="card">${table}</div></div>`;
}
