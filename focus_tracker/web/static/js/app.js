// App shell: hash-based routing, theme toggle, and the "session running" pill.
// Each page lives in views/<name>.js and exports render(container) → optional cleanup fn.

import * as store from "./store.js";
import { esc, clock, duration, icon, toast } from "./ui.js";
import * as dashboard from "./views/dashboard.js";
import * as focus from "./views/focus.js";
import * as history from "./views/history.js";
import * as activities from "./views/activities.js";
import * as insights from "./views/insights.js";

const ROUTES = {
  dashboard: { view: dashboard, title: "Dashboard", subtitle: "Your focus at a glance" },
  focus: { view: focus, title: "Focus Sessions", subtitle: "Start, pause and finish your focus sessions" },
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

// ---------- Running-session pill (every page) ----------

const pill = document.getElementById("active-pill");
const onFocusPage = () => (location.hash.replace(/^#\/?/, "") || "dashboard") === "focus";

function drawPill() {
  const session = store.getSnapshot().session;
  if (!session || onFocusPage()) { pill.hidden = true; return; }
  const remaining = store.remainingSeconds(session);
  const time = remaining != null ? `${clock(remaining)} left` : clock(store.focusedSeconds(session));
  pill.className = `active-pill${session.paused ? " paused" : ""}`;
  pill.innerHTML = `<span class="pulse-dot${session.paused ? " paused" : ""}"></span>
    <span class="pill-text">${session.paused ? "Paused" : "Focusing"} · ${esc(session.activity)} · ${time}</span>`;
  pill.hidden = false;
}

store.subscribe((session, event) => {
  drawPill();
  // The Focus page shows its own celebration; elsewhere, a toast points to it.
  if (event?.type === "completed" && !onFocusPage()) {
    toast(`Session complete: ${duration(event.session.focused_seconds)} of ${event.session.activity}. Add a reflection on the Focus page.`);
  }
  // Pages showing totals re-render so the finished session is counted.
  if (["completed", "gone"].includes(event?.type) && !onFocusPage()) navigate();
});
setInterval(drawPill, 1000);

window.addEventListener("hashchange", () => { navigate(); drawPill(); });
store.startStore();
navigate();
