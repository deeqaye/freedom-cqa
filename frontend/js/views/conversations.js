import { api, getRole } from "../api.js";
import { CHANNEL, esc, fmtNum, modal, costLine, runBatch, scoreTone, toast } from "../ui.js";

// Sortable columns: key -> [header, value getter]. null values always go last.
const STATUS_RANK = { ok: 0, error: 1, running: 2, queued: 3 };
const okScore = r => (r.evaluation && r.evaluation.status === "ok" ? r.evaluation.final_score : null);
const COLS = [
  ["id", "ID", r => r.id],
  ["channel", "Канал", r => CHANNEL[r.channel] || r.channel],
  ["language", "Язык", r => r.language],
  ["operator", "Оператор", r => r.operator_name || null],
  ["turns", "Реплик", r => r.turns, "num"],
  ["score", "Итог", okScore, "num"],
  ["critical", "Грубая ошибка", r => (r.evaluation && r.evaluation.status === "ok" ? (r.evaluation.critical_flag ? 1 : 0) : null)],
  ["status", "Статус", r => (r.evaluation ? STATUS_RANK[r.evaluation.status] ?? 9 : 10)],
];
const byId = (a, b) => a.id.localeCompare(b.id, "ru", { numeric: true });
const cmpVal = (a, b) => (typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), "ru", { numeric: true }));

const STATUS = { ok: ["good", "Оценён"], error: ["bad", "Ошибка"], queued: ["info", "В очереди"], running: ["info", "Оценивается"] };

