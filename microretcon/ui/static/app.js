/* MicroRETCON console — vanilla ES2020, no build step.
   Contract: docs/MICRORETCON-HTTP-API.md. SSE preferred, poll fallback. */
"use strict";

const API = "/api";
let configHash = null;
let inboxPage = 0;
let sse = null;
let pollTimer = null;
let peersById = {};      // dest_hash -> peer object (for the compose picker)
let selectedPeer = null; // dest_hash
let currentTab = "status";

// -- tiny helpers ---------------------------------------------------------

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtAge = (epoch) => {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - epoch));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
};
const trunc = (hash, n = 12) => (hash ? hash.slice(0, n) + "…" : "—");

async function api(path, opts) {
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const err = (body && body.error) || { code: "http_" + res.status, message: res.statusText };
    const e = new Error(err.message || err.code);
    e.code = err.code;
    throw e;
  }
  return body;
}

// -- tabs -------------------------------------------------------------------

function showTab(name) {
  currentTab = name;
  for (const tab of document.querySelectorAll("menu[role=tablist] > li")) {
    const link = tab.querySelector("a");
    if (link.dataset.tab === name) tab.setAttribute("aria-selected", "true");
    else tab.removeAttribute("aria-selected");
  }
  for (const panel of document.querySelectorAll(".tab-panel")) {
    if (panel.dataset.panel === name) panel.setAttribute("data-active", "1");
    else panel.removeAttribute("data-active");
  }
  if (name === "status") refreshStatus();
  if (name === "peers") refreshPeers();
  if (name === "messages") { refreshPeers(); refreshInbox(); }
}
document.querySelectorAll("menu[role=tablist] a").forEach((a) =>
  a.addEventListener("click", (ev) => {
    ev.preventDefault();
    showTab(a.dataset.tab);
  })
);

// -- status -------------------------------------------------------------------

async function refreshStatus() {
  const loading = $("status-loading");
  if (loading) loading.hidden = false;
  try {
    const s = await api("/api/status");
    $("node-name").textContent = s.node_name;
    $("badge-mode").textContent = s.mode;
    $("identity-hash").textContent = trunc(s.identity_hash, 16) + "…";
    $("identity-hash").title = s.identity_hash;
    $("identity-hash").onclick = () => navigator.clipboard?.writeText(s.identity_hash);
    $("transport-state").textContent = s.transport_enabled ? "on (forwarding)" : "off";
    $("interfaces").textContent = s.interfaces
      .map((i) => `${i.name} (${i.online ? "up" : "down"})`)
      .join(", ");
    $("storage").textContent = `${s.storage.inbox_messages} msgs (cap ${s.storage.inbox_cap})`;
    $("uptime").textContent = `up ${fmtAge(Math.floor(Date.now() / 1000) - s.uptime_s)} ago start`;
    $("about-firmware").textContent = s.firmware;
    $("sb-mock").textContent = s.mock ? "MOCK — real mesh, simulated USB" : "";
    if (s.identity_location !== "device") {
      // The explicitness rule: if this ever changes, the badge is where it shows.
      $("badge-identity").textContent = "identity location: " + s.identity_location;
      $("identity-note").hidden = false;
    }
    configHash = s.config_hash;
    if (loading) loading.hidden = true;
  } catch (e) {
    if (loading) {
      loading.hidden = false;
      loading.textContent = "failed to reach the device — retrying…";
    }
    throw e;
  }
}

// -- peers ----------------------------------------------------------------------

let composeLimit = null;

