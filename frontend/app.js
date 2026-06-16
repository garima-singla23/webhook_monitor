// app.js
// ─────────────────────────────────────────────
// Frontend JavaScript for Webhook Monitor
// Handles: API calls, UI updates, navigation
// ─────────────────────────────────────────────

const API = "http://localhost:8000";

// ════════════════════════════════
// INITIALIZATION
// ════════════════════════════════

// Run when page loads
document.addEventListener("DOMContentLoaded", async () => {
  await checkApiHealth();
  await loadDashboard();
});


// ════════════════════════════════
// NAVIGATION
// ════════════════════════════════

function showTab(tabName) {
  // Hide all tabs
  document.querySelectorAll(".tab").forEach(tab => {
    tab.classList.remove("active");
  });

  // Remove active from all nav items
  document.querySelectorAll(".nav-item").forEach(item => {
    item.classList.remove("active");
  });

  // Show selected tab
  const tab = document.getElementById(`tab-${tabName}`);
  if (tab) tab.classList.add("active");

  // Highlight nav item
  event.target.classList.add("active");

  // Load data for tab
  if (tabName === "dashboard") loadDashboard();
  if (tabName === "endpoints") loadEndpoints();
  if (tabName === "events") loadEvents();
  if (tabName === "register") resetRegisterForm();
}


// ════════════════════════════════
// API HEALTH CHECK
// ════════════════════════════════

async function checkApiHealth() {
  const dot = document.getElementById("apiStatus");
  const text = document.getElementById("apiStatusText");

  try {
    const response = await fetch(`${API}/health`);
    if (response.ok) {
      dot.className = "status-dot online";
      text.textContent = "API Online";
    } else {
      throw new Error("not ok");
    }
  } catch {
    dot.className = "status-dot offline";
    text.textContent = "API Offline";
  }
}


// ════════════════════════════════
// DASHBOARD
// ════════════════════════════════

async function loadDashboard() {
  try {
    const data = await apiGet("/api/dashboard/summary");

    if (!data.success) return;

    // Update summary stats
    const s = data.summary;
    setText("totalEndpoints", s.total_endpoints);
    setText("activeEndpoints", s.active_endpoints);
    setText("totalEvents", s.total_events);

    // Render recent events
    renderEvents(
      "recentEvents",
      data.recent_events,
      true // wrap in section
    );

  } catch (e) {
    console.error("Dashboard error:", e);
  }
}


// ════════════════════════════════
// ENDPOINTS
// ════════════════════════════════

