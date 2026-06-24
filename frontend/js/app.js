// app.js — Phase 2
// Handles: navigation, dashboard, health monitor, endpoints, events
// ─────────────────────────────────────────────────────────────────

const API = "http://localhost:8000";

// ════════════════════════════════
// AUTH STATE (Phase 7)
// ════════════════════════════════
// The access token lives only in memory (a plain JS variable),
// NOT localStorage — per this app's standing rule against
// browser storage in any context that has one. This means a
// page refresh logs the user out, which is an honest tradeoff:
// simpler and safer against XSS-style token theft, at the cost
// of needing to log in again after every refresh. A production
// version would typically use an httpOnly cookie set by the
// backend instead, which this simple frontend doesn't do.

let currentUser = null;
let accessToken = null;

function authHeaders() {
  return accessToken ? { "Authorization": `Bearer ${accessToken}` } : {};
}

function handleAuthExpired() {
  currentUser = null;
  accessToken = null;
  showLoginScreen("Your session expired — please log in again.");
}

async function signup(email, password) {
  const r = await fetch(`${API}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Signup failed");
  return data;
}

async function login(email, password) {
  const r = await fetch(`${API}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Login failed");
  return data;
}

function logout() {
  currentUser = null;
  accessToken = null;
  if (ws) ws.close();
  showLoginScreen();
}

function showLoginScreen(message = "") {
  document.getElementById("authScreen").classList.remove("hidden");
  document.getElementById("appShell").classList.add("hidden");
  const errEl = document.getElementById("authError");
  if (message) {
    errEl.textContent = message;
    errEl.classList.remove("hidden");
  } else {
    errEl.classList.add("hidden");
  }
}

function showApp() {
  document.getElementById("authScreen").classList.add("hidden");
  document.getElementById("appShell").classList.remove("hidden");
  const emailLabel = document.getElementById("currentUserEmail");
  if (emailLabel) emailLabel.textContent = currentUser?.email || "";
}

async function handleAuthFormSubmit(mode) {
  const email = document.getElementById("authEmail").value.trim();
  const password = document.getElementById("authPassword").value;
  const errEl = document.getElementById("authError");
  errEl.classList.add("hidden");

  if (!email || !password) {
    errEl.textContent = "Enter both email and password";
    errEl.classList.remove("hidden");
    return;
  }

  try {
    if (mode === "signup") {
      const result = await signup(email, password);
      if (!result.session) {
        // Email confirmation required before login works
        errEl.textContent = result.message;
        errEl.style.color = "var(--green)";
        errEl.classList.remove("hidden");
        return;
      }
      accessToken = result.session.access_token;
      currentUser = result.user;
    } else {
      const result = await login(email, password);
      accessToken = result.access_token;
      currentUser = result.user;
    }

    showApp();
    await initDashboard();

  } catch (e) {
    errEl.style.color = "var(--red)";
    errEl.textContent = e.message;
    errEl.classList.remove("hidden");
  }
}

// Currently selected endpoint for health tab
let selectedEndpointId = null;

// ════════════════════════════════
// INIT
// ════════════════════════════════

document.addEventListener("DOMContentLoaded", async () => {
  // Phase 7: the dashboard no longer loads automatically —
  // it only starts once a real login or signup succeeds.
  showLoginScreen();
});

async function initDashboard() {
  await checkApiHealth();
  await loadDashboard();
  await populateEndpointSelect();
  connectWebSocket();   // Phase 5: open live connection

  // Auto-refresh every 60 seconds — kept as a fallback even
  // with WebSockets active, in case a connection silently
  // misses a message or the user has been on the tab a long time.
  setInterval(async () => {
    if (!accessToken) return;  // logged out — stop refreshing
    const activeTab = document.querySelector(".tab.active")?.id;
    if (activeTab === "tab-dashboard") await loadDashboard();
    if (activeTab === "tab-health" && selectedEndpointId) await loadEndpointHealth();
  }, 60000);
}



// ════════════════════════════════
// NAVIGATION
// ════════════════════════════════

function showTab(tabName, el) {
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));

  const tab = document.getElementById(`tab-${tabName}`);
  if (tab) tab.classList.add("active");
  if (el) el.classList.add("active");

  if (tabName === "dashboard") loadDashboard();
  if (tabName === "health")    { loadHealth(); populateEndpointSelect(); }
  if (tabName === "endpoints") loadEndpoints();
  if (tabName === "events")    loadEvents();
  if (tabName === "register")  resetRegisterForm();
}