async function refreshPeers() {
  const p = await api("/api/peers");
  peersById = {};
  const body = $("peers-body");
  body.textContent = "";
  if (!p.peers.length) {
    body.innerHTML = `<tr><td colspan="6">no peers heard yet</td></tr>`;
  }
  for (const peer of p.peers) {
    peersById[peer.dest_hash] = peer;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${esc(peer.name ?? "(unnamed)")}</td>
      <td><code>${trunc(peer.dest_hash, 10)}</code></td>
      <td>${fmtAge(peer.last_heard)}</td>
      <td>${peer.hops < 0 ? "?" : peer.hops}</td>
      <td>${peer.has_path ? "yes" : "no"}</td>
      <td>
        <button data-act="compose" data-dest="${peer.dest_hash}">compose</button>
        <button data-act="path" data-dest="${peer.dest_hash}" ${peer.has_path ? "disabled" : ""}>path</button>
      </td>`;
    body.appendChild(tr);
  }
  // compose picker
  const picker = $("compose-dest");
  picker.innerHTML =
    `<option value="">— pick a peer —</option>` +
    p.peers
      .map(
        (peer) =>
          `<option value="${peer.dest_hash}">${esc(peer.name ?? trunc(peer.dest_hash, 10))}</option>`
      )
      .join("");
  $("btn-request-path").disabled = !p.peers.length;
}

$("peers-body").addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button");
  if (!btn) return;
  const dest = btn.dataset.dest;
  if (btn.dataset.act === "compose") {
    showTab("messages");               // rebuilds the picker — order matters
    $("compose-dest").value = dest;    // select AFTER the rebuild
    $("compose-dest-hash").value = "";
    $("compose-content").focus();
  } else if (btn.dataset.act === "path") {
    $("peers-hint").textContent = "path request sent…";
    try {
      await api("/api/peers/" + dest + "/request_path", { method: "POST" });
      $("peers-hint").textContent = "path request sent";
    } catch (e) {
      $("peers-hint").textContent = "path request failed: " + e.message;
    }
  }
});
$("btn-request-path").addEventListener("click", () => {
  const first = Object.keys(peersById)[0];
  if (first) requestPath(first);
});
async function requestPath(dest) {
  try {
    await api(`/api/peers/${dest}/request_path`, { method: "POST" });
    $("peers-hint").textContent = "path request sent";
  } catch (e) {
    $("peers-hint").textContent = "failed: " + e.message;
  }
}

// -- messages -------------------------------------------------------------------

let inboxCursor = 0;

async function refreshInbox(page = inboxCursor) {
  const data = await api(`/api/inbox?page=${page}`);
  inboxCursor = data.page;
  const body = $("inbox-body");
  body.textContent = "";
  if (!data.messages.length) body.innerHTML = `<tr><td colspan="3">empty</td></tr>`;
  for (const msg of data.messages) {
    const tr = document.createElement("tr");
    tr.dataset.hash = msg.message_hash;
    const name = peersById[msg.source_hash]?.name ?? trunc(msg.source_hash, 8);
    tr.innerHTML = `<td>${esc(msg.title || "(no title)")}</td>
      <td>${esc(name)}</td>
      <td>${fmtAge(msg.timestamp)}</td>`;
    tr.addEventListener("click", () => {
      body.querySelectorAll("tr").forEach((r) => r.classList.remove("selected"));
      tr.classList.add("selected");
      renderMessage(msg);
    });
    body.appendChild(tr);
  }
  $("inbox-older").disabled = !data.has_more;
  $("inbox-newer").disabled = data.page === 0;
}

function renderMessage(msg) {
  const name = peersById[msg.source_hash]?.name ?? trunc(msg.source_hash, 10);
  const el = $("msg-read-view");
  el.innerHTML = `<div class="msg-meta"><strong>${esc(msg.title || "(no title)")}</strong>
    · ${esc(name)} · ${new Date(msg.timestamp * 1000).toLocaleString()} · ${msg.content_len} B</div>
    <div>${esc(msg.content)}</div>`;
}

$("inbox-older").addEventListener("click", () => refreshInbox(inboxCursor + 1));
$("inbox-newer").addEventListener("click", () => refreshInbox(Math.max(0, inboxCursor - 1)));

// -- compose + send -----------------------------------------------------------------

function composeDest() {
  return $("compose-dest-hash").value.trim() || $("compose-dest").value;
}
$("compose-content").addEventListener("input", () => {
  const bytes = new TextEncoder().encode($("compose-content").value).length;
  $("compose-size").textContent = String(bytes);
  if (composeLimit && bytes > composeLimit) $("compose-size").style.color = "#a00000";
  else $("compose-size").style.color = "";
});
$("compose-dest").addEventListener("change", () => {
  $("compose-dest-hash").value = "";
});

$("btn-send").addEventListener("click", async () => {
  const statusEl = $("send-status");
  const dest = composeDest();
  if (!dest) {
    statusEl.textContent = "choose a recipient first";
    statusEl.className = "send-status failed";
    return;
  }
  const content = $("compose-content").value;
  const title = $("compose-title").value;
  statusEl.textContent = "sending…";
  statusEl.className = "send-status queued";
  $("btn-send").disabled = true;
  try {
    const res = await api("/api/send", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ dest, title, content }),
    });
    // The contract: sends are NEVER optimistic. Poll the handle until terminal.
    let handle = res.handle;
    statusEl.textContent = "queued";
    const deadline = Date.now() + 90_000;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 500));
      const st = await api(`/api/send/${handle}`);
      statusEl.textContent = st.status;
      statusEl.className = "send-status " + st.status;
      if (st.status !== "queued") break;
    }
    if (statusEl.textContent === "delivered") {
      $("compose-content").value = "";
      $("compose-title").value = "";
      $("compose-size").textContent = "0";
    }
  } catch (e) {
    statusEl.textContent = e.code === "too_large" ? "too large — use the dashboard" : "failed: " + e.message;
    statusEl.className = "send-status failed";
  } finally {
    $("btn-send").disabled = false;
  }
});

// -- config ---------------------------------------------------------------------------

async function refreshConfig() {
  const data = await api("/api/config");
  $("config-text").value = data.config;
  configHash = data.hash;
}

$("btn-config-save").addEventListener("click", async () => {
  const statusEl = $("config-status");
  const text = $("config-text").value;
  statusEl.textContent = "saving…";
  try {
    const res = await api("/api/config", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ config: text }),
    });
    configHash = res.hash;
    statusEl.textContent = res.message + " (hash " + res.hash + ")";
  } catch (e) {
    statusEl.textContent = "save failed: " + e.message;
  }
});

$("btn-announce").addEventListener("click", async () => {
  await api("/api/announce", { method: "POST" });
  $("btn-announce").textContent = "announced ✓";
  setTimeout(() => ($("btn-announce").textContent = "Announce now"), 1500);
});

$("btn-reboot").addEventListener("click", async () => {
  if (!window.confirm("Reboot the device?")) return;
  const typed = window.prompt('Type "reboot" to confirm:');
  if (typed !== "reboot") return;
  await api("/api/reboot", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ confirm: "reboot" }),
  });
  $("sb-conn").textContent = "rebooting… reconnecting shortly";
});

// -- live updates: SSE with poll fallback -------------------------------------------

let eventSource = null;

function startSSE() {
  try {
    eventSource = new EventSource("/api/events");
    eventSource.addEventListener("peers-changed", () => {
      if (currentTab === "peers") refreshPeers();
    });
    eventSource.addEventListener("inbox-changed", () => {
      if (currentTab === "messages") refreshInbox(inboxCursor);
    });
    eventSource.addEventListener("send-update", () => {
      /* send polls its own handle; nothing to do here in v1 */
    });
    eventSource.onerror = () => {
      // cffi/firmware may not implement SSE yet — fall back to polling.
      eventSource.close();
      eventSource = null;
      startPolling();
    };
    $("sb-conn").textContent = "live";
    return true;
  } catch {
    return false;
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      if (currentTab === "status") await refreshStatus();
      else if (currentTab === "peers") await refreshPeers();
      else if (currentTab === "messages") await refreshInbox(inboxCursor);
      $("sb-conn").textContent = "polling (5s)";
    } catch {
      $("sb-conn").textContent = "device unreachable — retrying…";
    }
  }, 5000);
}

// -- boot -----------------------------------------------------------------------------

async function boot() {
  try {
    const s = await api("/api/status");
    $("sb-conn").textContent = s.mock ? "connected (mock server — real mesh)" : "connected";
    $("sb-mock").textContent = s.mock ? "mock" : "";
    await refreshStatus();
    await refreshPeers();
    await refreshInbox(0);
    await refreshConfig();
    if (!startSSE()) startPolling();
  } catch (e) {
    $("sb-conn").textContent = "device unreachable — retrying in 5s…";
    setTimeout(boot, 5000);
  }
}
boot();