export async function mount(el) {
  const state = { group: "", language: "", channel: "", q: "", sortKey: "", sortDir: "" };  // one sorted column at a time
  try { Object.assign(state, JSON.parse(sessionStorage.getItem("cqa.filters") || "{}")); } catch { /* ignore */ }
  let rows = [];
  const checklists = await api.get("/api/checklists");

  el.innerHTML = `
    <div class="page-head">
      <div><h1>Диалоги</h1><div class="sub" data-count></div></div>
      <div class="row">
        ${getRole() === "admin" ? `<button class="btn ghost" data-admin>Данные…</button>` : ""}
        <button class="btn" data-load>⤓ Загрузить набор</button>
      </div>
    </div>
    <div class="card stack">
      <div class="row">
        <select data-f="group"><option value="">Все наборы</option></select>
        <select data-f="language"><option value="">Все языки</option><option>RU</option><option>KZ</option><option>EN</option></select>
        <select data-f="channel"><option value="">Все каналы</option><option value="agent chat">Чат</option><option value="voice call">Звонок</option></select>
        <input data-f="q" placeholder="Поиск по ID / оператору" style="width:200px">
        <span class="spacer"></span>
        <select data-cl>${checklists.map(c => `<option value="${esc(c.id)}">${esc(c.name)} · v${c.active_version}</option>`).join("")}</select>
        <button class="btn ghost" data-eval-sel disabled>Оценить выбранные</button>
        <button class="btn" data-eval-all>Оценить набор</button>
      </div>
      <div data-progress></div>
      <div class="small muted sel-hint">Выбор: флажок · <kbd>Shift</kbd>+клик — диапазон · зажмите и протяните мышью по строкам ·
        <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+клик — отметить строку · <kbd>Esc</kbd> — снять выбор</div>
      <div style="overflow:auto">
        <table class="tbl">
          <thead><tr><th><input type="checkbox" data-all aria-label="Выбрать все"></th>${COLS.map(([k, label, , cls]) =>
            `<th class="sortable ${cls || ""}" data-sort="${k}" aria-sort="none"><button type="button">${label}<span class="sort-ind" aria-hidden="true"></span></button></th>`).join("")}</tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>`;
  const tbody = el.querySelector("tbody");
  const selected = new Set();

  async function load() {
    rows = await api.get("/api/conversations");
    const groups = [...new Set(rows.map(r => r.group_id))];
    const gs = el.querySelector('[data-f="group"]');
    gs.innerHTML = `<option value="">Все наборы</option>` + groups.map(g => `<option>${esc(g)}</option>`).join("");
    for (const k of ["group", "language", "channel", "q"]) el.querySelector(`[data-f="${k}"]`).value = state[k];
    draw();
  }

  /** Click cycles ASC -> DESC -> none. Ties (and the unsorted view) are ordered by ID ascending,
   *  except when ID itself is the sorted column. */
  function sorted(list) {
    const col = COLS.find(c => c[0] === state.sortKey);
    if (!col || !state.sortDir) return list;
    const get = col[2], dir = state.sortDir === "desc" ? -1 : 1;
    return list.slice().sort((a, b) => {
      const va = get(a), vb = get(b);
      if (va == null || vb == null) {
        if (va == null && vb == null) return byId(a, b);
        return va == null ? 1 : -1;  // empty values last in both directions
      }
      const c = cmpVal(va, vb) * dir;
      return c || (col[0] === "id" ? 0 : byId(a, b));
    });
  }

  function drawSortHeads() {
    el.querySelectorAll("th[data-sort]").forEach(th => {
      const on = th.dataset.sort === state.sortKey && state.sortDir;
      th.setAttribute("aria-sort", on ? (state.sortDir === "asc" ? "ascending" : "descending") : "none");
      th.classList.toggle("sorted", !!on);
      th.querySelector(".sort-ind").textContent = on ? (state.sortDir === "asc" ? " ▲" : " ▼") : " ↕";
    });
  }

  function visible() {
    const q = state.q.toLowerCase();
    return sorted(rows.filter(r => (!state.group || r.group_id === state.group) && (!state.language || r.language === state.language)
      && (!state.channel || r.channel === state.channel)
      && (!q || r.id.toLowerCase().includes(q) || (r.operator_name || "").toLowerCase().includes(q))));
  }

  // "N диалогов · оценено M · средний балл X" for a set of rows (average over scored ones)
  const summary = list => {
    const ok = list.filter(r => r.evaluation && r.evaluation.status === "ok");
    const sc = ok.map(r => r.evaluation.final_score).filter(x => x != null);
    const avg = sc.length ? sc.reduce((a, b) => a + b, 0) / sc.length : null;
    return `${list.length} диалогов · оценено ${ok.length}` + (avg != null ? ` · средний балл ${fmtNum(avg)}` : "");
  };

  /** Selection-only repaint (no table rebuild; used while drag-selecting): checkboxes, row highlight, summary, buttons. */
  function syncSel() {
    const vis = visible();
    const sel = rows.filter(r => selected.has(r.id));
    el.querySelector("[data-count]").innerHTML = `<span>${summary(vis)}</span>`
      + (sel.length ? `<span class="sel-summary">Выбрано: ${summary(sel)} <button class="linkish" data-clear-sel>снять выбор</button></span>` : "");
    tbody.querySelectorAll("tr[data-id]").forEach(tr => {
      const on = selected.has(tr.dataset.id);
      tr.classList.toggle("picked", on);
      tr.setAttribute("aria-selected", String(on));
      tr.querySelector("[data-sel]").checked = on;
    });
    const all = el.querySelector("[data-all]"), n = vis.filter(r => selected.has(r.id)).length;
    all.checked = vis.length > 0 && n === vis.length;
    all.indeterminate = n > 0 && n < vis.length;
    el.querySelector("[data-eval-sel]").disabled = !selected.size;
    el.querySelector("[data-eval-sel]").textContent = selected.size ? `Оценить выбранные (${selected.size})` : "Оценить выбранные";
  }

  function draw() {
    drawSortHeads();
    const vis = visible();
    tbody.innerHTML = vis.map(r => {
      const e = r.evaluation;
      const st = e ? STATUS[e.status] : ["na", "Не оценён"];
      const changed = e && e.final_score !== e.original_score;
      return `<tr class="click" data-id="${esc(r.id)}">
        <td class="check"><input type="checkbox" data-sel="${esc(r.id)}" aria-label="Выбрать ${esc(r.id)}" ${selected.has(r.id) ? "checked" : ""}></td>
        <td><b>${esc(r.id)}</b></td>
        <td>${r.has_audio ? "🎧 " : ""}${esc(CHANNEL[r.channel] || r.channel)}</td>
        <td>${esc(r.language)}</td>
        <td>${esc(r.operator_name || "—")}</td>
        <td class="num">${r.turns}</td>
        <td class="num">${e && e.status === "ok" ? `<span class="chip ${scoreTone(e.final_score)}">${fmtNum(e.final_score)}</span>${changed ? ' <span class="small muted" title="Изменено апелляцией">*</span>' : ""}` : "—"}</td>
        <td>${e && e.critical_flag ? '<span class="chip bad">⚠ Да</span>' : e && e.status === "ok" ? '<span class="muted">Нет</span>' : ""}</td>
        <td><span class="chip ${st[0]}">${st[1]}</span></td>
      </tr>`;
    }).join("") || `<tr><td colspan="9" class="empty">Нет диалогов. Нажмите «Загрузить набор».</td></tr>`;
    syncSel();
  }

  el.addEventListener("input", e => {
    const f = e.target.dataset.f;
    if (f) {
      state[f] = e.target.value;
      try { sessionStorage.setItem("cqa.filters", JSON.stringify(state)); } catch { /* ignore */ }
      draw();
    }
  });
  // ---- selection: checkbox, Shift+click (range from the last clicked row), Ctrl/⌘+click (toggle a row),
  // press and drag across rows. Mouse only; touch and keyboard keep the plain checkbox.
  let anchor = null;          // last clicked row: start of a Shift range
  let drag = null;            // { start, on, base: Set, moved, x, y }
  let suppressClick = false;  // the click that ends a selection gesture must not open the card
  let lastWasTouch = false;
  const table = tbody.closest("table");
  const order = () => [...tbody.querySelectorAll("tr[data-id]")].map(tr => tr.dataset.id);
  /** Set rows between two ids (visible order, inclusive) to `on`, on top of `base`. */
  function applyRange(fromId, toId, on, base = new Set(selected)) {
    const ids = order();
    let a = ids.indexOf(fromId), b = ids.indexOf(toId);
    if (a < 0) a = b;
    if (a > b) [a, b] = [b, a];
    selected.clear();
    base.forEach(id => selected.add(id));
    ids.slice(a, b + 1).forEach(id => (on ? selected.add(id) : selected.delete(id)));
  }
  tbody.addEventListener("pointerdown", e => {
    suppressClick = false;
    lastWasTouch = e.pointerType === "touch";
    if (e.button !== 0 || lastWasTouch) return;
    const tr = e.target.closest("tr[data-id]");
    if (!tr) return;
    e.preventDefault();  // no text selection while gesturing
    const id = tr.dataset.id, inCheck = !!e.target.closest("td.check");
    if (e.shiftKey && anchor && order().includes(anchor)) {
      applyRange(anchor, id, !selected.has(id));
      suppressClick = true;
      return syncSel();
    }
    const base = new Set(selected), on = !selected.has(id);
    if (inCheck || e.metaKey || e.ctrlKey) {
      applyRange(id, id, on, base);
      anchor = id;
      suppressClick = true;
      syncSel();
    }
    // becomes a drag-select once the pointer itself moves onto another row
    drag = { start: id, on, base, moved: false, x: e.clientX, y: e.clientY };
  });
  // Tracked on the window with a hit-test, not "pointerover": after a press on a checkbox Chrome stops
  // sending pointerover to other rows, and the pointer may leave the table while dragging.
  const onDragMove = e => {
    if (!drag) return;
    const hit = document.elementFromPoint(e.clientX, e.clientY);
    const tr = hit && tbody.contains(hit) ? hit.closest("tr[data-id]") : null;
    if (!tr || (!drag.moved && tr.dataset.id === drag.start)) return;
    // Ignore "pointer over another row" caused by the table moving under a still pointer (e.g. the
    // "Выбрано: …" line appearing above it on the first selection): only a real mouse move starts a drag.
    if (!drag.moved && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 5) return;
    drag.moved = true;
    table.classList.add("dragging");
    applyRange(drag.start, tr.dataset.id, drag.on, drag.base);
    anchor = drag.start;
    syncSel();
  };
  const endDrag = () => {
    if (!drag) return;
    if (drag.moved) suppressClick = true;
    drag = null;
    table.classList.remove("dragging");
  };
  const onKey = e => {
    if (e.key !== "Escape" || !selected.size || document.querySelector(".modal-bg")) return;
    if (e.target.closest && e.target.closest("input, select, textarea")) return;
    selected.clear();
    syncSel();
  };
  addEventListener("pointermove", onDragMove);
  addEventListener("pointerup", endDrag);
  addEventListener("pointercancel", endDrag);
  addEventListener("keydown", onKey);
  el.addEventListener("click", e => {
    if (e.target.closest("[data-clear-sel]")) { selected.clear(); syncSel(); }
  });
  el.addEventListener("change", e => {
    if (e.target.dataset.sel) {  // keyboard (Space) and touch; mouse is handled on pointerdown
      e.target.checked ? selected.add(e.target.dataset.sel) : selected.delete(e.target.dataset.sel);
      anchor = e.target.dataset.sel;
      syncSel();
    }
    if (e.target.matches("[data-all]")) { visible().forEach(r => e.target.checked ? selected.add(r.id) : selected.delete(r.id)); syncSel(); }
  });
  el.querySelector("thead").addEventListener("click", e => {
    const th = e.target.closest("th[data-sort]");
    if (!th) return;
    const k = th.dataset.sort;
    // one column at a time: a new column starts at ASC; the same column cycles ASC -> DESC -> none
    if (state.sortKey !== k) { state.sortKey = k; state.sortDir = "asc"; }
    else if (state.sortDir === "asc") state.sortDir = "desc";
    else if (state.sortDir === "desc") { state.sortKey = ""; state.sortDir = ""; }
    else state.sortDir = "asc";
    try { sessionStorage.setItem("cqa.filters", JSON.stringify(state)); } catch { /* ignore */ }
    draw();
  });
  tbody.addEventListener("click", e => {
    // mouse clicks on the checkbox were applied on pointerdown: cancel the native toggle (keyboard: e.detail === 0)
    if (e.target.closest("td.check")) { if (e.detail !== 0 && e.target.matches("[data-sel]") && !lastWasTouch) e.preventDefault(); return; }
    if (suppressClick) { suppressClick = false; return; }
    const tr = e.target.closest("tr[data-id]");
    if (tr) location.hash = `#/c/${encodeURIComponent(tr.dataset.id)}`;
  });

  async function evaluate(body, btn) {
    btn.disabled = true;
    try {
      const p = await runBatch(el.querySelector("[data-progress]"), { ...body, checklist_id: el.querySelector("[data-cl]").value });
      toast(`Оценка завершена: ${p.ok || 0} успешно${p.error ? `, ошибок ${p.error}` : ""}${p.cost ? ". " + costLine(p.cost) : ""}`, !!p.error);
      selected.clear();
      await load();
    } catch (err) { toast(err.message, true); } finally { btn.disabled = false; }
  }
  el.querySelector("[data-eval-sel]").onclick = e => evaluate({ conversation_ids: [...selected] }, e.target);
  el.querySelector("[data-eval-all]").onclick = e => {
    const vis = visible();
    if (!vis.length) return toast("Нет диалогов для оценки", true);
    evaluate(state.group ? { group_id: state.group } : { conversation_ids: vis.map(r => r.id) }, e.target);
  };
  el.querySelector("[data-admin]")?.addEventListener("click", () => openDataAdmin(async () => {
    state.group = "";
    try { sessionStorage.setItem("cqa.filters", JSON.stringify(state)); } catch { /* ignore */ }
    selected.clear();
    dispatchEvent(new Event("cqa:appeals"));
    await load();
  }));
  el.querySelector("[data-load]").onclick = () => openLoader(async r => {
    toast(`Набор ${r.group_id}: ${r.count} диалогов (новых ${r.new}, обновлено ${r.updated})`);
    state.group = r.group_id;
    try { sessionStorage.setItem("cqa.filters", JSON.stringify(state)); } catch { /* ignore */ }
    await load();
  });

  await load();
  return { unmount() { removeEventListener("pointermove", onDragMove); removeEventListener("pointerup", endDrag); removeEventListener("pointercancel", endDrag); removeEventListener("keydown", onKey); } };
}