// ════════════════════════════════
// API HEALTH
// ════════════════════════════════

async function checkApiHealth() {
  const dot  = document.getElementById("apiStatus");
  const text = document.getElementById("apiStatusText");
  try {
    const r = await fetch(`${API}/health`);
    if (r.ok) {
      dot.className  = "status-dot online";
      text.textContent = "API Online";
    } else throw new Error();
  } catch {
    dot.className  = "status-dot offline";
    text.textContent = "API Offline";
  }
}


// ════════════════════════════════
// DASHBOARD
// ════════════════════════════════

async function loadDashboard() {
  try {
    // Load health overview + webhook events in parallel
    const [healthData, dashData] = await Promise.all([
      apiGet("/api/health/"),
      apiGet("/api/dashboard/summary")
    ]);

    // Stats
    if (healthData.success) {
      setText("totalEndpoints", healthData.summary.total);
      setText("upCount",        healthData.summary.up);
      setText("downCount",      healthData.summary.down);
      setText("degradedCount",  healthData.summary.degraded);
    }

    if (dashData.success) {
      setText("totalEvents", dashData.summary.total_events);
    }

    // Health overview table
    if (healthData.success) {
      renderHealthOverview(healthData.endpoints);
    }

    // Recent events
    if (dashData.success) {
      renderEventRows("recentEvents", dashData.recent_events);
    }

  } catch (e) {
    console.error("Dashboard error:", e);
  }
}


