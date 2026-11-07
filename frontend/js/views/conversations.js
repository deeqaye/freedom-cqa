import { api, getRole } from "../api.js";
import { CHANNEL, esc, fmtNum, modal, costLine, runBatch, scoreTone, toast } from "../ui.js";

const STATUS = { ok: ["good", "Оценён"], error: ["bad", "Ошибка"], queued: ["info", "В очереди"], running: ["info", "Оценивается"] };

export async function mount(el) {
  const state = { group: "", language: "", channel: "", q: "" };
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
      <div style="overflow:auto">
        <table class="tbl">
          <thead><tr><th><input type="checkbox" data-all aria-label="Выбрать все"></th><th>ID</th><th>Канал</th><th>Язык</th><th>Оператор</th>
            <th class="num">Реплик</th><th class="num">Итог</th><th>Грубая ошибка</th><th>Статус</th></tr></thead>
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

  function visible() {
    const q = state.q.toLowerCase();
    return rows.filter(r => (!state.group || r.group_id === state.group) && (!state.language || r.language === state.language)
      && (!state.channel || r.channel === state.channel)
      && (!q || r.id.toLowerCase().includes(q) || (r.operator_name || "").toLowerCase().includes(q)));
  }

  function draw() {
    const vis = visible();
    const evaluated = vis.filter(r => r.evaluation && r.evaluation.status === "ok");
    const avg = evaluated.length ? evaluated.reduce((s, r) => s + (r.evaluation.final_score || 0), 0) / evaluated.length : null;
    el.querySelector("[data-count]").textContent = `${vis.length} диалогов · оценено ${evaluated.length}` + (avg != null ? ` · средний балл ${fmtNum(avg)}` : "");
    tbody.innerHTML = vis.map(r => {
      const e = r.evaluation;
      const st = e ? STATUS[e.status] : ["na", "Не оценён"];
      const changed = e && e.final_score !== e.original_score;
      return `<tr class="click" data-id="${esc(r.id)}">
        <td onclick="event.stopPropagation()"><input type="checkbox" data-sel="${esc(r.id)}" ${selected.has(r.id) ? "checked" : ""}></td>
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
    el.querySelector("[data-eval-sel]").disabled = !selected.size;
    el.querySelector("[data-eval-sel]").textContent = selected.size ? `Оценить выбранные (${selected.size})` : "Оценить выбранные";
  }

  el.addEventListener("input", e => {
    const f = e.target.dataset.f;
    if (f) {
      state[f] = e.target.value;
      try { sessionStorage.setItem("cqa.filters", JSON.stringify(state)); } catch { /* ignore */ }
      draw();
    }
  });
  el.addEventListener("change", e => {
    if (e.target.dataset.sel) { e.target.checked ? selected.add(e.target.dataset.sel) : selected.delete(e.target.dataset.sel); draw(); }
    if (e.target.matches("[data-all]")) { visible().forEach(r => e.target.checked ? selected.add(r.id) : selected.delete(r.id)); draw(); }
  });
  tbody.addEventListener("click", e => {
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
