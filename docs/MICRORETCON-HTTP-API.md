# MicroRETCON — HTTP API + browser console spec (v1)

**Date:** 2026-09-19
**Design:** `docs/MICRORETCON-DESIGN.md` (mode A: HTTP pipe)
**Scope:** this doc is the *contract* — the ESP32 firmware and the browser
console both implement against it. Nothing here needs the crns worktree:
every endpoint is specified against the crns binding's existing surface
(`register_destination`, `set_inbound_handler`, `send_direct`, `announce`,
`path_info`, `has_path`) as vendored into RETCON today, so the SPA + a POSIX
mock server can be built and tested right now.

**Explicitness rule (user decision, 2026-09-19):** identity lives on the
device, always, and the UI says so. The WASM-peer posture (identity in the
browser) is a recorded future option (`docs/MICRORETCON-BRAINSTORM.md`
round 3) and is *not* implemented in any hidden way. The console shows
which world it's in on the status page.

## 0. Server shape (ESP32-side)

- `esp_http_server` (lwIP), port 80, no TLS — direct USB attach, nothing to
  intercept; mesh crypto is end-to-end already.
- Captive DNS: a UDP/53 responder answering every query with
  `A retcon.local → <gadget ip>` (~100 lines over lwIP). The gadget also
  answers at its raw link-local address for the DNS-ignoring case.
- Content: `/api/*` JSON; everything else static from the FAT region (the
  same files the MSC drive exposes). No server-side templating — the SPA
  is static and fills from `/api/*`.
- The API is **stateless between requests** (mesh state lives in crns
  structures on-device; UI state lives in the browser's localStorage).
  Every handler is crns-`submit()` shaped and runs on the host loop thread
  — the same discipline the Pi binding enforces.
- Max request body: 128 KB (config file replace). Max send content: the
  `send_direct` packed bound (0xFFFF); the API returns the same `TooLarge`
  error shape client-side before it hits crns.

## 1. Objects (what the JSON looks like)

```jsonc
// Status
{
  "node_name": "Field Node 3",
  "identity_hash": "a1b2c3…",           // 32-byte hex
  "identity_location": "device",        // literal, always, v1
  "mode": "transport|client",
  "transport_enabled": false,
  "firmware": "0.1.0",
  "config_hash": "…",                   // sha256 of the config file — the
                                        // UI's "is my view stale" signal
  "interfaces": [
    {"name":"rnode0","type":"RNodeInterface","online":true,"mtu":508},
    {"name":"espnow0","type":"EspNowInterface","online":true,"mtu":1450}
  ],
  "uptime_s": 1234,
  "storage": {"inbox_used": 4096, "inbox_cap": 262144}
}

// Peer (an entry of /api/peers)
{
  "dest_hash": "…",                     // 32-byte hex (the lxmf.delivery
                                        // destination the peer announced)
  "name": "operator laptop",            // from announce app_data if packed
  "last_heard": 1234,                   // unix epoch
  "age_s": 12,
  "hops": 2,                            // -1 when no path
  "has_path": true,
  "iface": "espnow0"
}

// Inbox message (an item of /api/inbox)
{
  "message_hash": "…",                  // 32-byte hex (dedup id)
  "source_hash": "…",                   // sender lxmf.delivery hash
  "timestamp": 1234.5,
  "title": "manifest",
  "content_len": 9400,
  "content": "…",                       // base64 when binary, utf-8 when it
                                        // decodes cleanly; `encoding` field
                                        // says which
  "encoding": "utf-8|base64",
  "delivery": "direct|direct_resource"  // informational only
}

// Send handle (POST /api/send response + GET /api/send/<id>)
{
  "handle": "a1b2…",                    // 32-byte hex message id
  "status": "queued|delivered|failed|cancelled"
}
```

## 2. Endpoints

| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| GET | `/api/status` | — | Status object | — |
| GET | `/api/peers` | — | `{peers:[Peer…]}` | — |
| GET | `/api/inbox?page=N` | — | `{messages:[…], page, has_more}` | — |
| GET | `/api/inbox/<hash>` | — | one message (same shape) | 404 |
| POST | `/api/send` | `{dest, title?, content}` | Send handle (201) | 400 bad dest; **413 TooLarge** (> packed bound) |
| GET | `/api/send/<handle>` | — | Send handle | 404 unknown |
| GET | `/api/config` | — | `{config: "<full file text>", hash}` | — |
| PUT | `/api/config` | `{config: "<full text>"}` | `{message, status, hash}` — validated (parse must succeed) before it is written; **write + apply semantics: file replaced, config reloaded in place, no reboot** | 400 parse error (with line info) |
| POST | `/api/announce` | — | `{announced: true}` | — |
| POST | `/api/reboot` | `{confirm:"reboot"}` | — then device reboots | 400 |
| GET | `/api/events` | — (SSE) | `event: peers-changed / inbox-changed / send-update` | — |
| GET | `/files/*` | — | static SPA assets | 404 |
| GET | `/` | — | redirect → `/files/index.html` (or serve index directly) | — |

Rules the firmware and the SPA must both honour:

- **Errors are structured**: `{"status":"error","error":{"code":"too_large"|
  "bad_dest"|"parse"|"no_path"|…, "message": "human text"}}` — the SPA
  surfaces `message`, never guesses from strings.
- **`413 TooLarge`** carries `{"limit": 61440}` (the file-send bound) so
  the SPA can say "too big — send it from the dashboard" with the number.
- **`PUT /api/config` validation is the same validation the Pi's
  `config_str` setter does**: parse must succeed, unknown keys tolerated,
  and the response returns the **new hash** so the SPA can confirm what it
  is now looking at.
- **No auth in v1** — matching the Pi's client-UI posture: physical USB
  attach is the boundary. The status page says so in the same words the
  Pi's page does ("anyone with this cable attached can change your node").
- **SSE (`/api/events`) is the only push channel**: peers-changed on a new
  announce, inbox-changed on LXMF delivery, send-updates on DirectSend
  conclusion. Reconnect-with-backoff on the client; the device sends a
  `retry: 2000` hint. No SSE = the SPA polls (v1 fallback is fine — the
  endpoints are identical).

## 3. Identity: what the UI says, verbatim

The status page carries a fixed, plain-words identity statement:

> **This node's mesh identity lives on this device.** It survives browser
> clears, computer changes, and reboots. The device holds the secret; this
> window is only a view.

`GET /api/status` exposes `identity_location: "device"`. The SPA renders
it as a badge on the status tab. If a future design ever moves identity,
the badge is where the change shows — the field is the contract.

## 4. UI/UX spec — the console

### 4.1 Design language

- **98.css, vendored, self-contained** — the same theme the Pi's client UI
  already uses (MIT, 26 KB, no build step). Fonts: ship the two Pixelated
  MS Sans Serif woffs on the device (the Pi's copy is missing them and
  silently falls back to Arial — the spec requires the fonts *or* the
  fallback is accepted and documented; v1 ships them, +100 KB on flash,
  nothing in RAM).
- The retro-window framing is not decoration: it *is* the layout grammar —
  a single window, a tab strip, dense field rows. Same information
  architecture as the Pi's `index.html` (Applications / Wifi / Files /
  Advanced / Credits) so the two consoles feel like siblings.