/** Dataset loader: by group_id (server's ORG_API_URL), by full GET link, or by JSON file. */
function openLoader(onLoaded) {
  modal(`
    <h2>Загрузить набор диалогов</h2>
    <div class="seg" data-tabs>
      <button data-t="gid" class="on">По group_id</button><button data-t="url">По ссылке</button><button data-t="file">Файл JSON</button>
    </div>
    <div data-pane="gid" class="stack" style="gap:8px">
      <label class="f">group_id<input data-gid placeholder="например, DEV" autocomplete="off"></label>
      <p class="small muted">Запрос к API организаторов через сервер (адрес API задан в настройках сервера).</p>
    </div>
    <div data-pane="url" class="stack" style="gap:8px" hidden>
      <label class="f">Полная ссылка GET (вместе с group_id)<textarea rows="3" data-url placeholder="https://…powerplatform.com/…&group_id=…"></textarea></label>
      <label class="f">group_id (необязательно — иначе берётся из ответа или ссылки)<input data-url-gid autocomplete="off"></label>
      <p class="small muted">Принимаются только https-ссылки на домен API организаторов.</p>
    </div>
    <div data-pane="file" class="stack" style="gap:8px" hidden>
      <label class="f">Файл JSON — ответ API, {records:[…]} или массив записей<input type="file" accept=".json,application/json" data-file></label>
      <label class="f">group_id (необязательно)<input data-file-gid autocomplete="off"></label>
    </div>
    <div class="small" data-err style="color:var(--bad)"></div>
    <div class="row"><span class="spacer"></span><button class="btn ghost" data-close>Отмена</button><button class="btn" data-go>Загрузить</button></div>`,
  (m, close) => {
    let tab = "gid";
    const $ = s => m.querySelector(s);
    const show = t => {
      tab = t;
      m.querySelectorAll("[data-t]").forEach(b => b.classList.toggle("on", b.dataset.t === t));
      m.querySelectorAll("[data-pane]").forEach(p => { p.hidden = p.dataset.pane !== t; });
      $("[data-err]").textContent = "";
    };
    $("[data-tabs]").addEventListener("click", e => { const b = e.target.closest("[data-t]"); if (b) show(b.dataset.t); });
    $("[data-gid]").focus();
    m.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.tagName === "INPUT" && e.target.type !== "file") $("[data-go]").click(); });

    $("[data-go]").onclick = async () => {
      const err = $("[data-err]"), go = $("[data-go]");
      err.textContent = "";
      let req;
      if (tab === "gid") {
        const gid = $("[data-gid]").value.trim();
        if (!gid) { err.textContent = "Введите group_id"; return $("[data-gid]").focus(); }
        req = () => api.post(`/api/ingest?group_id=${encodeURIComponent(gid)}`);
      } else if (tab === "url") {
        const url = $("[data-url]").value.trim(), gid = $("[data-url-gid]").value.trim();
        if (!/^https:\/\//i.test(url)) { err.textContent = "Вставьте полную https-ссылку"; return $("[data-url]").focus(); }
        req = () => api.post("/api/ingest/url", { url, group_id: gid || null });
      } else {
        const f = $("[data-file]").files[0], gid = $("[data-file-gid]").value.trim();
        if (!f) { err.textContent = "Выберите файл"; return; }
        const fd = new FormData();
        fd.append("file", f);
        req = () => api.post(`/api/conversations/upload${gid ? `?group_id=${encodeURIComponent(gid)}` : ""}`, fd);
      }
      go.disabled = true;
      go.textContent = "Загрузка…";
      try {
        const r = await req();
        close();
        await onLoaded(r);
      } catch (e) {
        err.textContent = e.message;
      } finally {
        go.disabled = false;
        go.textContent = "Загрузить";
      }
    };
  });
}