async function loadEndpoints() {
  const container = document.getElementById("endpointsList");
  container.innerHTML = '<div class="loading-text">Loading...</div>';

  try {
    const data = await apiGet("/api/endpoints/");

    if (!data.success || data.endpoints.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <p>No endpoints registered yet</p>
          <button class="btn-primary" onclick="showTab('register')">
             Add Your First Endpoint
          </button>
        </div>
      `;
      return;
    }

    // Render endpoint cards
    container.innerHTML = data.endpoints
      .map(ep => renderEndpointCard(ep))
      .join("");

  } catch (e) {
    container.innerHTML =
      '<div class="loading-text">Failed to load endpoints</div>';
    console.error(e);
  }
}


function renderEndpointCard(ep) {
  const stats = ep.stats || {};
  const webhookUrl = `${API}/webhook/${ep.id}`;
  const isActive = ep.is_active !== false;

  const providerEmojis = {
    razorpay: "💳",
    stripe: "💰",
    github: "🐙",
    generic: "🔗"
  };

  return `
    <div class="endpoint-card">
      <div class="endpoint-header">
        <span class="endpoint-name">
          ${providerEmojis[ep.provider] || "🔗"} ${ep.name}
        </span>
        <span class="provider-badge">${ep.provider}</span>
      </div>

      <div class="endpoint-url">${ep.url}</div>

      <div class="endpoint-stats">
        <div class="endpoint-stat">
          <span class="endpoint-stat-value">
            ${stats.total || 0}
          </span>
          <span class="endpoint-stat-label">Total</span>
        </div>
        <div class="endpoint-stat">
          <span class="endpoint-stat-value" style="color: var(--green)">
            ${stats.received || 0}
          </span>
          <span class="endpoint-stat-label">Received</span>
        </div>
        <div class="endpoint-stat">
          <span class="endpoint-stat-value" style="color: var(--red)">
            ${stats.failed || 0}
          </span>
          <span class="endpoint-stat-label">Failed</span>
        </div>
        <div class="endpoint-stat">
          <span class="endpoint-stat-value" style="color: ${isActive ? 'var(--green)' : 'var(--red)'}">
            ${isActive ? "Active" : "Paused"}
          </span>
          <span class="endpoint-stat-label">Status</span>
        </div>
      </div>

      <div class="endpoint-footer">
        <div class="endpoint-webhook-url">
           ${webhookUrl}
        </div>
        <button
          class="btn-copy"
          onclick="copyToClipboard('${webhookUrl}')"
        >
          
        </button>
      </div>
    </div>
  `;
}


// ════════════════════════════════
// EVENTS
// ════════════════════════════════

async function loadEvents() {
  const container = document.getElementById("allEventsList");
  container.innerHTML =
    '<div class="loading-text">Loading...</div>';

  try {
    const data = await apiGet("/api/dashboard/events/recent?limit=50");

    if (!data.success) return;

    renderEvents("allEventsList", data.events, false);

  } catch (e) {
    container.innerHTML =
      '<div class="loading-text">Failed to load events</div>';
  }
}


function renderEvents(containerId, events, wrapInSection) {
  const container = document.getElementById(containerId);

  if (!events || events.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <p>No events yet</p>
        <p style="font-size: 0.8rem">
          Events will appear here when webhooks are received
        </p>
      </div>
    `;
    return;
  }

  const rows = events.map(event => renderEventRow(event)).join("");

  if (wrapInSection) {
    container.innerHTML = `<div class="section">
      <div class="section-header">
        <h2>Recent Webhook Events</h2>
      </div>
      <div class="events-list">${rows}</div>
    </div>`;
  } else {
    container.innerHTML = rows;
  }
}


function renderEventRow(event) {
  const status = event.status || "received";
  const readable = event.readable || event.event_type || "Webhook";
  const provider = event.provider || "generic";
  const time = formatTime(event.received_at);

  // Get endpoint name if joined
  const endpointName = event.endpoints?.name || provider;

  const providerEmojis = {
    razorpay: "💳",
    stripe: "💰",
    github: "🐙",
    generic: "🔗"
  };

  const icon = providerEmojis[provider] || "📨";

  const badgeClass = {
    received: "badge-received",
    delivered: "badge-delivered",
    failed: "badge-failed"
  }[status] || "badge-received";

  return `
    <div class="event-row">
      <div class="event-icon">${icon}</div>
      <div class="event-body">
        <div class="event-readable">${readable}</div>
        <div class="event-meta">
          ${endpointName} • ${event.event_type || "webhook"}
        </div>
      </div>
      <div class="event-time">${time}</div>
      <div class="event-badge ${badgeClass}">${status}</div>
    </div>
  `;
}


// ════════════════════════════════
// REGISTER ENDPOINT
// ════════════════════════════════

async function registerEndpoint() {
  const name = document.getElementById("endpointName").value.trim();
  const url = document.getElementById("endpointUrl").value.trim();
  const provider = document.getElementById("endpointProvider").value;
  const threshold = parseInt(
    document.getElementById("endpointThreshold").value
  );

  // Clear previous messages
  hideElement("registerError");
  hideElement("registerSuccess");
  hideElement("webhookUrlBox");

  // Validate
  if (!name) {
    showFormError("registerError", "Please enter a name");
    return;
  }
  if (!url) {
    showFormError("registerError", "Please enter a URL");
    return;
  }
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    showFormError("registerError", "URL must start with http:// or https://");
    return;
  }

  try {
    const data = await apiPost("/api/endpoints/", {
      name,
      url,
      provider,
      threshold_ms: threshold
    });

    if (data.success) {
      // Show success message
      showFormSuccess(
        "registerSuccess",
        `Endpoint "${name}" registered successfully!`
      );

      // Show the webhook URL to use
      const webhookUrl = `${API}${data.webhook_url}`;
      document.getElementById("generatedUrl").textContent = webhookUrl;
      showElement("webhookUrlBox");

      // Clear form
      document.getElementById("endpointName").value = "";
      document.getElementById("endpointUrl").value = "";

      showToast(" Endpoint registered!");

    } else {
      showFormError("registerError", "Registration failed");
    }

  } catch (e) {
    showFormError("registerError", `Error: ${e.message}`);
  }
}


function resetRegisterForm() {
  hideElement("registerError");
  hideElement("registerSuccess");
  hideElement("webhookUrlBox");
}


function copyUrl() {
  const url = document.getElementById("generatedUrl").textContent;
  copyToClipboard(url);
}


// ════════════════════════════════
// API HELPERS
// ════════════════════════════════

async function apiGet(path) {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }
  return response.json();
}

async function apiPost(path, body) {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
}


// ════════════════════════════════
// UI HELPERS
// ════════════════════════════════

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function showElement(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
}

function hideElement(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("hidden");
}

function showFormError(id, message) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = "⚠️ " + message;
    el.classList.remove("hidden");
  }
}

function showFormSuccess(id, message) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = "✅ " + message;
    el.classList.remove("hidden");
  }
}

function showToast(message, duration = 3000) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), duration);
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast(" Copied to clipboard!");
  }).catch(() => {
    // Fallback for older browsers
    const el = document.createElement("textarea");
    el.value = text;
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
    showToast(" Copied!");
  });
}

function formatTime(timestamp) {
  if (!timestamp) return "—";

  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;

    // Less than 1 minute
    if (diff < 60000) {
      return "Just now";
    }
    // Less than 1 hour
    if (diff < 3600000) {
      return `${Math.floor(diff / 60000)}m ago`;
    }
    // Less than 24 hours
    if (diff < 86400000) {
      return `${Math.floor(diff / 3600000)}h ago`;
    }
    // Older
    return date.toLocaleDateString();

  } catch {
    return timestamp;
  }
}