- **No build step, no npm**: static HTML + one `app.js` + one `ui.css`.
  Vanilla ES2020, no framework. Target: every page functional with JS
  disabled? — **no** (the SPA needs JS to fetch JSON), but every *action*
  degrades to a working form POST fallback on the few state-changing
  endpoints (config, send) — v1 note: JSON-only is acceptable if forms
  would double the surface; pinned: **the SPA must never block reading
  status/inbox on JS features newer than ES2020 or on SSE** (poll fallback
  built in).
- Density budget: the whole SPA ≤ 30 KB gzipped, ≤ 120 KB unpacked,
  including 98.css. No images beyond the logo (reuse the Pi's).

### 4.2 Tabs

1. **Status** (default) — node name, identity hash (truncated, click to
   copy full), `identity_location` badge ("keys live on this device"),
   mode badge, transport on/off, interface list with online dots, uptime,
   peers-heard count. Live-updating via SSE (poll fallback 5 s).
2. **Peers** — table: name (from app_data), hash (truncated), last-heard
   (human), hops, path freshness. Row actions: *Compose to*, *Ping*
   (sends a 1-byte LXMF "ping" titled `ping`), *Copy hash*. Sorted by
   last-heard; stale entries greyed after 2× announce interval. "Request
   path" button for no-path peers (the same `request_path` call the
   console's `sendfile` uses).
3. **Messages** — two panes: list (title, source name/hash, age, size) +
   read view. Compose opens the same pane: dest picker fed from
   `/api/peers` (name → hash, or paste-hash), title, content (textarea,
   ~60 KB soft cap shown live against the limit). Send → the handle's
   status line is rendered *in the compose pane* (queued → delivered /
   failed / cancelled) via SSE — not a modal, not a page reload. Inbox
   pagination: "Older" button, cursor from the API. No on-browser inbox
   state beyond the open page — the device ring is the truth.
4. **Config** — the same file-in-a-textarea the Pi's Advanced tab is, with
   the same save semantics, **plus**: (a) a validity check on submit with
   the parser's line info on failure, (b) a "changes applied live — no
   reboot needed" notice (the ESP32 reloads config in place; the Pi's
   "reboot to apply" wording is a Pi-side artifact), (c) the raw file is
   the *only* config editor — no form-based duplicate, so there's exactly
   one way to change a setting and it's the same on both consoles.
   Also on this tab: Reboot (with `confirm`), Announce Now.
