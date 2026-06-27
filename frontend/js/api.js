/**
 * js/api.js
 */

const API_BASE = (
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1"
)
  ? "http://localhost:8000"
  : "https://webhook-monitor-u662.onrender.com"; // ← replace with your real Render URL

const TOKEN_KEY = "wm_access_token"; // sessionStorage, not localStorage — cleared per tab session

const Auth = {
  getToken() {
    return sessionStorage.getItem(TOKEN_KEY);
  },
  setToken(token) {
    sessionStorage.setItem(TOKEN_KEY, token);
  },
  clearToken() {
    sessionStorage.removeItem(TOKEN_KEY);
  },
  isLoggedIn() {
    return Boolean(this.getToken());
  },
};
 
function authHeaders() {
  const token = Auth.getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
 
function handleUnauthorized() {
  Auth.clearToken();
  if (!location.pathname.endsWith("index.html") && location.pathname !== "/") {
    window.location.href = "index.html";
  }
}
 
async function request(method, path, body) {
  const headers = { ...authHeaders() };
  if (body !== undefined) headers["Content-Type"] = "application/json";
 
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (networkError) {
    throw new ApiError(
      "Could not reach the server. Check your connection and try again.",
      0
    );
  }
 
  let data = null;
  try {
    data = await response.json();
  } catch {
    // empty body — fine for some endpoints
  }
 
  // A 401 here means "you HAD a session and it's no longer valid" —
  // that's the right moment to clear the stale token and bounce to
  // login. It does NOT cover a login/signup attempt that was rejected
  // for some other reason (wrong password, unconfirmed email) — those
  // come back as 401/403 too, but there was never a session to expire
  // in the first place, so redirecting and showing "session expired"
  // would be actively misleading. We only apply that handling when a
  // token actually existed before this request was made.
  const hadTokenBeforeThisRequest = Boolean(Auth.getToken());
 
  if (response.status === 401 && hadTokenBeforeThisRequest) {
    handleUnauthorized();
    throw new ApiError("Your session has expired. Please log in again.", 401);
  }
 
  if (!response.ok) {
    const message = data?.detail || data?.message || `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
 
  return data;
}
 
class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}
 
const Api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body ?? {}),
  patch: (path, body) => request("PATCH", path, body ?? {}),
  delete: (path) => request("DELETE", path),
 
  // ── Auth ──
  signup: (email, password) => request("POST", "/api/auth/signup", { email, password }),
  login: (email, password) => request("POST", "/api/auth/login", { email, password }),
  me: () => request("GET", "/api/auth/me"),
 
  // ── Endpoints ──
  listEndpoints: () => request("GET", "/api/endpoints/"),
  getEndpoint: (id) => request("GET", `/api/endpoints/${id}`),
  createEndpoint: (data) => request("POST", "/api/endpoints/", data),
  updateEndpoint: (id, data) => request("PATCH", `/api/endpoints/${id}`, data),
  deleteEndpoint: (id) => request("DELETE", `/api/endpoints/${id}`),
 
  // ── Dashboard ──
  dashboardSummary: () => request("GET", "/api/dashboard/summary"),
  recentEvents: (limit = 50) => request("GET", `/api/dashboard/events/recent?limit=${limit}`),
 
  // ── Health ──
  allHealth: () => request("GET", "/api/health/"),
  endpointHealth: (id) => request("GET", `/api/health/${id}`),
  checkNow: (id) => request("POST", `/api/health/${id}/check-now`),
  endpointAlerts: (id) => request("GET", `/api/health/${id}/alerts`),
 
  // ── Events for one endpoint (webhook receiver route) ──
  endpointEvents: (id) => request("GET", `/webhook/${id}/events`),
 
  // ── Delivery ──
  queueStatus: () => request("GET", "/api/delivery/queue-status"),
  eventDelivery: (eventId) => request("GET", `/api/delivery/event/${eventId}`),
  endpointDeliveryStats: (id) => request("GET", `/api/delivery/endpoint/${id}/stats`),
  retryNow: (eventId) => request("POST", `/api/delivery/event/${eventId}/retry-now`),
 
  // ── AI ──
  endpointDiagnoses: (id) => request("GET", `/api/ai/endpoint/${id}/diagnoses`),
  eventSummary: (eventId) => request("GET", `/api/ai/event/${eventId}/summary`),
 
  // ── Alerts ──
  alertDeliveries: (id) => request("GET", `/api/alerts/endpoint/${id}/deliveries`),
  updateAlertPrefs: (id, prefs) => {
    const params = new URLSearchParams(prefs).toString();
    return request("PATCH", `/api/alerts/endpoint/${id}/preferences?${params}`);
  },
 
  // ── System ──
  systemHealth: () => request("GET", "/health"),
};