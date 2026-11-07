import { api, getRole } from "../api.js";
import { attachTips, esc, fmtNum, scoreTone } from "../ui.js";

export async function mount(el) {
  const isAdmin = getRole() !== "operator";
  let period = "week", operator = null;
  const overview = await api.get("/api/stats/overview");
  const operators = overview.operators.map(o => o.operator);
  operator = operators[0];
  const checklist = await api.get("/api/checklists/chat-quality").catch(() => null);
  const titles = Object.fromEntries((checklist?.version.criteria || []).map(c => [c.id, c.title]));

  el.innerHTML = `
    <div class="page-head"><div><h1>Аналитика</h1><div class="sub">${isAdmin ? "Качество по всем операторам" : "Моя статистика"}</div></div>
      <div class="row">
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
    const d = operator ? await api.get(`/api/stats/operators/${encodeURIComponent(operator)}?period=${period}`)
      : await api.get(`/api/stats/overview?period=${period}`);
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
        </div>`}`;
  }

  el.querySelector("[data-period]").addEventListener("click", e => { const b = e.target.closest("[data-p]"); if (b) { period = b.dataset.p; draw(); } });
  el.querySelector("[data-op]").onchange = e => { operator = e.target.value; draw(); };
  body.addEventListener("click", e => {
    const o = e.target.closest("[data-o]");
    if (o) { operator = o.dataset.o; el.querySelector("[data-op]").value = operator; draw(); }
    const c = e.target.closest("[data-c]");
    if (c) location.hash = `#/c/${encodeURIComponent(c.dataset.c)}`;
  });
  await draw();
}
