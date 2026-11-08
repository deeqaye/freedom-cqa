import { api, getRole } from "../api.js";
import { esc, fmtNum, costLine, runBatch, toast } from "../ui.js";

const TYPES = { binary: "Да / Нет", scale: "Шкала", flag: "Флаг (без баллов)" };
const blank = () => ({ id: "", section: "", title: "", type: "binary", weight: 10, na_allowed: false, description: "", na_condition: "", prompt_hint: "", _new: true });

export async function mount(el) {
  const list = await api.get("/api/checklists");
  let clId = list[0]?.id, data = null, crit = [], dirty = false;
  const canEdit = ["admin", "lead"].includes(getRole());

  el.innerHTML = `
    <div class="page-head"><div><h1>Чек-листы</h1><div class="sub" data-sub></div></div>
      <div class="row"><select data-cl>${list.map(c => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("")}</select>
        <select data-ver aria-label="Версия"></select></div></div>
    ${canEdit ? "" : `<div class="alert info mb-2">Роль «Оператор» — только просмотр. Редактирование доступно администратору и главному специалисту.</div>`}
    <div class="stack">
      <div class="card row" data-bar>
        <span class="weights" data-w></span><span class="spacer"></span>
        ${canEdit ? `<button class="btn ghost" data-add>+ Критерий</button><input data-note placeholder="Комментарий к версии" class="w-220"><button class="btn" data-save>Сохранить новую версию</button>` : ""}
      </div>
      <div class="stack" data-crits></div>
      <div class="card stack">
        <h2 class="m-0">Применить чек-лист к диалогам</h2>
        <div class="row"><span>Набор</span><select data-group></select>
          <span class="muted small" data-apply-ver></span><span class="spacer"></span>
          <button class="btn" data-apply>Запустить оценку</button></div>
        <div data-progress></div>
      </div>
    </div>`;

  const critsEl = el.querySelector("[data-crits]");

  async function load(version) {
    data = await api.get(`/api/checklists/${clId}${version ? `?version=${version}` : ""}`);
    crit = structuredClone(data.version.criteria);
    dirty = false;
    const vers = await api.get(`/api/checklists/${clId}/versions`);
    el.querySelector("[data-ver]").innerHTML = vers.slice().reverse().map(v =>
      `<option value="${v.version}" ${v.version === data.version.version ? "selected" : ""}>v${v.version}${v.active ? " · активна" : ""} — ${esc(v.note || v.created_by)}</option>`).join("");
    el.querySelector("[data-sub]").textContent = `Версия ${data.version.version}${data.version.active ? " (активна)" : ""} · ${crit.length} критериев · изменения сохраняются как новая версия, старые оценки ссылаются на свою версию`;
    el.querySelector("[data-apply-ver]").textContent = `будет использована активная версия v${data.active_version}`;
    draw();
  }

  function weights() {
    const w = crit.filter(c => c.type !== "flag").reduce((s, c) => s + (+c.weight || 0), 0);
    el.querySelector("[data-w]").innerHTML = `Сумма весов: <b>${fmtNum(w)}</b> ${w === 100 ? '<span class="chip good">= 100</span>' : '<span class="chip warn">итог всё равно нормируется к 100</span>'}${dirty ? ' · <span class="chip warn">есть несохранённые изменения</span>' : ""}`;
  }

  function draw() {
    const dis = canEdit ? "" : "disabled";
    critsEl.innerHTML = crit.map((c, i) => `
      <div class="cl-crit ${c._new ? "new" : ""}" data-i="${i}">
        <label class="f">ID (код)<input data-k="id" value="${esc(c.id)}" ${dis} ${c._new ? "" : 'title="Код используется в results.json"'}></label>
        <label class="f wide">Название<input data-k="title" value="${esc(c.title)}" ${dis}></label>
        <label class="f span2">Секция<input data-k="section" value="${esc(c.section)}" list="sections" ${dis}></label>
        <label class="f">Тип ответа<select data-k="type" ${dis}>${Object.entries(TYPES).map(([k, v]) => `<option value="${k}" ${c.type === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        <label class="f">Вес<input type="number" min="0" step="1" data-k="weight" value="${c.type === "flag" ? 0 : c.weight}" ${c.type === "flag" ? "disabled" : dis}></label>
        <label class="f span2" ${c.type === "scale" ? "" : "hidden"}>Ступени шкалы (через запятую)<input data-k="steps" value="${esc((c.steps || []).join(", "))}" ${dis}></label>
        <label class="f span2 inline"><input type="checkbox" data-k="na_allowed" ${c.na_allowed ? "checked" : ""} ${dis}> Допускается N/A</label>
        <label class="f full">Описание — когда ставить «Да» / как оценивать<textarea rows="2" data-k="description" ${dis}>${esc(c.description)}</textarea></label>
        <label class="f wide" ${c.na_allowed ? "" : "hidden"}>Условие N/A<textarea rows="2" data-k="na_condition" ${dis}>${esc(c.na_condition || "")}</textarea></label>
        <label class="f ${c.na_allowed ? "wide" : "full"}">Подсказка для модели (мини-промпт)<textarea rows="2" data-k="prompt_hint" ${dis}>${esc(c.prompt_hint || "")}</textarea></label>
        ${c.type === "scale" ? `<label class="f full">Описание ступеней (по строке: «ступень: текст»)<textarea rows="3" data-k="step_labels" ${dis}>${esc(Object.entries(c.step_labels || {}).sort((a, b) => b[0] - a[0]).map(([k, v]) => `${k}: ${v}`).join("\n"))}</textarea></label>` : ""}
        ${canEdit ? `<div class="tools"><button class="btn ghost sm" data-up ${i ? "" : "disabled"}>↑</button><button class="btn ghost sm" data-down ${i < crit.length - 1 ? "" : "disabled"}>↓</button><button class="btn danger sm" data-del>Удалить</button></div>` : ""}
      </div>`).join("") + `<datalist id="sections">${[...new Set(crit.map(c => c.section).filter(Boolean))].map(s => `<option value="${esc(s)}">`).join("")}</datalist>`;
    weights();
  }

  critsEl.addEventListener("input", e => {
    const k = e.target.dataset.k, box = e.target.closest("[data-i]");
    if (!k || !box) return;
    const c = crit[+box.dataset.i];
    if (k === "na_allowed") c.na_allowed = e.target.checked;
    else if (k === "weight") c.weight = +e.target.value;
    else if (k === "steps") c.steps = e.target.value.split(/[,\s]+/).filter(Boolean).map(Number);
    else if (k === "step_labels") c.step_labels = Object.fromEntries(e.target.value.split("\n").map(l => l.match(/^\s*(\d+)\s*:\s*(.+)$/)).filter(Boolean).map(m => [m[1], m[2]]));
    else c[k] = e.target.value;
    dirty = true;
    if (k === "type") {
      if (c.type === "scale" && !c.steps) c.steps = [0, 5, 10];
      if (c.type === "flag") { c.weight = 0; c.na_allowed = false; }
    }
    if (k === "type" || k === "na_allowed") draw(); else weights();
  });
  critsEl.addEventListener("click", e => {
    const box = e.target.closest("[data-i]");
    if (!box) return;
    const i = +box.dataset.i;
    if (e.target.matches("[data-del]")) { if (confirm(`Удалить критерий «${crit[i].title || crit[i].id}»?`)) { crit.splice(i, 1); dirty = true; draw(); } }
    if (e.target.matches("[data-up]")) { [crit[i - 1], crit[i]] = [crit[i], crit[i - 1]]; dirty = true; draw(); }
    if (e.target.matches("[data-down]")) { [crit[i + 1], crit[i]] = [crit[i], crit[i + 1]]; dirty = true; draw(); }
  });
  el.querySelector("[data-add]")?.addEventListener("click", () => {
    crit.push(blank()); dirty = true; draw();
    critsEl.lastElementChild.previousElementSibling?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
  el.querySelector("[data-save]")?.addEventListener("click", async e => {
    const criteria = crit.map(({ _new, ...c }) => {
      const out = { ...c, weight: c.type === "flag" ? 0 : +c.weight };
      if (out.type !== "scale") { delete out.steps; delete out.step_labels; }
      if (!out.na_allowed) out.na_condition = null;
      return out;
    });
    e.target.disabled = true;
    try {
      const v = await api.put(`/api/checklists/${clId}`, { criteria, note: el.querySelector("[data-note]").value.trim() || null });
      toast(`Сохранено как версия v${v.version} и активировано`);
      el.querySelector("[data-note]").value = "";
      await load();
    } catch (err) { toast(err.message, true); } finally { e.target.disabled = false; }
  });
  el.querySelector("[data-cl]").onchange = e => { clId = e.target.value; load(); };
  el.querySelector("[data-ver]").onchange = e => {
    if (dirty && !confirm("Несохранённые изменения будут потеряны. Продолжить?")) return;
    load(+e.target.value);
  };

  const convs = await api.get("/api/conversations");
  const groups = [...new Set(convs.map(c => c.group_id))];
  el.querySelector("[data-group]").innerHTML = groups.map(g => `<option>${esc(g)}</option>`).join("");
  el.querySelector("[data-apply]").onclick = async e => {
    if (dirty) return toast("Сначала сохраните изменения", true);
    e.target.disabled = true;
    try {
      const p = await runBatch(el.querySelector("[data-progress]"), { group_id: el.querySelector("[data-group]").value, checklist_id: clId });
      toast(`Готово: ${p.ok || 0} оценено${p.error ? `, ошибок ${p.error}` : ""}${p.cost ? ". " + costLine(p.cost) : ""}`, !!p.error);
    } catch (err) { toast(err.message, true); } finally { e.target.disabled = false; }
  };

  const beforeUnload = e => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
  addEventListener("beforeunload", beforeUnload);
  await load();
  return { unmount() { removeEventListener("beforeunload", beforeUnload); } };
}