5. **Files** — the MSC volume listing (read-only in v1), which is the same
   flash region: `START_HERE.html`, `config`, docs. The browser reads it
   over HTTP (`/files/*`) — not via the OS drive — so it works even when
   the drive is mounted elsewhere.

### 4.3 The interaction contract (behaviour, not just pixels)

- **Polling vs SSE**: the SPA prefers SSE; if the connection drops it
  falls back to 5 s polling of status/peers/inbox. Both paths use the
  same JSON shapes.
- **Optimistic UI is limited to form feedback**: config save and announce
  show immediate success; *message send is never optimistic* — the
  compose pane shows "queued" from the handle and updates on send-updates.
  A FAILED status shows the reason verbatim from the API.
- **No destructive action without a typed confirmation**: config replace
  (shows a diff of what changed, computed client-side from the two
  texts), reboot. The Pi's "erase everything" danger-zone button has no
  v1 analogue (nothing to erase but the config, which has its own
  confirmation).
- **Stale-view protection**: every GET of status/config carries
  `config_hash`; the SPA polls it cheaply and if it changes while the
  user is editing config, it offers "reload the config" rather than
  silently overwriting.
- **The device is a shared resource**: the UI must tolerate another
  browser being connected simultaneously (no session state, no exclusive
  locks — last write wins on config, with the hash check as the guard).
  This is stated in the spec *because* it constrains the API's v2 (no
  cookies/sessions are assumed by any endpoint).

### 4.3.1 What's deliberately *not* in the UI (v1)

- No on-device JS runtime, no server-side templating, no login screen
  (physical attach is the auth), no file *upload* to the device (the
  drive is read-only in v1; config goes through the API), no message
  drafts stored on-device (localStorage only, with a "drafts live in this
  browser" note), no notification sounds, no theme switcher (98.css is
  the theme), no maps, no attachments.
- NomadNet page browsing is **not** here: NomadNet is a *python-rns*
  peer; MicroRETCON's console is the node's own console. A `.mu` browser
  would be a *second* app talking to the same mesh — later scope.

## 5. The mock server (how this is built before the ESP32 exists)

`microretcon/ui/mock_server.py` — a single-file Flask app (same shape as
the Pi's `retcon_client_ui.py`: one file, stdlib + flask) that serves the
same static SPA and implements every endpoint against a live crns
**binding** (vendored, `crns_lib/`) on the Pi — i.e. the mock is not a
mock of the mesh, only of the USB boundary. Consequences:

- Every endpoint is exercised against the real mesh (announces, peers,
  DirectSend round-trips) before the firmware exists.
- The SPA's entire surface is testable today, and the endpoint contract is
  *proven* — the ESP32 firmware's job is then "make these exact responses
  from crns's C API", with the doc as the shared spec.
- The mock doubles as the Pi-side test harness: point the SPA at a Pi
  running the mock and you have the console UI on the Pi too — one UI for
  both devices, which is the "same RETCON, different box" promise.

`GET /api/status` on the mock adds `"mock": true` so the UI can badge it.

## 6. Acceptance (v1, all testable on POSIX before the device)

1. `GET /api/status` returns the full status object; the SPA status tab
   renders it, badge included.
2. Two live crns hosts: console A hears console B's announce → Peers tab
   lists it with name + freshness → Compose → send 60 KB → DELIVERED
   shown in-pane → console B's inbox shows it (SSE or poll fallback).
3. `PUT /api/config` with a valid file applies live (peers/config reflect
   it) and with an invalid file returns 400 + line info without
   corrupting the running config.
4. Config replace flow asks for confirmation and shows a computed diff.
5. TooLarge: a > bound send returns 413 with the limit; the UI shows the
   limit and the dashboard path hint.
6. The whole console works in Firefox *and* Chromium (no Web Serial, no
   WASM, no optional APIs in the critical path).
7. Total served payload ≤ 30 KB gzipped; zero external network requests
   (fonts included or fallback documented).

## 7. Firmware-side notes (what the ESP32 implementation must keep)

- Handlers are submit()-shaped: an API call that touches crns state runs
  on the host loop via the same `submit` discipline the python binding
  uses; lwIP handler threads never call crns directly.
- The inbox ring, config file, and identity are the same FAT/NVS regions
  the MSC drive exposes — one source of truth, two read windows (the
  concurrency rule from the design doc: the drive is read-only in v1; the
  API writes).
- SSE fan-out: a small subscriber list per event class; the host loop
  publishes on dispatch (inbox-changed), announce ingest (peers-changed),
  and DirectSend conclusion (send-update). No browser holds state the
  device doesn't have.