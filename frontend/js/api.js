// Thin API client. apiBase is configurable so the UI can be hosted as a Dynamics 365 web resource.
const base = () => (window.CQA_CONFIG && window.CQA_CONFIG.apiBase) || "";

let role = "admin";
try { role = localStorage.getItem("cqa.role") || "admin"; } catch { /* storage unavailable */ }

export const getRole = () => role;
export function setRole(r) {
  role = r;
  try { localStorage.setItem("cqa.role", r); } catch { /* ignore */ }
}

async function req(method, path, body) {
  const opts = { method, headers: { "X-Role": role } };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(base() + path, opts);
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!r.ok) {
    let msg = data && data.detail ? data.detail : `${r.status} ${r.statusText}`;
    if (Array.isArray(msg)) msg = msg.map(e => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return data;
}

export const api = {
  get: p => req("GET", p),
  post: (p, b) => req("POST", p, b ?? {}),
  put: (p, b) => req("PUT", p, b),
  del: p => req("DELETE", p),
  url: p => base() + p,
};