/** Admin: clear all conversations/evaluations/appeals (optionally checklists) or re-load the demo set. */
async function openDataAdmin(onChanged) {
  const c = await api.get("/api/admin/counts");
  modal(`
    <h2>Управление данными</h2>
    <p>Сейчас в базе: <b>${c.conversations}</b> диалогов, <b>${c.evaluations}</b> оценок, <b>${c.appeals}</b> апелляций,
      <b>${c.checklist_versions}</b> версий чек-листов.</p>
    <div class="card stack" style="gap:8px;border-color:#efc4bb">
      <h3 style="margin:0;color:var(--bad)">Очистить данные</h3>
      <p class="small" style="margin:0">Удаляет все диалоги, оценки и апелляции — чтобы загрузить набор и оценить его с нуля.
        Данные не вернутся сами после перезапуска сервера.</p>
      <label class="row small"><input type="checkbox" data-cl> Также сбросить чек-листы к исходной версии v1</label>
      <label class="row small"><input type="checkbox" data-ok> Я понимаю, что это действие нельзя отменить</label>
      <div class="row"><span class="spacer"></span><button class="btn danger" data-reset disabled>Очистить</button></div>
    </div>
    <div class="card stack" style="gap:8px">
      <h3 style="margin:0">Демо-набор</h3>
      <p class="small" style="margin:0">Загрузить DEV (65 диалогов) и сохранённые в репозитории оценки для неоценённых диалогов.</p>
      <div class="row"><span class="spacer"></span><button class="btn ghost" data-demo>Загрузить демо-набор</button></div>
    </div>
    <div class="small" data-err style="color:var(--bad)"></div>
    <div class="row"><span class="spacer"></span><button class="btn ghost" data-close>Закрыть</button></div>`,
  (m, close) => {
    const $ = s => m.querySelector(s);
    $("[data-ok]").onchange = e => { $("[data-reset]").disabled = !e.target.checked; };
    const run = async (btn, fn, msg) => {
      btn.disabled = true;
      try {
        const r = await fn();
        close();
        toast(msg(r));
        await onChanged();
      } catch (e) { $("[data-err]").textContent = e.message; btn.disabled = false; }
    };
    $("[data-reset]").onclick = e => run(e.target,
      () => api.post("/api/admin/reset", { confirm: "DELETE", reset_checklists: $("[data-cl]").checked }),
      r => `Удалено: ${r.deleted.conversations} диалогов, ${r.deleted.evaluations} оценок, ${r.deleted.appeals} апелляций`);
    $("[data-demo]").onclick = e => run(e.target, () => api.post("/api/admin/seed-demo"),
      r => `Загружено: ${r.loaded.conversations} диалогов, ${r.loaded.evaluations} оценок`);
  });
}
