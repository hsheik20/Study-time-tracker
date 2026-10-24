import { api } from "../api.js";
import { clock, duration, esc, icon, parseLocal, statusChip, timeOfDay } from "../ui.js";

const RADIUS = 110;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function ring(session) {
  return `
    <div class="ring">
      <svg viewBox="0 0 260 260" aria-hidden="true">
        <defs>
          <linearGradient id="ring-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="var(--accent)"/><stop offset="1" stop-color="var(--accent-2)"/>
          </linearGradient>
        </defs>
        <circle class="ring-bg" cx="130" cy="130" r="${RADIUS}"/>
        <circle class="ring-fg" id="ring-fg" cx="130" cy="130" r="${RADIUS}"
                stroke-dasharray="${CIRCUMFERENCE}" stroke-dashoffset="${CIRCUMFERENCE}"/>
      </svg>
      <div class="ring-center">
        <span class="ring-time num" id="ring-time">--:--</span>
        <span class="ring-caption" id="ring-caption">${session.target_seconds != null ? "remaining" : "elapsed"}</span>
      </div>
    </div>`;
}

function activeCard(session) {
  const started = timeOfDay(parseLocal(session.start));
  const length = session.target_seconds != null ? `${duration(session.target_seconds)} session` : "Open-ended session";
  return `
    <div class="card ring-card">
      ${ring(session)}
      <h3>${esc(session.activity)}</h3>
      <div class="meta">${esc(length)} · started ${esc(started)} · <span id="ring-status">${statusChip(session)}</span></div>
      ${session.note ? `<div class="meta">“${esc(session.note)}”</div>` : ""}
      <div class="notice">${icon("terminal")}
        <span>This session is running in your terminal. Pause, end or cancel it there with
        <code>P</code>, <code>E</code> or <code>C</code>. Browser controls arrive with the interactive timer.</span>
      </div>
    </div>`;
}

function idleCard(suggestedMinutes) {
  return `
    <div class="card ring-card">
      <div class="empty">
        <div class="empty-icon">${icon("timer")}</div>
        <h3>No session running</h3>
        <p>Start a focus session from your terminal and it will appear here live.</p>
      </div>
      <div class="kv" style="width:100%; max-width:420px">
        <div class="kv-row"><span>${icon("terminal")}Interactive menu</span><code>focus</code></div>
        <div class="kv-row"><span>${icon("zap")}Quick start</span><code>focus start studying -m ${suggestedMinutes}</code></div>
      </div>
      <div class="notice">${icon("sparkles")}
        <span><strong>Coming soon:</strong> start, pause and finish sessions right here with an interactive browser timer.</span>
      </div>
    </div>`;
}

function habitsCard(stats, suggestedMinutes) {
  const rate = stats.completion_rate == null ? "—" : `${Math.round(stats.completion_rate * 100)}%`;
  const rows = [
    ["check", "Completion rate", rate],
    ["timer", "Sessions this week", stats.sessions],
    ["clock", "Average session", duration(stats.average_seconds)],
    ["trending", "Longest session", duration(stats.longest_seconds)],
    ["target", "Usual session length", `${suggestedMinutes}m`],
    ["flame", "Current streak", `${stats.streak_days} day${stats.streak_days === 1 ? "" : "s"}`],
  ];
  return `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">${icon("zap")}Focus habits</div>
          <div class="card-subtitle">This week · timed sessions you finished vs. ended early</div>
        </div>
      </div>
      <div class="kv">
        ${rows.map(([i, label, value]) => `
          <div class="kv-row"><span>${icon(i)}${esc(label)}</span><strong class="num">${esc(value)}</strong></div>`).join("")}
      </div>
    </div>`;
}

export async function render(container) {
  const [{ session, suggested_minutes: suggested }, stats] =
    await Promise.all([api.activeSession(), api.stats("week")]);

  container.innerHTML = `
    <div class="focus-layout">
      ${session ? activeCard(session) : idleCard(suggested)}
      ${habitsCard(stats, suggested)}
    </div>`;
  if (!session) return;

  // Tick locally every second; re-sync with the server every 5 seconds so
  // pauses or a finish made in the terminal show up quickly.
  let current = session;
  let syncedAt = Date.now();

  const draw = () => {
    const elapsed = current.paused ? 0 : (Date.now() - syncedAt) / 1000;
    const timed = current.target_seconds != null;
    const focused = current.focused_seconds + elapsed;
    const value = timed ? Math.max(0, current.remaining_seconds - elapsed) : focused;
    const fraction = timed ? Math.min(1, focused / current.target_seconds) : 0;
    const timeEl = container.querySelector("#ring-time");
    if (!timeEl) return;
    timeEl.textContent = clock(value);
    container.querySelector("#ring-fg").style.strokeDashoffset = String(CIRCUMFERENCE * (1 - fraction));
    container.querySelector("#ring-caption").textContent =
      current.paused ? "paused" : timed ? "remaining" : "elapsed";
  };

  const sync = async () => {
    try {
      const fresh = (await api.activeSession()).session;
      if (!fresh || fresh.id !== current.id) {
        // Finished or replaced: re-route so the router cleans up these timers first.
        window.dispatchEvent(new HashChangeEvent("hashchange"));
        return;
      }
      current = fresh;
      syncedAt = Date.now();
      container.querySelector("#ring-status").innerHTML = statusChip(current);
    } catch (_) { /* keep ticking; try again next time */ }
  };

  draw();
  const tick = setInterval(draw, 1000);
  const poll = setInterval(sync, 5000);
  return () => { clearInterval(tick); clearInterval(poll); };
}
