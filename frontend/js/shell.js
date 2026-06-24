/**
 * js/shell.js
 */

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard", href: "/static/dashboard.html", icon: "grid" },
  { key: "endpoints", label: "Endpoints", href: "/static/endpoints.html", icon: "link" },
  { key: "settings", label: "Settings", href: "/static/settings.html", icon: "settings" },
];

const ICONS = {
  grid: `<rect x="2" y="2" width="6" height="6" rx="1"/><rect x="10" y="2" width="6" height="6" rx="1"/><rect x="2" y="10" width="6" height="6" rx="1"/><rect x="10" y="10" width="6" height="6" rx="1"/>`,
  link: `<path d="M6.5 9.5l3-3M5 7L3.5 8.5a2.5 2.5 0 003.5 3.5L8.5 11M11 9l1.5-1.5a2.5 2.5 0 00-3.5-3.5L7.5 5" stroke-linecap="round" fill="none"/>`,
  settings: `<circle cx="8" cy="8" r="2"/><path d="M8 1.5v2M8 12.5v2M2.6 4.6l1.4 1.4M12 10l1.4 1.4M1.5 8h2M12.5 8h2M2.6 11.4l1.4-1.4M12 6l1.4-1.4" stroke-linecap="round" fill="none"/>`,
  logout: `<path d="M6 14H3.5A1.5 1.5 0 012 12.5v-9A1.5 1.5 0 013.5 2H6M10.5 11l3-3-3-3M13.5 8h-8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`,
  menu: `<path d="M2 4h12M2 8h12M2 12h12" stroke-linecap="round" fill="none"/>`,
};

const Shell = {
  async mount({ active }) {
    if (!Auth.isLoggedIn()) {
      window.location.href = "index.html";
      return false;
    }

    this._renderSidebar(active);
    this._renderMobileTopbar();
    await this._loadUser();
    return true;
  },

  _renderSidebar(active) {
    const el = document.getElementById("shell-sidebar");
    if (!el) return;

    el.innerHTML = `
      <div class="flex h-full flex-col">
        <div class="flex items-center gap-2 px-5 py-5">
          <div class="flex h-6 w-6 items-center justify-center rounded bg-accent text-white">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M8 1L2 9h4l-1 6 7-9H8l1-5z" fill="currentColor"/>
            </svg>
          </div>
          <span class="text-sm font-semibold text-ink">Webhook Monitor</span>
        </div>

        <nav class="flex-1 px-3" aria-label="Primary">
          ${NAV_ITEMS.map((item) => this._navLink(item, active)).join("")}
        </nav>

        <div class="border-t border-border px-3 py-3">
          <div class="flex items-center gap-2.5 rounded-sm px-2.5 py-2">
            <div id="shell-user-avatar" class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-surface-hover text-xs font-medium text-ink-muted">
              …
            </div>
            <div class="min-w-0 flex-1">
              <p id="shell-user-email" class="truncate text-xs font-medium text-ink">Loading…</p>
            </div>
            <button id="shell-logout-btn" aria-label="Log out" class="flex-shrink-0 rounded p-1.5 text-ink-faint hover:bg-surface-hover hover:text-ink transition-colors">
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">${ICONS.logout}</svg>
            </button>
          </div>
        </div>
      </div>
    `;

    document.getElementById("shell-logout-btn").addEventListener("click", () => {
      Auth.clearToken();
      window.location.href = "index.html";
    });
  },

  _navLink(item, active) {
    const isActive = item.key === active;
    return `
      <a href="${item.href}"
         class="mb-0.5 flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-sm transition-colors ${
           isActive
             ? "bg-surface-hover text-ink font-medium"
             : "text-ink-muted hover:bg-surface-hover hover:text-ink"
         }"
         ${isActive ? 'aria-current="page"' : ""}>
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true">${ICONS[item.icon]}</svg>
        ${item.label}
      </a>`;
  },

  _renderMobileTopbar() {
    const el = document.getElementById("shell-topbar-mobile");
    if (!el) return;

    el.innerHTML = `
      <div class="flex items-center justify-between border-b border-border bg-surface-raised px-4 py-3 lg:hidden">
        <div class="flex items-center gap-2">
          <div class="flex h-5 w-5 items-center justify-center rounded bg-accent text-white">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 1L2 9h4l-1 6 7-9H8l1-5z" fill="currentColor"/></svg>
          </div>
          <span class="text-sm font-semibold text-ink">Webhook Monitor</span>
        </div>
        <button id="shell-mobile-menu-btn" aria-label="Open navigation menu" aria-expanded="false" class="rounded p-1.5 text-ink-muted hover:bg-surface-hover">
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">${ICONS.menu}</svg>
        </button>
      </div>
    `;

    document.getElementById("shell-mobile-menu-btn").addEventListener("click", () => {
      const sidebar = document.getElementById("shell-sidebar-wrapper");
      const isOpen = sidebar.classList.contains("translate-x-0");
      sidebar.classList.toggle("translate-x-0", !isOpen);
      sidebar.classList.toggle("-translate-x-full", isOpen);
      document.getElementById("shell-mobile-menu-btn").setAttribute("aria-expanded", String(!isOpen));
    });
  },

  async _loadUser() {
    try {
      const { user } = await Api.me();
      const emailEl = document.getElementById("shell-user-email");
      const avatarEl = document.getElementById("shell-user-avatar");
      if (emailEl) emailEl.textContent = user.email;
      if (avatarEl) avatarEl.textContent = user.email.slice(0, 1).toUpperCase();
    } catch {
      // handled by Api's 401 interceptor already
    }
  },
};