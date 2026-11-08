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
let navSeq = 0;  // bumps on every navigation; a page that finishes loading after the user moved on is discarded

async function render() {
  const hash = location.hash || "#/conversations";
  const route = routes.find(([re]) => re.test(hash));
  if (!route) { location.hash = "#/conversations"; return; }
  const [re, nav, load, params] = route;
  document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("active", a.dataset.nav === nav));
  if (current && current.unmount) current.unmount();
  current = null;
  // Each page mounts into its own container: a slow page (e.g. a card still fetching) that resolves after the
  // user navigated elsewhere writes into a detached box instead of painting over the new page.
  const seq = ++navSeq;
  const box = document.createElement("div");
  box.innerHTML = `<div class="empty">Загрузка…</div>`;
  view.replaceChildren(box);
  try {
    const mod = await load();
    const mounted = (await mod.mount(box, params ? params(hash.match(re)) : {})) || null;
    if (seq !== navSeq) { mounted && mounted.unmount && mounted.unmount(); return; }  // superseded
    current = mounted;
  } catch (e) {
    console.error(e);
    if (seq !== navSeq) return;
    box.innerHTML = `<div class="card"><h2>Ошибка</h2><p></p></div>`;
    box.querySelector("p").textContent = e.message;
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