function renderHealthOverview(endpoints) {
  const container = document.getElementById("healthOverview");
  if (!endpoints || endpoints.length === 0) {
    container.innerHTML = `<div class="empty-state"><p>No endpoints yet</p></div>`;
    return;
  }

  const rows = endpoints.map(ep => {
    const status  = ep.status || "unknown";
    const uptime  = ep.uptime_percentage != null ? `${ep.uptime_percentage}%` : "—";
    const respMs  = ep.last_response_ms != null ? `${ep.last_response_ms}ms` : "—";
    const checked = ep.last_checked ? formatTime(ep.last_checked) : "Never";
    const cdn     = ep.cdn_detected
      ? `<span style="color:var(--accent)">✅ ${ep.cdn_provider}</span>`
      : `<span style="color:var(--text-muted)">—</span>`;

    return `
      <tr>
        <td><strong>${ep.name}</strong></td>
        <td><span class="status-pill ${status}">${statusEmoji(status)} ${status}</span></td>
        <td>${uptime}</td>
        <td class="${responseClass(ep.last_response_ms)}">${respMs}</td>
        <td>${cdn}</td>
        <td>${checked}</td>
        <td>
          <button class="btn-secondary" style="padding:4px 10px;font-size:0.75rem"
            onclick="openHealthForEndpoint('${ep.endpoint_id}')">
            Details
          </button>
        </td>
      </tr>`;
  }).join("");

  container.innerHTML = `
    <table class="health-table">
      <thead>
        <tr>
          <th>Name</th><th>Status</th><th>Uptime</th>
          <th>Response</th><th>CDN</th><th>Last Check</th><th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function openHealthForEndpoint(endpointId) {
  selectedEndpointId = endpointId;
  document.getElementById("healthEndpointSelect").value = endpointId;
  showTab("health", document.querySelector('[data-tab="health"]'));
  loadEndpointHealth();
}


// ════════════════════════════════
// HEALTH TAB
// ════════════════════════════════

async function loadHealth() {
  // Nothing to do here — endpoint select handles it
}

async function populateEndpointSelect() {
  try {
    const data = await apiGet("/api/endpoints/");
    const select = document.getElementById("healthEndpointSelect");
    const current = select.value;

    // Keep first placeholder option
    select.innerHTML = '<option value="">— Choose an endpoint —</option>';

    (data.endpoints || []).forEach(ep => {
      const opt = document.createElement("option");
      opt.value = ep.id;
      opt.textContent = `${ep.name} (${ep.provider})`;
      select.appendChild(opt);
    });

    // Restore selection if it still exists
    if (current) select.value = current;

  } catch (e) {
    console.error("Could not load endpoints for select:", e);
  }
}

async function loadEndpointHealth() {
  const select = document.getElementById("healthEndpointSelect");
  const endpointId = select.value;

  if (!endpointId) {
    document.getElementById("healthDetail").classList.add("hidden");
    document.getElementById("healthEmpty").classList.remove("hidden");
    return;
  }

  selectedEndpointId = endpointId;
  document.getElementById("healthEmpty").classList.add("hidden");
  document.getElementById("healthDetail").classList.remove("hidden");

  try {
    const data = await apiGet(`/api/health/${endpointId}`);
    if (!data.success) return;

    const h = data.health;

    // Status banner
    const banner  = document.getElementById("statusBanner");
    const status  = h.current_status || "unknown";
    banner.className = `status-banner ${status}`;
    setText("statusIcon",    statusEmoji(status));
    setText("statusText",    status.toUpperCase().replace("_", " "));
    setText("statusSubtext", h.last_checked ? `Last checked ${formatTime(h.last_checked)}` : "Never checked");

    // Metrics
    setText("uptimeValue",     h.uptime_percentage != null ? `${h.uptime_percentage}%` : "—");
    setText("avgResponseValue", h.avg_response_ms != null ? `${h.avg_response_ms}` : "—");
    setText("failuresValue",   h.consecutive_failures ?? 0);

    // CDN
    if (data.cdn && data.cdn.detected) {
      setText("cdnValue", data.cdn.provider || "Yes");
    } else {
      setText("cdnValue", "None");
    }

    // Recent checks
    renderHealthChecks(data.recent_checks || []);

    // Alerts
    const alertData = await apiGet(`/api/health/${endpointId}/alerts`);
    renderAlerts(alertData.alerts || []);

  } catch (e) {
    console.error("Health load error:", e);
  }
}

function renderHealthChecks(checks) {
  const container = document.getElementById("recentChecks");
  if (!checks.length) {
    container.innerHTML = '<div class="loading-text">No health checks yet — first check runs within 60 seconds</div>';
    return;
  }

  container.innerHTML = checks.map(c => {
    const respMs   = c.response_time_ms != null ? c.response_time_ms : null;
    const respText = respMs != null ? `${respMs}ms` : "—";
    const cls      = responseClass(respMs);
    const cdn      = c.cdn_detected ? `🌐 ${c.cdn_provider}` : "";
    const err      = c.error_message ? `<div class="check-error">${c.error_message}</div>` : "";

    return `
      <div class="check-row">
        <div class="check-status-dot ${c.status}"></div>
        <div class="check-body">
          <div class="check-status-text">${c.status.toUpperCase()}</div>
          ${err}
          ${cdn ? `<div class="check-cdn">${cdn}</div>` : ""}
        </div>
        <div class="check-time-col">
          <div class="check-response ${cls}">${respText}</div>
          <div class="check-timestamp">${formatTime(c.checked_at)}</div>
        </div>
      </div>`;
  }).join("");
}

function renderAlerts(alerts) {
  const container = document.getElementById("alertsList");
  if (!alerts.length) {
    container.innerHTML = '<div class="loading-text">No alerts yet — great sign! 🎉</div>';
    return;
  }

  container.innerHTML = alerts.map(a => {
    const icon = a.alert_type === "recovered" ? "✅" : a.alert_type === "down" ? "🔴" : "⚠️";
    return `
      <div class="alert-row">
        <div class="alert-icon">${icon}</div>
        <div class="alert-msg">${a.message}</div>
        <div class="alert-time">${formatTime(a.sent_at)}</div>
      </div>`;
  }).join("");
}

async function triggerManualCheck() {
  if (!selectedEndpointId) return;
  showToast("⚡ Running health check...");
  try {
    const data = await apiPost(`/api/health/${selectedEndpointId}/check-now`, {});
    if (data.success) {
      const r = data.result;
      showToast(`${statusEmoji(r.status)} ${r.status.toUpperCase()} — ${r.response_time_ms ?? "N/A"}ms`);
      await loadEndpointHealth();
    }
  } catch (e) {
    showToast("❌ Check failed");
  }
}


// ════════════════════════════════
// ENDPOINTS TAB
// ════════════════════════════════

async function loadEndpoints() {
  const container = document.getElementById("endpointsList");
  container.innerHTML = '<div class="loading-text">Loading...</div>';
  try {
    const data = await apiGet("/api/endpoints/");
    if (!data.success || !data.endpoints.length) {
      container.innerHTML = `
        <div class="empty-state">
          <p>No endpoints yet</p>
          <button class="btn-primary" onclick="showTab('register', null)">➕ Add Endpoint</button>
        </div>`;
      return;
    }
    container.innerHTML = data.endpoints.map(ep => renderEndpointCard(ep)).join("");
  } catch (e) {
    container.innerHTML = '<div class="loading-text">Failed to load</div>';
  }
}

function renderEndpointCard(ep) {
  const stats  = ep.stats || {};
  const wUrl   = `${API}/webhook/${ep.id}`;
  const active = ep.is_active !== false;
  const status = ep.last_status || "unknown";

  const icons = { razorpay:"💳", stripe:"💰", github:"🐙", generic:"🔗" };

  return `
    <div class="endpoint-card">
      <div class="endpoint-header">
        <span class="endpoint-name">${icons[ep.provider]||"🔗"} ${ep.name}</span>
        <span class="provider-badge">${ep.provider}</span>
      </div>
      <div class="endpoint-url">${ep.url}</div>
      <div class="endpoint-stats">
        <div class="endpoint-stat">
          <span class="endpoint-stat-value">${stats.total||0}</span>
          <span class="endpoint-stat-label">Events</span>
        </div>
        <div class="endpoint-stat">
          <span class="endpoint-stat-value" style="color:var(--green)">${stats.received||0}</span>
          <span class="endpoint-stat-label">Received</span>
        </div>
        <div class="endpoint-stat">
          <span class="endpoint-stat-value" style="color:var(--${status==='up'?'green':status==='down'?'red':'yellow'})">${status}</span>
          <span class="endpoint-stat-label">Health</span>
        </div>
        <div class="endpoint-stat">
          <span class="endpoint-stat-value" style="color:${active?'var(--green)':'var(--red)'}">${active?"Active":"Paused"}</span>
          <span class="endpoint-stat-label">Status</span>
        </div>
      </div>
      <div class="endpoint-footer">
        <div class="endpoint-webhook-url">📥 ${wUrl}</div>
        <button class="btn-copy" onclick="copyToClipboard('${wUrl}')">📋</button>
      </div>
    </div>`;
}


// ════════════════════════════════
// EVENTS TAB
// ════════════════════════════════

async function loadEvents() {
  const container = document.getElementById("allEventsList");
  container.innerHTML = '<div class="loading-text">Loading...</div>';
  try {
    const data = await apiGet("/api/dashboard/events/recent?limit=50");
    renderEventRows("allEventsList", data.events || []);
  } catch {
    container.innerHTML = '<div class="loading-text">Failed to load</div>';
  }
}

function renderEventRows(containerId, events) {
  const container = document.getElementById(containerId);
  if (!events || !events.length) {
    container.innerHTML = `<div class="empty-state"><p>No events yet</p></div>`;
    return;
  }
  container.innerHTML = events.map(ev => {
    const provider = ev.provider || "generic";
    const icons    = { razorpay:"💳", stripe:"💰", github:"🐙", generic:"📨" };
    const status   = ev.status || "received";
    const badge    = { received:"badge-received", delivered:"badge-delivered", failed:"badge-failed" }[status] || "badge-received";
    const epName   = ev.endpoints?.name || provider;
    return `
      <div class="event-row">
        <div class="event-icon">${icons[provider]||"📨"}</div>
        <div class="event-body">
          <div class="event-readable">${ev.readable || ev.event_type || "Webhook"}</div>
          <div class="event-meta">${epName} • ${ev.event_type||"webhook"}</div>
        </div>
        <div class="event-time">${formatTime(ev.received_at)}</div>
        <div class="event-badge ${badge}">${status}</div>
      </div>`;
  }).join("");
}


// ════════════════════════════════
// REGISTER ENDPOINT
// ════════════════════════════════

async function registerEndpoint() {
  const name      = document.getElementById("endpointName").value.trim();
  const url       = document.getElementById("endpointUrl").value.trim();
  const provider  = document.getElementById("endpointProvider").value;
  const threshold = parseInt(document.getElementById("endpointThreshold").value);

  hideEl("registerError"); hideEl("registerSuccess"); hideEl("webhookUrlBox");

  if (!name) return showFormError("registerError", "Please enter a name");
  if (!url)  return showFormError("registerError", "Please enter a URL");
  if (!url.startsWith("http://") && !url.startsWith("https://"))
    return showFormError("registerError", "URL must start with http:// or https://");

  try {
    const data = await apiPost("/api/endpoints/", { name, url, provider, threshold_ms: threshold });
    if (data.success) {
      showFormSuccess("registerSuccess", `"${name}" registered!`);
      const wUrl = `${API}${data.webhook_url}`;
      document.getElementById("generatedUrl").textContent = wUrl;
      showEl("webhookUrlBox");
      showToast("✅ Endpoint registered — health checks start in 60s");
      await populateEndpointSelect();
    }
  } catch (e) {
    showFormError("registerError", e.message);
  }
}

function copyUrl() {
  copyToClipboard(document.getElementById("generatedUrl").textContent);
}

function resetRegisterForm() {
  hideEl("registerError"); hideEl("registerSuccess"); hideEl("webhookUrlBox");
}


// ════════════════════════════════
// API HELPERS
// ════════════════════════════════

async function apiGet(path) {
  const r = await fetch(`${API}${path}`, {
    headers: authHeaders()
  });
  if (r.status === 401) { handleAuthExpired(); throw new Error("Not authenticated"); }
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function apiPost(path, body) {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body)
  });
  if (r.status === 401) { handleAuthExpired(); throw new Error("Not authenticated"); }
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}

async function apiPatch(path, body) {
  const r = await fetch(`${API}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body)
  });
  if (r.status === 401) { handleAuthExpired(); throw new Error("Not authenticated"); }
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}


