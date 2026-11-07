import { api } from "../api.js";
import { CHANNEL, esc, fmtNum, runBatch, scoreTone, toast } from "../ui.js";

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
        <input data-gid placeholder="group_id (напр. DEV)" style="width:170px">
        <button class="btn ghost" data-ingest>Загрузить из API</button>
        <label class="btn ghost" style="margin:0">Файл JSON<input type="file" accept=".json" data-file hidden></label>
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
    }).join("") || `<tr><td colspan="9" class="empty">Нет диалогов. Загрузите набор по group_id.</td></tr>`;
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
      toast(`Оценка завершена: ${p.ok || 0} успешно${p.error ? `, ошибок ${p.error}` : ""}`, !!p.error);
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
  el.querySelector("[data-ingest]").onclick = async e => {
    const gid = el.querySelector("[data-gid]").value.trim();
    if (!gid) return toast("Укажите group_id", true);
    e.target.disabled = true;
    try {
      const r = await api.post(`/api/ingest?group_id=${encodeURIComponent(gid)}`);
      toast(`Загружено ${r.count} диалогов (${gid})`);
      state.group = gid;
      await load();
    } catch (err) { toast(err.message, true); } finally { e.target.disabled = false; }
  };
  el.querySelector("[data-file]").onchange = async e => {
    const fd = new FormData();
    fd.append("file", e.target.files[0]);
    try {
      const r = await api.post("/api/conversations/upload", fd);
      toast(`Загружено ${r.count} диалогов`);
      await load();
    } catch (err) { toast(err.message, true); }
    e.target.value = "";
  };

  await load();
}
