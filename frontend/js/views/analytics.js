import { api, getRole } from "../api.js";
import { attachTips, esc, fmtDur, fmtNum, fmtUsd, scoreTone } from "../ui.js";

export async function mount(el) {
  const isAdmin = getRole() !== "operator";
  let period = "week", operator = null;
  const lists = await api.get("/api/checklists").catch(() => []);
  let clId = lists[0]?.id || "";
  const overview = await api.get("/api/stats/overview");
  const operators = overview.operators.map(o => o.operator);
  operator = operators[0];
  let titles = {};
  async function loadTitles() {
    const cl = clId ? await api.get(`/api/checklists/${encodeURIComponent(clId)}`).catch(() => null) : null;
    titles = Object.fromEntries((cl?.version.criteria || []).map(c => [c.id, c.title]));
  }

  el.innerHTML = `
    <div class="page-head"><div><h1>Аналитика</h1><div class="sub">${isAdmin ? "Качество по всем операторам" : "Моя статистика"}</div></div>
      <div class="row">
        ${lists.length > 1 ? `<select data-cl aria-label="Чек-лист">${lists.map(c => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("")}</select>` : ""}
        <select data-op ${isAdmin ? "" : ""}>${isAdmin ? `<option value="">Все операторы</option>` : ""}${operators.map(o => `<option ${!isAdmin && o === operator ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>
        <div class="seg" data-period><button data-p="week" class="on">По неделям</button><button data-p="month">По месяцам</button></div>
      </div></div>
    <div class="stack" data-body></div>`;
  if (isAdmin) operator = "";
  const body = el.querySelector("[data-body]");
  attachTips(body);

  function seriesChart(series) {
    if (!series.length) return `<div class="empty">Нет данных</div>`;
    const W = 640, H = 200, pad = 28, bw = Math.min(56, (W - pad) / series.length - 12);
    const x = i => pad + 6 + i * ((W - pad) / series.length);
    const y = v => H - 22 - (v / 100) * (H - 40);
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Средний балл по периодам">
      ${[0, 50, 100].map(v => `<line x1="${pad}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="#e3e8e4"/><text x="0" y="${y(v) + 4}" font-size="11" fill="#8a978e">${v}</text>`).join("")}
      ${series.map((s, i) => `<g data-tip="<b>${esc(s.period)}</b><br>Средний балл: ${fmtNum(s.avg_score)}<br>Диалогов: ${s.count}">
        <rect x="${x(i) - 4}" y="0" width="${bw + 8}" height="${H}" fill="transparent"/>
        <path d="M${x(i)},${y(0)} V${y(s.avg_score || 0) + 4} q0,-4 4,-4 h${bw - 8} q4,0 4,4 V${y(0)} Z" fill="#1f7a3a"/>
        <text x="${x(i) + bw / 2}" y="${y(s.avg_score || 0) - 6}" text-anchor="middle" font-size="12" fill="#17231b">${fmtNum(s.avg_score, 1)}</text>
        <text x="${x(i) + bw / 2}" y="${H - 6}" text-anchor="middle" font-size="11" fill="#4c5c51">${esc(s.period)}</text></g>`).join("")}
    </svg>`;
  }

  function critBars(criteria) {
    const rows = Object.entries(criteria).filter(([, v]) => v.avg_pct != null || v.na);
    if (!rows.length) return `<div class="empty">Нет данных</div>`;
    return `<div class="bars">${rows.map(([k, v]) => `
      <div class="bar-row" data-tip="<b>${esc(titles[k] || k)}</b><br>Выполнение: ${v.avg_pct == null ? "—" : fmtNum(v.avg_pct, 1) + "%"}<br>Применим: ${v.applicable} · N/A: ${v.na}">
        <span>${esc(titles[k] || k)}</span>
        <div class="track"><div class="fill" style="width:${v.avg_pct || 0}%"></div></div>
        <span class="num">${v.avg_pct == null ? "N/A" : fmtNum(v.avg_pct, 0) + "%"}</span></div>`).join("")}</div>`;
  }

  async function draw() {
    el.querySelectorAll("[data-p]").forEach(b => b.classList.toggle("on", b.dataset.p === period));
    const q = `period=${period}${clId ? `&checklist_id=${encodeURIComponent(clId)}` : ""}`;
    const d = operator ? await api.get(`/api/stats/operators/${encodeURIComponent(operator)}?${q}`)
      : await api.get(`/api/stats/overview?${q}`);
    const tiles = [["Средний балл", fmtNum(d.avg_score)], ["Оценено диалогов", d.count], ["С грубыми ошибками", d.critical_count]];
    if (!operator) tiles.push(["Открытых апелляций", d.appeals.open]);
    else tiles.push(["Лучший / худший", d.conversations.length ? `${fmtNum(Math.max(...d.conversations.map(c => c.final_score ?? 0)), 0)} / ${fmtNum(Math.min(...d.conversations.map(c => c.final_score ?? 100)), 0)}` : "—"]);
    body.innerHTML = `
      <div class="tiles">${tiles.map(([k, v]) => `<div class="card tile"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("")}</div>
      <div class="grid2">
        <div class="card"><h2>Средний балл ${period === "week" ? "по неделям" : "по месяцам"}</h2>${seriesChart(d.series)}
          <p class="small muted">Для чатов без даты в данных используется дата загрузки.</p></div>
        <div class="card"><h2>Выполнение критериев</h2>${critBars(d.criteria)}</div>
      </div>
      ${operator ? `<div class="card"><h2>Диалоги оператора</h2><table class="tbl"><thead><tr><th>ID</th><th>Язык</th><th class="num">Балл</th><th>Грубая ошибка</th></tr></thead><tbody>
          ${d.conversations.map(c => `<tr class="click" data-c="${esc(c.id)}"><td>${esc(c.id)}</td><td>${esc(c.language)}</td>
            <td class="num"><span class="chip ${scoreTone(c.final_score)}">${fmtNum(c.final_score)}</span></td><td>${c.critical_flag ? '<span class="chip bad">⚠ Да</span>' : "Нет"}</td></tr>`).join("")}
        </tbody></table></div>`
        : `<div class="grid2">
          <div class="card"><h2>Операторы</h2><table class="tbl"><thead><tr><th>Оператор</th><th class="num">Диалогов</th><th class="num">Средний балл</th><th class="num">Грубые</th></tr></thead><tbody>
            ${d.operators.map(o => `<tr class="click" data-o="${esc(o.operator)}"><td>${esc(o.operator)}</td><td class="num">${o.count}</td>
              <td class="num"><span class="chip ${scoreTone(o.avg_score)}">${fmtNum(o.avg_score)}</span></td><td class="num">${o.critical_count}</td></tr>`).join("")}
          </tbody></table></div>
          <div class="card"><h2>По языкам</h2><table class="tbl"><thead><tr><th>Язык</th><th class="num">Средний балл</th></tr></thead><tbody>
            ${Object.entries(d.by_language).map(([l, v]) => `<tr><td>${esc(l)}</td><td class="num">${fmtNum(v)}</td></tr>`).join("")}</tbody></table>
            <h3 style="margin-top:14px">Апелляции</h3><p>Открыто: <b>${d.appeals.open}</b> · принято: <b>${d.appeals.accepted}</b> · отклонено: <b>${d.appeals.rejected}</b></p></div>
        </div>`}
      ${!operator && isAdmin ? compareCard(await api.get("/api/stats/compare").catch(() => null)) : ""}
      ${!operator && isAdmin ? costCard(await api.get("/api/stats/cost").catch(() => null)) : ""}`;
  }

  /** The same conversations scored under each checklist version. */
  function compareCard(d) {
    if (!d || d.columns.length < 2) return `<div class="card"><h2>Сравнение чек-листов</h2><div class="empty">Оцените один набор по двум чек-листам
      (переключатель на странице «Чек-листы» или в карточке диалога), чтобы сравнить результаты.</div></div>`;
    const cols = d.columns, shared = d.rows.filter(r => Object.keys(r.critical).length === cols.length);
    const head = cols.map(c => `<th class="num">${esc(c.checklist_name)} <span class="muted">v${c.version}</span></th>`).join("");
    const delta = r => { const v = cols.map(c => r.scores[c.version_id]); return v.every(x => x != null) ? Math.max(...v) - Math.min(...v) : -1; };
    const top = shared.slice().sort((a, b) => delta(b) - delta(a)).slice(0, 10);
    return `<div class="card"><h2>Сравнение чек-листов</h2>
      <table class="tbl"><thead><tr><th></th>${head}</tr></thead><tbody>
        <tr><td>Оценено диалогов</td>${cols.map(c => `<td class="num">${c.count}</td>`).join("")}</tr>
        <tr><td>Средний балл (все оценённые)</td>${cols.map(c => `<td class="num">${fmtNum(c.avg_score)}</td>`).join("")}</tr>
        <tr><td>Средний балл (общие ${d.shared_count})</td>${cols.map(c => `<td class="num"><b>${fmtNum(d.shared_avg[c.version_id])}</b></td>`).join("")}</tr>
        <tr><td>С грубыми ошибками</td>${cols.map(c => `<td class="num">${c.critical_count}</td>`).join("")}</tr>
      </tbody></table>
      ${top.length ? `<h3 style="margin-top:14px">Наибольшее расхождение</h3>
        <table class="tbl"><thead><tr><th>Диалог</th>${head}<th class="num">Разница</th></tr></thead><tbody>
        ${top.map(r => `<tr class="click" data-c="${esc(r.conversation_id)}"><td>${esc(r.conversation_id)}</td>
          ${cols.map(c => `<td class="num"><span class="chip ${scoreTone(r.scores[c.version_id])}">${fmtNum(r.scores[c.version_id])}</span></td>`).join("")}
          <td class="num">${fmtNum(delta(r))}</td></tr>`).join("")}</tbody></table>` : ""}
      <p class="small muted">«Общие» — диалоги, оценённые по всем столбцам; сравнивать средние стоит по ним.</p></div>`;
  }

  function costCard(c) {
    if (!c || !c.evaluations) return `<div class="card"><h2>Стоимость обработки</h2><div class="empty">Нет запусков оценщика (импортированные результаты не измерялись)</div></div>`;
    const CH = { "agent chat": "Чаты", "voice call": "Звонки" };
    const t = [["Время на диалог (сред. / p95)", `${fmtDur(c.time.avg_s)} / ${fmtDur(c.time.p95_s)}`],
      ["Токенов на диалог (вход → выход)", c.tokens.avg_input == null ? "—" : `${c.tokens.avg_input.toLocaleString("ru")} → ${c.tokens.avg_output.toLocaleString("ru")}`],
      ["Стоимость на диалог", fmtUsd(c.cost.avg_per_evaluation_usd)],
      ["На 1000 диалогов", fmtUsd(c.cost.per_1000_usd)]];
    return `<div class="card"><h2>Стоимость обработки</h2>
      <div class="tiles">${t.map(([k, v]) => `<div class="tile"><div class="k">${k}</div><div class="v" style="font-size:22px">${v}</div></div>`).join("")}</div>
      <p class="small muted">Последняя оценка каждого диалога: ${c.evaluations} (ошибок ${c.errors}). Всего ${c.tokens.total.toLocaleString("ru")} токенов,
        ${fmtUsd(c.cost.total_usd)}${c.cost.usd_per_1m_tokens != null ? ` (${fmtUsd(c.cost.usd_per_1m_tokens)} за 1M токенов)` : ""}.
        ${c.cost.unpriced ? `Без стоимости: ${c.cost.unpriced} — оценщик не вернул usage, модели нет в тарифах.` : ""}</p>
      <div class="grid2">
        <table class="tbl"><thead><tr><th>Канал</th><th class="num">Диалогов</th><th class="num">Время</th><th class="num">Токенов</th><th class="num">$ / диалог</th></tr></thead><tbody>
          ${Object.entries(c.by_channel).map(([k, v]) => `<tr><td>${esc(CH[k] || k)}</td><td class="num">${v.count}</td><td class="num">${fmtDur(v.avg_s)}</td>
            <td class="num">${v.avg_tokens == null ? "—" : v.avg_tokens.toLocaleString("ru")}</td><td class="num">${fmtUsd(v.avg_cost_usd)}</td></tr>`).join("")}</tbody></table>
        <table class="tbl"><thead><tr><th>Модель</th><th class="num">Оценок</th><th class="num">Тариф вход / выход, $ за 1M</th><th class="num">Итого</th></tr></thead><tbody>
          ${c.by_model.map(m => `<tr><td>${esc(m.model)}</td><td class="num">${m.count}</td>
            <td class="num">${m.price_per_1m ? `${m.price_per_1m.input} / ${m.price_per_1m.output}` : "—"}</td><td class="num">${fmtUsd(m.cost_usd)}</td></tr>`).join("")}</tbody></table>
      </div></div>`;
  }

  el.querySelector("[data-period]").addEventListener("click", e => { const b = e.target.closest("[data-p]"); if (b) { period = b.dataset.p; draw(); } });
  const clSel = el.querySelector("[data-cl]");
  if (clSel) clSel.onchange = async () => { clId = clSel.value; await loadTitles(); draw(); };
  el.querySelector("[data-op]").onchange = e => { operator = e.target.value; draw(); };
  body.addEventListener("click", e => {
    const o = e.target.closest("[data-o]");
    if (o) { operator = o.dataset.o; el.querySelector("[data-op]").value = operator; draw(); }
    const c = e.target.closest("[data-c]");
    if (c) location.hash = `#/c/${encodeURIComponent(c.dataset.c)}`;
  });
  await loadTitles();
  await draw();
}