// ════════════════════════════════
// UI HELPERS
// ════════════════════════════════

function setText(id, v) { const e = document.getElementById(id); if (e) e.textContent = v; }
function showEl(id)  { const e = document.getElementById(id); if (e) e.classList.remove("hidden"); }
function hideEl(id)  { const e = document.getElementById(id); if (e) e.classList.add("hidden"); }

function showFormError(id, msg) {
  const e = document.getElementById(id);
  if (e) { e.textContent = "⚠️ " + msg; e.classList.remove("hidden"); }
}
function showFormSuccess(id, msg) {
  const e = document.getElementById(id);
  if (e) { e.textContent = "✅ " + msg; e.classList.remove("hidden"); }
}

function showToast(msg, ms = 3000) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), ms);
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text)
    .then(() => showToast("📋 Copied!"))
    .catch(() => showToast("❌ Copy failed"));
}

function formatTime(ts) {
  if (!ts) return "—";
  try {
    const d    = new Date(ts);
    const diff = Date.now() - d;
    if (diff < 60000)   return "Just now";
    if (diff < 3600000) return `${Math.floor(diff/60000)}m ago`;
    if (diff < 86400000)return `${Math.floor(diff/3600000)}h ago`;
    return d.toLocaleDateString();
  } catch { return ts; }
}

