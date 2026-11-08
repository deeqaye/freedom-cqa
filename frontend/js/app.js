// Shell: hash router + role switcher. Each view is a self-contained module exporting mount(el, params),
// so any screen can be embedded on its own (e.g. a Dynamics 365 HTML web resource per screen).
import { api, getRole, setRole } from "./api.js";
import { toast } from "./ui.js";

const routes = [
  [/^#\/conversations$/, "conversations", () => import("./views/conversations.js")],
  [/^#\/c\/(.+)$/, "conversations", () => import("./views/card.js"), m => ({ id: decodeURIComponent(m[1]) })],
  [/^#\/checklists$/, "checklists", () => import("./views/checklists.js")],
  [/^#\/appeals(?:\/(\d+))?$/, "appeals", () => import("./views/appeals.js"), m => ({ id: m[1] && +m[1] })],
  [/^#\/analytics$/, "analytics", () => import("./views/analytics.js")],
  [/^#\/help$/, "help", () => import("./views/help.js")],
];

const view = document.getElementById("view");
let current = null;

async function render() {
  const hash = location.hash || "#/conversations";
  const route = routes.find(([re]) => re.test(hash));
  if (!route) { location.hash = "#/conversations"; return; }
  const [re, nav, load, params] = route;
  document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("active", a.dataset.nav === nav));
  if (current && current.unmount) current.unmount();
  view.innerHTML = `<div class="empty">Загрузка…</div>`;
  try {
    const mod = await load();
    current = (await mod.mount(view, params ? params(hash.match(re)) : {})) || null;
  } catch (e) {
    console.error(e);
    view.innerHTML = `<div class="card"><h2>Ошибка</h2><p>${e.message}</p></div>`;
  }
  view.focus({ preventScroll: true });
  refreshBadge();
}

export async function refreshBadge() {
  try {
    const open = await api.get("/api/appeals?status=open");
    const b = document.getElementById("appeals-badge");
    b.hidden = !open.length;
    b.textContent = open.length;
  } catch { /* ignore */ }
}

const roleSel = document.getElementById("role");
roleSel.value = getRole();
roleSel.addEventListener("change", () => {
  setRole(roleSel.value);
  toast(`Роль: ${roleSel.selectedOptions[0].text}`);
  render();
});

api.get("/api/health").then(h => {
  document.getElementById("evaluator-info").textContent = `Оценщик: ${h.evaluator}`;
}).catch(() => {});

addEventListener("hashchange", render);
addEventListener("cqa:appeals", refreshBadge);
render();
