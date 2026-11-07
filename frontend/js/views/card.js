import { api, getRole } from "../api.js";
import { createPlayer } from "../components/player.js";
import {
  CHANNEL, LANG, MARK, SPEAKER, esc, fmtNum, fmtTime, fmtTs, fmtValue, modal, optionsHtml, scoreTone, toast, tone, valueOptions, fmtDur, fmtUsd,
} from "../ui.js";

const AP_STATUS = { open: ["warn", "Апелляция на рассмотрении"], accepted: ["good", "Апелляция принята"], rejected: ["na", "Апелляция отклонена"] };

export async function mount(el, { id }) {
  const conv = await api.get(`/api/conversations/${encodeURIComponent(id)}`);
  const byTurn = Object.fromEntries(conv.transcript.map(m => [m.turn, m]));
  const isCall = !!conv.audio_url;
  let player = null, ev = null, appeals = [], pollTimer = 0;

  const last = conv.transcript[conv.transcript.length - 1];
  const dur = isCall ? fmtTime(last.t) : last.timestamp;
  el.innerHTML = `
    <div class="page-head">
      <div>
        <a href="#/conversations" class="small">← Все диалоги</a>
        <h1>Анализ разговора</h1>
        <div class="sub">${esc(CHANNEL[conv.channel] || conv.channel)} ${esc(conv.id)} · ${esc(LANG[conv.language] || conv.language)} · ${esc(dur)}
          ${conv.operator_name ? ` · Оператор: ${esc(conv.operator_name)}` : ""}</div>
      </div>
      <div class="row" data-head-actions></div>
    </div>
    ${isCall ? `<div class="card player" data-player style="margin-bottom:16px"></div>` : ""}
    <div class="grid2">
      <section class="card">
        <h2>Расшифровка</h2>
        <div class="transcript" data-transcript>
          ${conv.transcript.map(m => `
            <div class="msg ${m.speaker}" id="msg-${m.turn}" data-turn="${m.turn}">
              <div class="turn">#${m.turn}</div>
              <div>
                <div class="meta"><span class="ts ${isCall ? "seek" : ""}" ${isCall ? `data-seek="${m.turn}" title="Слушать с этого места"` : ""}>${esc(fmtTs(m))}</span>
                  <span class="who">${esc(SPEAKER[m.speaker] || m.speaker)}</span></div>
                <div class="text">${esc(m.text)}</div>
              </div>
            </div>`).join("")}
        </div>
      </section>
      <section class="card" data-score><h2>Оценка качества</h2><div class="empty">Загрузка…</div></section>
    </div>`;

  if (isCall) player = createPlayer(el.querySelector("[data-player]"), { src: api.url(`/api/audio/${encodeURIComponent(conv.id)}`), transcript: conv.transcript });

  const scoreEl = el.querySelector("[data-score]");
  const trEl = el.querySelector("[data-transcript]");

  function jump(turns, range) {
    trEl.querySelectorAll(".flash, .evidence").forEach(n => n.classList.remove("flash", "evidence"));
    const list = (turns || []).filter(t => byTurn[t]);
    if (range) for (let t = range[0]; t <= range[1]; t++) trEl.querySelector(`#msg-${t}`)?.classList.add("evidence");
    list.forEach(t => trEl.querySelector(`#msg-${t}`)?.classList.add("flash"));
    const first = trEl.querySelector(`#msg-${list[0] ?? (range && range[0])}`);
    if (first) trEl.scrollTop = first.offsetTop - trEl.offsetTop - 40;
    if (player && list.length) player.focus(byTurn[Math.min(...list)], byTurn[Math.max(...list)]);
    history.replaceState(null, "", `#/c/${encodeURIComponent(conv.id)}`);
  }

  trEl.addEventListener("click", e => {
    const s = e.target.closest("[data-seek]");
    if (s && player) player.focus(byTurn[+s.dataset.seek]);
  });

  async function load() {
    try {
      ev = await api.get(`/api/conversations/${encodeURIComponent(conv.id)}/evaluation`);
      appeals = await api.get(`/api/appeals?evaluation_id=${ev.id}`);
    } catch (e) {
      if (e.status !== 404) throw e;
      ev = null;
    }
    drawScore();
    if (ev && (ev.status === "queued" || ev.status === "running")) pollTimer = setTimeout(load, 1500);
  }

  function drawScore() {
    const actions = el.querySelector("[data-head-actions]");
    actions.innerHTML = `<button class="btn ghost" data-run>${ev ? "Переоценить" : "Оценить"}</button>`;
    actions.querySelector("[data-run]").onclick = async e => {
      e.target.disabled = true;
      try {
        await api.post("/api/evaluations", { conversation_ids: [conv.id], wait: true });
        toast("Оценка готова");
        await load();
      } catch (err) { toast(err.message, true); } finally { e.target.disabled = false; }
    };
    if (!ev) { scoreEl.innerHTML = `<h2>Оценка качества</h2><div class="empty">Диалог ещё не оценён.</div>`; return; }
    if (ev.status === "queued" || ev.status === "running") { scoreEl.innerHTML = `<h2>Оценка качества</h2><div class="empty">Оценивается…</div>`; return; }
    if (ev.status === "error") {
      scoreEl.innerHTML = `<h2>Оценка качества</h2><div class="alert bad">Оценка не выполнена</div><p class="small">${esc(ev.error)}</p>`;
      return;
    }

    const apBy = {};
    appeals.forEach(a => { (apBy[a.criterion_id] = apBy[a.criterion_id] || []).push(a); });
    const s = ev.final_score, changed = ev.final_score !== ev.original_score;
    const C = 2 * Math.PI * 70, frac = s == null ? 0 : s / 100;
    const ringColor = { good: "#1f7a3a", warn: "#c77a12", bad: "#c2412d", na: "#8a978e" }[scoreTone(s)];
    const lost = ev.criteria.filter(c => c.type !== "flag" && c.points != null && c.points < c.effective_weight - 0.005);
    const sections = Object.entries(ev.sections || {});

    scoreEl.innerHTML = `
      <div class="row"><h2 style="margin:0">Оценка качества</h2><span class="spacer"></span>
        <span class="small muted">Чек-лист v${ev.checklist.version} · ${esc(ev.model.name || ev.evaluator)}${usageText(ev)}</span></div>
      ${ev.critical_flag ? `<div class="alert bad" style="margin-top:10px">⚠ Выявлена грубая ошибка — отмечено отдельно, итог не обнуляется</div>` : ""}
      <div class="score-head" style="margin-top:12px">
        <div class="ring" role="img" aria-label="Итоговый балл ${fmtNum(s)} из 100">
          <svg width="160" height="160"><circle cx="80" cy="80" r="70" fill="none" stroke="#e8ede9" stroke-width="12"/>
            <circle cx="80" cy="80" r="70" fill="none" stroke="${ringColor}" stroke-width="12" stroke-linecap="round"
              stroke-dasharray="${C * frac} ${C}"/></svg>
          <div class="val"><b>${s == null ? "—" : fmtNum(s)}</b><span>/ 100</span>${changed ? `<s title="Исходная оценка">${fmtNum(ev.original_score)}</s>` : ""}</div>
        </div>
        <div class="sections">
          ${sections.map(([name, v]) => `<div><span>${esc(name)}</span><b>${fmtNum(v.earned)} <span class="muted">/ ${fmtNum(v.max)}</span></b></div>`).join("")}
          ${changed ? `<p class="change">Исходная оценка ${fmtNum(ev.original_score)} → после апелляции ${fmtNum(ev.final_score)}</p>` : ""}
        </div>
      </div>
      ${lost.length ? `<h3 style="margin-top:14px">Почему снижена оценка</h3>
        <ul class="why">${lost.map(c => `<li><b>${esc(c.title)}</b> — ${esc(c.rationale)}</li>`).join("")}</ul>` : ""}
      <h3 style="margin-top:14px">Критерии</h3>
      ${ev.criteria.map(c => critRow(c, apBy[c.criterion_id] || [])).join("")}
      <p class="small muted" style="margin-top:12px">Вес N/A-критериев перераспределён между применимыми. Баллы — после перераспределения.</p>`;
  }

  function critRow(c, aps) {
    const t = tone(c);
    const valChanged = JSON.stringify(c.final_value) !== JSON.stringify(c.original_value);
    const pts = c.type === "flag" ? `<span class="chip ${c.final_value ? "bad" : "good"}">${c.final_value ? "Выявлено" : "Нет"}</span>`
      : c.points == null ? `<span class="chip na">N/A</span>`
        : `<span class="pts"><b class="${t}">${fmtNum(c.points)}</b> <span class="muted">/ ${fmtNum(c.effective_weight)}</span></span>`;
    const lastAp = aps[0];
    return `<details class="crit" data-crit="${esc(c.criterion_id)}">
      <summary><span class="mark ${t}" aria-hidden="true">${MARK[t]}</span>
        <span>${esc(c.title)} ${lastAp ? `<span class="chip ${AP_STATUS[lastAp.status][0]}">${AP_STATUS[lastAp.status][1]}</span>` : ""}</span>${pts}</summary>
      <div class="body">
        <div class="row small"><span>Ответ: <b>${esc(fmtValue(c.final_value, c))}</b>${valChanged ? ` <span class="muted">(было: ${esc(fmtValue(c.original_value, c))})</span>` : ""}</span>
          <span class="muted">Вес ${fmtNum(c.weight)}${c.type !== "flag" && c.points != null ? ` → ${fmtNum(c.effective_weight)} после перераспределения` : ""}</span></div>
        <div>${esc(c.rationale)}</div>
        ${c.value === null && c.na_reason ? `<div class="small"><b>Причина N/A:</b> ${esc(c.na_reason)}</div>` : ""}
        <div class="row small">Доказательство:
          ${(c.evidence_turns || []).map(n => `<button class="ev" data-ev="${n}" title="${esc((byTurn[n] || {}).text || "")}">#${n} ${esc(SPEAKER[(byTurn[n] || {}).speaker] || "")}</button>`).join("")}
          ${c.checked_turns ? `<span class="muted">· проверен участок #${c.checked_turns[0]}–#${c.checked_turns[1]}</span>` : ""}</div>
        ${aps.map(a => `<div class="quote small"><b>${AP_STATUS[a.status][1]}</b> · ${esc(a.comment)}
            ${a.status !== "open" ? `<br>Решение: ${esc(a.reviewer_comment)}${a.status === "accepted" ? ` (новое значение: ${esc(fmtValue(a.new_value, c))})` : ""}` : ""}
            ${a.improvement ? `<br>Что доработать: ${esc(a.improvement)}` : ""}</div>`).join("")}
        <div class="row">
          <button class="btn sm" data-jump="${esc(c.criterion_id)}">Перейти к фрагменту</button>
          <button class="btn ghost sm" data-appeal="${esc(c.criterion_id)}" ${aps.some(a => a.status === "open") ? "disabled title='Уже на рассмотрении'" : ""}>Оспорить оценку</button>
        </div>
      </div>
    </details>`;
  }

  scoreEl.addEventListener("click", e => {
    const evb = e.target.closest("[data-ev]");
    if (evb) return jump([+evb.dataset.ev]);
    const j = e.target.closest("[data-jump]");
    if (j) { const c = ev.criteria.find(x => x.criterion_id === j.dataset.jump); return jump(c.evidence_turns, c.checked_turns); }
    const ap = e.target.closest("[data-appeal]");
    if (ap) openAppeal(ap.dataset.appeal);
  });

  function openAppeal(cid) {
    const open = new Set(appeals.filter(a => a.status === "open").map(a => a.criterion_id));
    const crits = ev.criteria.filter(c => !open.has(c.criterion_id));
    modal(`
      <h2>Оспорить оценку</h2>
      <label class="f">Критерий<select data-c>${crits.map(c => `<option value="${esc(c.criterion_id)}" ${c.criterion_id === cid ? "selected" : ""}>${esc(c.title)} — ${esc(fmtValue(c.final_value, c))}</option>`).join("")}</select></label>
      <div class="quote small" data-ctx></div>
      <label class="f">Предлагаемое значение (необязательно)<select data-v></select></label>
      <label class="f">Комментарий<textarea rows="4" data-comment placeholder="Почему вы не согласны с оценкой?"></textarea></label>
      ${getRole() !== "operator" ? `<div class="alert info small">Подаёт оператор. Вы сейчас в роли «${getRole() === "admin" ? "Администратор" : "Главный специалист"}» — для демо это допустимо.</div>` : ""}
      <div class="row"><span class="spacer"></span><button class="btn ghost" data-close>Отмена</button><button class="btn" data-send>Отправить</button></div>`,
    (m, close) => {
      const sel = m.querySelector("[data-c]");
      const sync = () => {
        const c = ev.criteria.find(x => x.criterion_id === sel.value);
        m.querySelector("[data-ctx]").innerHTML = `${esc(c.rationale)}<br><span class="muted">Доказательство: ${(c.evidence_turns || []).map(n => `#${n}`).join(", ")}</span>`;
        m.querySelector("[data-v]").innerHTML = `<option value="">— не указано —</option>` + optionsHtml(valueOptions(c).filter(([v]) => JSON.stringify(v) !== JSON.stringify(c.final_value)));
      };
      sel.onchange = sync; sync();
      m.querySelector("[data-send]").onclick = async () => {
        const comment = m.querySelector("[data-comment]").value.trim();
        if (comment.length < 3) return toast("Добавьте комментарий", true);
        const v = m.querySelector("[data-v]").value;
        try {
          await api.post("/api/appeals", { evaluation_id: ev.id, criterion_id: sel.value, comment, suggested_value: v ? JSON.parse(v) : null });
          close();
          toast("Апелляция отправлена проверяющему");
          dispatchEvent(new Event("cqa:appeals"));
          await load();
        } catch (err) { toast(err.message, true); }
      };
    });
  }

  await load();
  return { unmount() { clearTimeout(pollTimer); player && player.destroy(); } };
}

/** " · 4.2 с · 3 100 → 600 токенов · $0.012" for the score header. */
function usageText(ev) {
  const u = ev.usage || {}, parts = [];
  if (ev.duration_s != null) parts.push(fmtDur(ev.duration_s));
  if (u.input_tokens != null || u.output_tokens != null)
    parts.push(`${(u.input_tokens || 0).toLocaleString("ru")} → ${(u.output_tokens || 0).toLocaleString("ru")} токенов`);
  if (u.cost_usd != null) parts.push(fmtUsd(u.cost_usd) + (u.cost_source === "price_table" ? " (по тарифу)" : ""));
  return parts.length ? " · " + parts.join(" · ") : "";
}