function statusEmoji(status) {
  return { up:"✅", down:"❌", degraded:"⚠️", unknown:"❓", never_checked:"🔘" }[status] || "❓";
}

function responseClass(ms) {
  if (ms == null) return "";
  if (ms < 300)  return "fast";
  if (ms < 1000) return "medium";
  return "slow";
}


// ════════════════════════════════
// WEBSOCKET — LIVE DASHBOARD (Phase 5)
// ════════════════════════════════

let ws = null;
let wsReconnectAttempts = 0;
const WS_MAX_RECONNECT_DELAY = 30000; // cap backoff at 30s

function getWsUrl() {
  // Build ws:// or wss:// from whatever protocol the page loaded with,
  // so this works locally (ws://localhost:8000) and once deployed
  // behind https (wss://yourapp.com) without changing any code.
  //
  // Phase 7: the browser WebSocket API can't set custom headers,
  // so the access token rides along as a query parameter instead
  // of an Authorization header — the backend's /ws route reads it
  // from there to at least require a logged-in user to connect.
  const apiUrl = new URL(API);
  const wsProtocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  const tokenParam = accessToken ? `?token=${encodeURIComponent(accessToken)}` : "";
  return `${wsProtocol}//${apiUrl.host}/ws${tokenParam}`;
}

