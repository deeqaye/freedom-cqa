// Shell: hash router + role switcher. Each view is a self-contained module exporting mount(el, params),
// so any screen can be embedded on its own (e.g. a Dynamics 365 HTML web resource per screen).
import { api, getRole, setRole } from "./api.js";
import { hydrateIcons, icon } from "./icons.js";
import { skeleton, toast } from "./ui.js";

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
  view.innerHTML = skeleton("page");
  setDrawer(false);
  try {
    const mod = await load();
    current = (await mod.mount(view, params ? params(hash.match(re)) : {})) || null;
    view.style.animation = "none"; void view.offsetWidth; view.style.animation = "";  // replay page-enter animation
  } catch (e) {
    console.error(e);
    view.innerHTML = `<div class="card empty-state">${icon("alert", 28)}<h2>Не удалось открыть страницу</h2><p class="muted"></p></div>`;
    view.querySelector("p").textContent = e.message;
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

const root = document.documentElement;
const store = (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage blocked: state lasts this page only */ } };

// ---- theme (initial value set by the inline script in index.html) ----
const themeBtn = document.querySelector("[data-theme-toggle]");
function drawThemeBtn() {
  const dark = root.dataset.theme === "dark";
  themeBtn.querySelector(".ico").innerHTML = icon(dark ? "sun" : "moon");
  themeBtn.querySelector("[data-theme-label]").textContent = dark ? "Светлая тема" : "Тёмная тема";
  themeBtn.title = dark ? "Светлая тема" : "Тёмная тема";
}
themeBtn.onclick = () => {
  root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
  store("cqa.theme", root.dataset.theme);
  drawThemeBtn();
  dispatchEvent(new Event("cqa:theme"));  // canvas/SVG drawn with computed colors redraw
};

// ---- collapsible sidebar (desktop) and drawer (mobile) ----
const collapseBtn = document.querySelector("[data-collapse]");
function drawCollapseBtn() {
  const c = root.classList.contains("side-collapsed");
  collapseBtn.querySelector(".ico").innerHTML = icon(c ? "expand" : "collapse");
  collapseBtn.title = c ? "Развернуть меню" : "Свернуть меню";
  collapseBtn.setAttribute("aria-label", collapseBtn.title);
  collapseBtn.querySelector(".lbl").textContent = c ? "Развернуть" : "Свернуть";
}
function setCollapsed(c) {
  root.classList.toggle("side-collapsed", c);
  store("cqa.side", c ? "collapsed" : "expanded");
  drawCollapseBtn();
  setTimeout(() => dispatchEvent(new Event("resize")), 220);  // waveform canvases re-measure after the transition
}
collapseBtn.onclick = () => setCollapsed(!root.classList.contains("side-collapsed"));
document.querySelector("[data-role-mini]").onclick = () => setCollapsed(false);

const drawerBtn = document.querySelector("[data-drawer]");
function setDrawer(open) {
  root.classList.toggle("drawer-open", open);
  drawerBtn.setAttribute("aria-expanded", String(open));
}
drawerBtn.onclick = () => setDrawer(!root.classList.contains("drawer-open"));
document.querySelector("[data-scrim]").onclick = () => setDrawer(false);
addEventListener("keydown", e => { if (e.key === "Escape" && root.classList.contains("drawer-open")) setDrawer(false); });

hydrateIcons();
drawThemeBtn();
drawCollapseBtn();

const roleSel = document.getElementById("role");
const roleMini = document.querySelector("[data-role-mini]");
const drawRoleMini = () => { roleMini.textContent = roleSel.selectedOptions[0].text[0]; roleMini.title = `Роль: ${roleSel.selectedOptions[0].text}`; };
roleSel.value = getRole();
drawRoleMini();
roleSel.addEventListener("change", () => {
  setRole(roleSel.value);
  drawRoleMini();
  toast(`Роль: ${roleSel.selectedOptions[0].text}`);
  render();
});

api.get("/api/health").then(h => {
  document.getElementById("evaluator-info").textContent = `Оценщик: ${h.evaluator}`;
}).catch(() => {});

addEventListener("hashchange", render);
addEventListener("cqa:appeals", refreshBadge);
render();
