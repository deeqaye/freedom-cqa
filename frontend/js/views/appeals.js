import { api, getRole } from "../api.js";
import { icon } from "../icons.js";
import { SPEAKER, esc, fmtNum, fmtTs, fmtValue, modal, optionsHtml, skeleton, toast, valueOptions } from "../ui.js";

const ST = { open: ["warn", "На рассмотрении"], accepted: ["good", "Принята"], rejected: ["na", "Отклонена"] };
const EVENT = { created: ["warn", "Подана"], accepted: ["good", "Принята"], rejected: ["na", "Отклонена"] };
const ROLE = { operator: "Оператор", lead: "Главный специалист", admin: "Администратор" };
const fmtDate = d => new Date(d).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

export async function mount(el, { id }) {
  let filter = "open", list = [];
  el.innerHTML = `
    <div class="page-head"><div><h1>Апелляции</h1><div class="sub">Оспоренные оценки и решения проверяющего</div></div>
      <div class="seg" data-filter>
        <button data-s="open">Открытые</button><button data-s="accepted">Принятые</button><button data-s="rejected">Отклонённые</button><button data-s="">Все</button><button data-s="history">${icon("clock", 15)} История</button>
      </div></div>
    <div class="card" data-history hidden></div>
    <div class="split" data-split><div class="card" data-list></div><div class="card" data-detail><div class="empty-state">${icon("scale", 32)}<p>Выберите апелляцию слева, чтобы увидеть фрагмент и принять решение.</p></div></div></div>`;
  const listEl = el.querySelector("[data-list]"), detEl = el.querySelector("[data-detail]");
  const histEl = el.querySelector("[data-history]"), splitEl = el.querySelector("[data-split]");

  /** Stored log of every filed / accepted / rejected appeal (kept in the DB, survives restarts). */
  async function loadHistory() {
    histEl.innerHTML = skeleton("table", 6);
    const h = await api.get("/api/appeals/history");
    const canClear = ["admin", "lead"].includes(getRole());
    const change = e => {
      if (e.action === "created") return e.new_value != null ? `${esc(fmtValue(e.old_value))} → предлагает <b>${esc(fmtValue(e.new_value))}</b>` : `оспорено: ${esc(fmtValue(e.old_value))}`;
      if (e.action === "accepted") return `${esc(fmtValue(e.old_value))} → <b>${esc(fmtValue(e.new_value))}</b>`;
      return `<span class="muted">без изменений</span>`;
    };
    const score = e => (e.score_before == null || e.score_before === e.score_after ? "" :
      `${fmtNum(e.score_before)} → <b>${fmtNum(e.score_after)}</b>`);
    histEl.innerHTML = `
      <div class="card-head"><h2>История апелляций</h2>
        <span class="muted small">${h.total} ${h.total === 1 ? "событие" : "событий"}${h.total > h.events.length ? ` · показаны последние ${h.events.length}` : ""}</span>
        <span class="spacer"></span>
        ${canClear ? `<button class="btn danger sm" data-clear ${h.total ? "" : "disabled"}>Очистить историю</button>` : ""}</div>
      ${h.events.length ? `<div class="tbl-wrap"><table class="tbl"><thead><tr>
          <th>Когда</th><th>Событие</th><th>Диалог</th><th>Критерий</th><th>Кто</th><th>Значение</th><th class="num">Итог диалога</th><th>Комментарий</th>
        </tr></thead><tbody>${h.events.map(e => `
          <tr class="${e.appeal_id ? "click" : ""}" data-ap="${e.appeal_id ?? ""}" title="Открыть апелляцию">
            <td class="small">${esc(fmtDate(e.created_at))}</td>
            <td><span class="chip dot ${EVENT[e.action]?.[0] || "na"}">${EVENT[e.action]?.[1] || esc(e.action)}</span></td>
            <td><span class="id">${esc(e.conversation_id || "—")}</span></td>
            <td>${esc(e.criterion_title || e.criterion_id || "—")}</td>
            <td>${esc(ROLE[e.role] || e.role)}</td>
            <td class="small">${change(e)}</td>
            <td class="num small">${score(e)}</td>
            <td class="small">${esc(e.comment || "")}</td></tr>`).join("")}</tbody></table></div>`
        : `<div class="empty-state">${icon("clock", 32)}<p>История пуста. Здесь появятся поданные апелляции и решения по ним.</p></div>`}`;
    histEl.querySelector("[data-clear]")?.addEventListener("click", () => modal(`
      <h2>Очистить историю апелляций?</h2>
      <p>Будут удалены все ${h.total} записей журнала. Сами апелляции, их статусы и изменённые баллы <b>сохранятся</b>.</p>
      <label class="row small"><input type="checkbox" data-ok> Я понимаю, что журнал нельзя восстановить</label>
      <div class="row"><span class="spacer"></span><button class="btn ghost" data-close>Отмена</button><button class="btn danger" data-go disabled>Очистить</button></div>`,
    (m, close) => {
      m.querySelector("[data-ok]").onchange = e => { m.querySelector("[data-go]").disabled = !e.target.checked; };
      m.querySelector("[data-go]").onclick = async e => {
        e.target.disabled = true;
        try {
          const r = await api.del("/api/appeals/history");
          close();
          toast(`История очищена: удалено записей — ${r.deleted}`);
          await loadHistory();
        } catch (err) { toast(err.message, true); e.target.disabled = false; }
      };
    }));
  }
  histEl.addEventListener("click", async e => {
    const tr = e.target.closest("tr[data-ap]");
    if (!tr || !tr.dataset.ap) return;
    filter = "";
    await setTab();
    await showDetail(+tr.dataset.ap);
  });

  async function setTab() {
    const isHist = filter === "history";
    el.querySelectorAll("[data-s]").forEach(b => b.classList.toggle("on", b.dataset.s === filter));
    histEl.hidden = !isHist;
    splitEl.hidden = isHist;
    if (isHist) { history.replaceState(null, "", "#/appeals"); return loadHistory(); }
    return loadList();
  }

  async function loadList() {
    el.querySelectorAll("[data-s]").forEach(b => b.classList.toggle("on", b.dataset.s === filter));
    list = await api.get(`/api/appeals${filter ? `?status=${filter}` : ""}`);
    listEl.innerHTML = list.map(a => `
      <div class="ap-item ${a.id === id ? "active" : ""}" data-id="${a.id}">
        <div class="row"><b>${esc(a.conversation_id)}</b><span class="spacer"></span><span class="chip ${ST[a.status][0]}">${ST[a.status][1]}</span></div>
        <div>${esc(a.criterion_title)} · <span class="muted">${esc(fmtValue(a.original_value, a))}</span></div>
        <div class="small muted">${esc(a.comment.slice(0, 90))}</div>
      </div>`).join("") || `<div class="empty-state">${icon("inbox", 32)}<p>Нет апелляций${filter === "open" ? " на рассмотрении" : ""}</p></div>`;
  }

  async function showDetail(aid) {
    id = aid;
    listEl.querySelectorAll(".ap-item").forEach(n => n.classList.toggle("active", +n.dataset.id === aid));
    const a = await api.get(`/api/appeals/${aid}`);
    const canDecide = ["admin", "lead"].includes(getRole());
    const crit = { type: a.criterion_type, steps: a.steps, na_allowed: a.na_allowed };
    detEl.innerHTML = `
      <div class="card-head"><h2>${esc(a.criterion_title)}</h2><span class="spacer"></span><span class="chip ${ST[a.status][0]}">${ST[a.status][1]}</span></div>
      <p class="small muted">Диалог <a href="#/c/${encodeURIComponent(a.conversation_id)}">${esc(a.conversation_id)}</a> · оценка #${a.evaluation_id} · подал: ${esc(a.author_role)}</p>
      <div class="grid2 gap-3">
        <div><h3>Спорная оценка</h3>
          <p><b>${esc(fmtValue(a.original_value, crit))}</b> <span class="muted">(вес ${fmtNum(a.weight)})</span></p>
          <p class="small">${esc(a.rationale)}</p></div>
        <div><h3>Комментарий оператора</h3><div class="quote">${esc(a.comment)}</div>
          ${a.suggested_value !== null && a.suggested_value !== undefined ? `<p class="small">Предлагает: <b>${esc(fmtValue(a.suggested_value, crit))}</b></p>` : ""}</div>
      </div>
      <h3 class="mt-2">Фрагмент диалога</h3>
      <div class="excerpt">${(a.excerpt || []).map(m => `
        <div class="msg ${m.speaker} ${(a.evidence_turns || []).includes(m.turn) ? "evidence" : ""}"><div class="turn">#${m.turn}</div>
          <div><div class="meta"><span class="ts">${esc(fmtTs(m))}</span><span class="who">${esc(SPEAKER[m.speaker])}</span></div><div class="text">${esc(m.text)}</div></div></div>`).join("")}
      </div>
      <p><a href="#/c/${encodeURIComponent(a.conversation_id)}">Открыть карточку целиком →</a></p>
      ${a.status === "open" ? (canDecide ? `
        <h3>Решение проверяющего</h3>
        <div class="stack gap-2">
          <div class="seg" data-dec><button data-d="reject" class="on">Оценка верна (отклонить)</button><button data-d="accept">Изменить оценку (принять)</button></div>
          <label class="f" data-newv hidden>Новое значение<select>${optionsHtml(valueOptions(crit).filter(([v]) => JSON.stringify(v) !== JSON.stringify(a.original_value)), a.suggested_value)}</select></label>
          <label class="f">Причина решения<textarea rows="3" data-reason placeholder="Обоснование для оператора"></textarea></label>
          <label class="f">Что можно доработать (подсказка оператору)<textarea rows="2" data-impr></textarea></label>
          <div class="row"><span class="spacer"></span><button class="btn" data-save>Сохранить решение</button></div>
        </div>` : `<div class="alert info">Решение принимает главный специалист или администратор — переключите роль слева.</div>`)
        : `<h3>Решение</h3>
          <p>${a.status === "accepted" ? `Оценка изменена: <b>${esc(fmtValue(a.original_value, crit))} → ${esc(fmtValue(a.new_value, crit))}</b>` : "Исходная оценка подтверждена"}
            <span class="muted">· ${esc(a.reviewer_role)} · ${new Date(a.decided_at).toLocaleString("ru-RU")}</span></p>
          <div class="quote">${esc(a.reviewer_comment)}</div>
          ${a.improvement ? `<p class="small"><b>Что доработать:</b> ${esc(a.improvement)}</p>` : ""}
          <p>Итог диалога: исходный <b>${fmtNum(a.score_before)}</b> → финальный <b>${fmtNum(a.score_after)}</b></p>`}`;

    let decision = "reject";
    detEl.querySelector("[data-dec]")?.addEventListener("click", e => {
      const b = e.target.closest("[data-d]");
      if (!b) return;
      decision = b.dataset.d;
      detEl.querySelectorAll("[data-d]").forEach(x => x.classList.toggle("on", x === b));
      detEl.querySelector("[data-newv]").hidden = decision !== "accept";
    });
    const save = detEl.querySelector("[data-save]");
    if (save) save.onclick = async () => {
      const reason = detEl.querySelector("[data-reason]").value.trim();
      if (reason.length < 3) return toast("Укажите причину решения", true);
      const body = { decision, reason, improvement: detEl.querySelector("[data-impr]").value.trim() || null };
      if (decision === "accept") body.new_value = JSON.parse(detEl.querySelector("[data-newv] select").value);
      save.disabled = true;
      try {
        const r = await api.post(`/api/appeals/${a.id}/decision`, body);
        toast(`Решение сохранено. Итог: ${fmtNum(r.score_before)} → ${fmtNum(r.score_after)}`);
        dispatchEvent(new Event("cqa:appeals"));
        await loadList();
        await showDetail(a.id);
      } catch (err) { toast(err.message, true); save.disabled = false; }
    };
    history.replaceState(null, "", `#/appeals/${aid}`);
  }

  el.querySelector("[data-filter]").addEventListener("click", async e => {
    const b = e.target.closest("[data-s]");
    if (b) { filter = b.dataset.s; await setTab(); }
  });
  listEl.addEventListener("click", e => {
    const it = e.target.closest("[data-id]");
    if (it) showDetail(+it.dataset.id);
  });

  if (id) filter = "";
  await loadList();
  if (id) await showDetail(id);
  else if (list[0]) await showDetail(list[0].id);
}