function connectWebSocket() {
  ws = new WebSocket(getWsUrl());

  ws.onopen = () => {
    console.log("WebSocket connected");
    wsReconnectAttempts = 0;  // reset backoff on a clean connect
    setWsIndicator(true);
  };

  ws.onmessage = (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      return; // ignore anything that isn't valid JSON
    }
    handleWsMessage(message.type, message.data);
  };

  ws.onclose = () => {
    console.log("WebSocket disconnected — will attempt reconnect");
    setWsIndicator(false);
    scheduleReconnect();
  };

  ws.onerror = () => {
    // onclose will fire right after this — reconnect logic lives there,
    // so onerror just needs to exist to avoid an unhandled error in console.
  };
}

function scheduleReconnect() {
  // Exponential backoff: 1s, 2s, 4s, 8s... capped at 30s.
  // Prevents hammering the server with reconnect attempts if
  // it's down for an extended period.
  const delay = Math.min(
    1000 * Math.pow(2, wsReconnectAttempts),
    WS_MAX_RECONNECT_DELAY
  );
  wsReconnectAttempts++;

  console.log(`Reconnecting in ${delay / 1000}s...`);
  setTimeout(connectWebSocket, delay);
}

function setWsIndicator(connected) {
  // Reuses the existing API status dot/text in the sidebar —
  // if the WebSocket is down, that's worth surfacing even if
  // the REST API itself is fine.
  const dot = document.getElementById("apiStatus");
  const text = document.getElementById("apiStatusText");
  if (!dot || !text) return;

  if (connected) {
    text.textContent = "Live";
  } else {
    text.textContent = "Reconnecting...";
    dot.className = "status-dot offline";
  }
}

function handleWsMessage(type, data) {
  switch (type) {
    case "webhook_received":
      onWebhookReceived(data);
      break;
    case "health_status_changed":
      onHealthStatusChanged(data);
      break;
    case "delivery_retrying":
      onDeliveryRetrying(data);
      break;
    case "delivery_delivered":
      onDeliveryDelivered(data);
      break;
    case "delivery_failed":
      onDeliveryFailed(data);
      break;
    case "ai_diagnosis_ready":
      onAiDiagnosisReady(data);
      break;
    default:
      console.log("Unknown WS message type:", type);
  }
}


// ── Individual event handlers ──
// Each one does two things: shows an immediate toast so the
// person sees *something happened right now*, and refreshes
// the relevant section of the dashboard if it's the active tab,
// rather than blindly re-rendering tabs nobody is looking at.

function onWebhookReceived(data) {
  showToast(`📨 ${data.readable || data.event_type || "Webhook received"}`);

  const activeTab = document.querySelector(".tab.active")?.id;
  if (activeTab === "tab-dashboard") loadDashboard();
  if (activeTab === "tab-events") loadEvents();
}

function onHealthStatusChanged(data) {
  const icon = statusEmoji(data.current_status);
  showToast(
    `${icon} ${data.endpoint_name}: ${data.previous_status} → ${data.current_status}`
  );

  const activeTab = document.querySelector(".tab.active")?.id;
  if (activeTab === "tab-dashboard") loadDashboard();
  if (activeTab === "tab-health" && selectedEndpointId === data.endpoint_id) {
    loadEndpointHealth();
  }
}

function onDeliveryRetrying(data) {
  showToast(`Retry #${data.retry_count} scheduled in ${data.next_retry_in_seconds}s`);
}

function onDeliveryDelivered(data) {
  if (data.delivered_after_retry) {
    showToast(`Delivered after ${data.retry_count} retr${data.retry_count === 1 ? "y" : "ies"}`);
  }
  // Silent on first-try delivery — too frequent to toast every single one
}

function onDeliveryFailed(data) {
  showToast(`Delivery permanently failed: ${data.error_message || "unknown error"}`);

  const activeTab = document.querySelector(".tab.active")?.id;
  if (activeTab === "tab-events") loadEvents();
}

function onAiDiagnosisReady(data) {
  const cacheTag = data.from_cache ? " (cached)" : "";
  showToast(`AI diagnosis ready${cacheTag}: ${data.likely_cause}`);

  const activeTab = document.querySelector(".tab.active")?.id;
  if (activeTab === "tab-health" && selectedEndpointId === data.endpoint_id) {
    loadEndpointHealth();
  }
}