/**
 * js/ui.js
 */

// TOAST NOTIFICATIONS
const Toast = {
  _container: null,

  _ensureContainer() {
    if (this._container) return this._container;
    const el = document.createElement("div");
    el.id = "toast-region";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.className = "fixed bottom-5 right-5 z-50 flex flex-col gap-2 w-80";
    document.body.appendChild(el);
    this._container = el;
    return el;
  },

  /**
   * @param {string} message
   * @param {"info"|"success"|"error"} variant
   */
  show(message, variant = "info") {
    const container = this._ensureContainer();

    const styles = {
      info: { border: "border-border", dot: "bg-accent" },
      success: { border: "border-border", dot: "bg-status-up" },
      error: { border: "border-border", dot: "bg-status-down" },
    };
    const s = styles[variant] || styles.info;

    const toast = document.createElement("div");
    toast.className = `slide-up flex items-start gap-2.5 rounded border ${s.border} bg-surface-overlay px-3.5 py-3 shadow-lg`;
    toast.innerHTML = `
      <span class="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full ${s.dot}"></span>
      <p class="text-sm text-ink leading-snug">${escapeHtml(message)}</p>
    `;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.15s ease";
      setTimeout(() => toast.remove(), 150);
    }, 4000);
  },
};

// MODAL DIALOG
const Modal = {
  _activeEl: null,
  _previouslyFocused: null,

  /**
   * @param {{title: string, bodyHtml: string, confirmLabel?: string, onConfirm?: Function, danger?: boolean}} opts
   */
  open(opts) {
    this.close(); // only one modal at a time

    this._previouslyFocused = document.activeElement;

    const overlay = document.createElement("div");
    overlay.id = "modal-overlay";
    overlay.className = "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 fade-in";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "modal-title");

    const confirmClasses = opts.danger
      ? "bg-status-down hover:bg-red-500 text-white"
      : "bg-accent hover:bg-accent-hover text-white";

    overlay.innerHTML = `
      <div class="w-full max-w-md rounded-lg border border-border bg-surface-raised shadow-lg slide-up">
        <div class="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 id="modal-title" class="text-base font-semibold text-ink">${escapeHtml(opts.title)}</h2>
          <button data-modal-close aria-label="Close dialog" class="rounded p-1 text-ink-faint hover:bg-surface-hover hover:text-ink transition-colors">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
          </button>
        </div>
        <div class="px-5 py-4 text-sm text-ink-muted">${opts.bodyHtml}</div>
        <div class="flex justify-end gap-2 border-t border-border px-5 py-3.5">
          <button data-modal-close class="rounded-sm border border-border px-3.5 py-2 text-sm font-medium text-ink-muted hover:bg-surface-hover hover:text-ink transition-colors">
            Cancel
          </button>
          ${
            opts.onConfirm
              ? `<button data-modal-confirm class="rounded-sm px-3.5 py-2 text-sm font-medium transition-colors ${confirmClasses}">${escapeHtml(opts.confirmLabel || "Confirm")}</button>`
              : ""
          }
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    this._activeEl = overlay;

    overlay.querySelectorAll("[data-modal-close]").forEach((btn) =>
      btn.addEventListener("click", () => this.close())
    );
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) this.close();
    });

    const confirmBtn = overlay.querySelector("[data-modal-confirm]");
    if (confirmBtn && opts.onConfirm) {
      confirmBtn.addEventListener("click", async () => {
        confirmBtn.disabled = true;
        confirmBtn.textContent = "Working…";
        try {
          await opts.onConfirm();
          this.close();
        } catch (err) {
          Toast.show(err.message || "Something went wrong.", "error");
          confirmBtn.disabled = false;
          confirmBtn.textContent = opts.confirmLabel || "Confirm";
        }
      });
    }

    document.addEventListener("keydown", this._onKeydown);
    (confirmBtn || overlay.querySelector("[data-modal-close]")).focus();
  },

  _onKeydown(e) {
    if (e.key === "Escape") Modal.close();
  },

  close() {
    if (this._activeEl) {
      this._activeEl.remove();
      this._activeEl = null;
    }
    document.removeEventListener("keydown", this._onKeydown);
    if (this._previouslyFocused) this._previouslyFocused.focus();
  },
};

// SKELETON / LOADING STATES
function skeletonRows(count, columns) {
  return Array.from({ length: count })
    .map(
      () => `
      <tr class="border-b border-border-subtle">
        ${Array.from({ length: columns })
          .map(() => `<td class="px-4 py-3.5"><div class="skeleton h-3.5 w-full rounded"></div></td>`)
          .join("")}
      </tr>`
    )
    .join("");
}

function skeletonCard() {
  return `
    <div class="rounded-lg border border-border bg-surface-raised p-4">
      <div class="skeleton h-3 w-20 rounded mb-3"></div>
      <div class="skeleton h-7 w-16 rounded"></div>
    </div>`;
}

// EMPTY STATE
/**
 * @param {{icon: string, title: string, body: string, actionLabel?: string, actionHref?: string}} opts
 */
function emptyState(opts) {
  return `
    <div class="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div class="mb-4 flex h-11 w-11 items-center justify-center rounded-full border border-border text-ink-faint">
        ${opts.icon}
      </div>
      <p class="text-sm font-medium text-ink mb-1">${escapeHtml(opts.title)}</p>
      <p class="text-sm text-ink-faint max-w-sm mb-5">${escapeHtml(opts.body)}</p>
      ${
        opts.actionLabel
          ? `<a href="${opts.actionHref || "#"}" class="rounded-sm bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover transition-colors">${escapeHtml(opts.actionLabel)}</a>`
          : ""
      }
    </div>`;
}

// HELPERS
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function formatRelativeTime(isoString) {
  if (!isoString) return "—";
  const diff = Date.now() - new Date(isoString).getTime();
  if (diff < 0) return "just now";
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.floor(hr / 24);
  return `${days}d ago`;
}

function statusBadge(status) {
  const map = {
    up: { label: "Operational", dot: "bg-status-up", text: "text-status-up", bg: "bg-status-up-dim", pulse: true },
    down: { label: "Down", dot: "bg-status-down", text: "text-status-down", bg: "bg-status-down-dim", pulse: false },
    degraded: { label: "Degraded", dot: "bg-status-degraded", text: "text-status-degraded", bg: "bg-status-degraded-dim", pulse: false },
  };
  const s = map[status] || { label: "Unknown", dot: "bg-status-unknown", text: "text-status-unknown", bg: "bg-status-unknown-dim", pulse: false };

  return `
    <span class="inline-flex items-center gap-1.5 rounded-full ${s.bg} px-2.5 py-1 text-xs font-medium ${s.text}">
      <span class="h-1.5 w-1.5 rounded-full ${s.dot} ${s.pulse ? "status-pulse" : ""}"></span>
      ${s.label}
    </span>`;
}