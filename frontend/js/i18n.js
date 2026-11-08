// UI language switch: RU (source) / KK / EN.
// - Static text (labels, buttons, help text) is written in Russian in the views and translated on the rendered page
//   by a MutationObserver using DICT (exact match on the trimmed text of a text node or a title/placeholder/aria-label).
// - Text with values inside is built with tf("template {x}", {x}) at render time; views re-render on a switch.
// - Content is never translated: anything inside [data-raw] (dialogue messages, comments, model rationale);
//   [data-raw-attrs] keeps an element's attributes as they are (e.g. evidence buttons whose title is a message).
import { DICT } from "./i18n-dict.js";

export const LANGS = [["ru", "RU"], ["kk", "ҚАЗ"], ["en", "EN"]];
const COL = { kk: 0, en: 1 };
// Numbers/dates for Kazakh use the Russian conventions (comma decimals, dd.mm.yyyy) — browsers' kk data is uneven.
const LOCALE = { ru: "ru-RU", kk: "ru-RU", en: "en-US" };

let lang = "ru";
try { const s = localStorage.getItem("cqa.lang"); if (s in LOCALE) lang = s; } catch { /* storage blocked: default RU */ }

export const getLang = () => lang;
export const locale = () => LOCALE[lang];

/** Translation of a Russian source string (returned unchanged if unknown or RU). */
export function t(ru) {
  if (lang === "ru" || ru == null) return ru;
  const e = DICT[ru] || DICT[String(ru).replace(/\s+/g, " ").trim()];  // keys are single-spaced
  return (e && e[COL[lang]]) || ru;
}

/** Template with {name} placeholders: tf("{n} диалогов", {n: 5}). Values are inserted as given (escape HTML first). */
export function tf(ru, params = {}) {
  return t(ru).replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k] ?? "") : m));
}

/** Model rationale in the UI language when the evaluator provided a translation (rationale_i18n: {en, kk}). */
export const rationaleOf = c => (lang !== "ru" && c && c.rationale_i18n && c.rationale_i18n[lang]) || (c && c.rationale) || "";

// ---------------------------------------------------------------- DOM translation
const ATTRS = ["title", "placeholder", "aria-label"];
const textSrc = new WeakMap();   // text node -> Russian source
const textOut = new WeakMap();   // text node -> value we last wrote
const attrSrc = new WeakMap();   // element -> {attr: source}
const attrOut = new WeakMap();   // element -> {attr: value we last wrote}

const rawEl = el => !el || !!el.closest("[data-raw], script, style, textarea");

function translateCore(s) {
  const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(s);
  if (!m[2]) return s;
  const out = t(m[2]);
  return out === m[2] ? s : m[1] + out + m[3];
}

function doText(node) {
  if (rawEl(node.parentElement)) return;
  let src = textSrc.get(node);
  if (src === undefined || node.nodeValue !== textOut.get(node)) { src = node.nodeValue; textSrc.set(node, src); }  // new or changed by the app
  const out = lang === "ru" ? src : translateCore(src);
  if (node.nodeValue !== out) node.nodeValue = out;
  textOut.set(node, out);
}

function doAttr(el, name) {
  if (!el.hasAttribute(name) || el.closest("[data-raw-attrs]") || rawEl(el)) return;
  const srcs = attrSrc.get(el) || {}, outs = attrOut.get(el) || {};
  const cur = el.getAttribute(name);
  if (!(name in srcs) || cur !== outs[name]) srcs[name] = cur;
  const out = lang === "ru" ? srcs[name] : translateCore(srcs[name]);
  if (cur !== out) el.setAttribute(name, out);
  outs[name] = out;
  attrSrc.set(el, srcs); attrOut.set(el, outs);
}

function doTree(root) {
  if (root.nodeType === Node.TEXT_NODE) return doText(root);
  if (root.nodeType !== Node.ELEMENT_NODE) return;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) doText(n);
  const els = [root, ...root.querySelectorAll(ATTRS.map(a => `[${a}]`).join(","))];
  for (const el of els) for (const a of ATTRS) if (el.hasAttribute && el.hasAttribute(a)) doAttr(el, a);
}

const observer = new MutationObserver(muts => {
  for (const m of muts) {
    if (m.type === "childList") m.addedNodes.forEach(doTree);
    else if (m.type === "characterData") doText(m.target);
    else if (m.type === "attributes") doAttr(m.target, m.attributeName);
  }
});

export function startI18n() {
  document.documentElement.lang = lang === "kk" ? "kk" : lang;
  document.title = t("CQA — Анализ качества диалогов");
  doTree(document.body);
  observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
}

/** Switch language: re-translate what is on screen, then views re-render (listen for "cqa:lang"). */
export function setLang(l) {
  if (!(l in LOCALE) || l === lang) return;
  lang = l;
  try { localStorage.setItem("cqa.lang", l); } catch { /* ignore */ }
  document.documentElement.lang = l === "kk" ? "kk" : l;
  document.title = t("CQA — Анализ качества диалогов");
  doTree(document.body);
  dispatchEvent(new Event("cqa:lang"));
}
