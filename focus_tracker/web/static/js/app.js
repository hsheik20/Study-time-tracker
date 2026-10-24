// App shell: hash-based routing, theme toggle, and the "session running" pill.
// Each page lives in views/<name>.js and exports render(container) → optional cleanup fn.

import { api } from "./api.js";
import { esc, clock, icon } from "./ui.js";
import * as dashboard from "./views/dashboard.js";
import * as focus from "./views/focus.js";
import * as history from "./views/history.js";
import * as activities from "./views/activities.js";
import * as insights from "./views/insights.js";

const ROUTES = {
  dashboard: { view: dashboard, title: "Dashboard", subtitle: "Your focus at a glance" },
  focus: { view: focus, title: "Focus Sessions", subtitle: "Your current session and focus habits" },
  history: { view: history, title: "History", subtitle: "Every session, grouped by day" },
  activities: { view: activities, title: "Activities", subtitle: "Where your focus time goes" },
  insights: { view: insights, title: "AI Insights", subtitle: "Personalised weekly insights" },
};

const viewEl = document.getElementById("view");
let cleanup = null;
let renderToken = 0;

async function navigate() {
  const name = location.hash.replace(/^#\/?/, "") || "dashboard";
  const route = ROUTES[name] || ROUTES.dashboard;
  const token = ++renderToken;

  if (typeof cleanup === "function") cleanup();
  cleanup = null;

  document.querySelectorAll(".nav-link").forEach((link) => {
    const active = link.dataset.route === (ROUTES[name] ? name : "dashboard");
    link.classList.toggle("active", active);
    link.toggleAttribute("aria-current", active);
  });
  document.getElementById("page-title").textContent = route.title;
  document.getElementById("page-subtitle").textContent = route.subtitle;
  document.title = `${route.title} · Focus Tracker`;

  viewEl.innerHTML = `<div class="grid stats-grid">${'<div class="skeleton"></div>'.repeat(4)}</div>`;
  try {
    const result = await route.view.render(viewEl);
    if (token !== renderToken) { if (typeof result === "function") result(); return; }
    cleanup = result;
  } catch (error) {
    if (token !== renderToken) return;
    viewEl.innerHTML = `
      <div class="card error-card">
        <div class="empty">
          <div class="empty-icon">${icon("alert")}</div>
          <h3>Couldn't load this page</h3>
          <p>${esc(error.message)}. Is the Focus Tracker server still running?</p>
        </div>
      </div>`;
  }
  viewEl.classList.remove("view-enter");
  void viewEl.offsetWidth; // restart the entrance animation
  viewEl.classList.add("view-enter");
}

// ---------- Theme ----------

const root = document.documentElement;
const toggle = document.getElementById("theme-toggle");

function applyThemeLabel() {
  const next = root.dataset.theme === "dark" ? "light" : "dark";
  toggle.setAttribute("aria-label", `Switch to ${next} mode`);
  toggle.title = `Switch to ${next} mode`;
}

toggle.addEventListener("click", () => {
  root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
  try { localStorage.setItem("focus-theme", root.dataset.theme); } catch (_) {}
  applyThemeLabel();
});
applyThemeLabel();

// ---------- Running-session pill ----------

const pill = document.getElementById("active-pill");

async function refreshPill() {
  try {
    const { session } = await api.activeSession();
    if (!session) { pill.hidden = true; return; }
    const time = session.remaining_seconds != null
      ? `${clock(session.remaining_seconds)} left` : `${clock(session.focused_seconds)}`;
    pill.className = `active-pill${session.paused ? " paused" : ""}`;
    pill.innerHTML = `<span class="pulse-dot${session.paused ? " paused" : ""}"></span>
      <span class="pill-text">${session.paused ? "Paused" : "Focusing"} · ${esc(session.activity)} · ${time}</span>`;
    pill.hidden = false;
  } catch (_) {
    pill.hidden = true;
  }
}

window.addEventListener("hashchange", navigate);
navigate();
refreshPill();
setInterval(refreshPill, 15000);
