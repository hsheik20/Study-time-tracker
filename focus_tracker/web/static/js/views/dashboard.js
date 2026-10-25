import { api } from "../api.js";
import {
  activityColor, clock, duration, emptyState, esc, greeting, icon, parseLocal, plural,
  sameDay, sessionRow,
} from "../ui.js";

function statCard({ label, value, unit = "", meta, iconName, tint }) {
  return `
    <div class="card stat hoverable ${tint}">
      <div class="stat-top">
        <span class="stat-label">${esc(label)}</span>
        <span class="stat-icon">${icon(iconName)}</span>
      </div>
      <div class="stat-value num">${value}${unit ? `<small>${esc(unit)}</small>` : ""}</div>
      <div class="stat-meta">${meta}</div>
    </div>`;
}

function liveBanner(session) {
  if (!session) return "";
  const timed = session.target_seconds != null;
  return `
    <a class="live-banner" href="#/focus">
      <span class="pulse-dot${session.paused ? " paused" : ""}"></span>
      <div class="live-text">
        <strong>${session.paused ? "Paused" : "Focusing on"} ${esc(session.activity)}</strong>
        <div class="card-subtitle">${timed ? `${duration(session.target_seconds)} session · ${session.percent}% done` : "Open-ended session"}</div>
      </div>
      <span class="live-clock num">${timed ? clock(session.remaining_seconds) : clock(session.focused_seconds)}</span>
      <span class="link-arrow">View ${icon("arrow")}</span>
    </a>`;
}

function weekChart(days) {
  const now = new Date();
  const max = Math.max(...days.map((d) => d.focused_seconds), 1);
  const total = days.reduce((sum, d) => sum + d.focused_seconds, 0);
  const bars = days.map((day, i) => {
    const date = parseLocal(day.date);
    const today = sameDay(date, now);
    const height = day.focused_seconds ? Math.max(4, (day.focused_seconds / max) * 100) : 2;
    const label = date.toLocaleDateString([], { weekday: "short" });
    return `
      <div class="bar-col">
        <div class="bar-track">
          <div class="bar${today ? " today" : ""}${day.focused_seconds ? "" : " empty"}"
               style="height:${height}%; animation-delay:${i * 50}ms">
            <span class="bar-tip">${duration(day.focused_seconds)} · ${esc(date.toLocaleDateString([], { month: "short", day: "numeric" }))}</span>
          </div>
        </div>
        <span class="bar-label${today ? " today" : ""}">${esc(label)}</span>
      </div>`;
  }).join("");
  return `
    <div class="card">
      <div class="card-header">
        <div>
          <div class="card-title">${icon("calendar")}Last 7 days</div>
          <div class="card-subtitle">${duration(total)} focused · daily average ${duration(total / 7)}</div>
        </div>
      </div>
      <div class="bar-chart" role="img" aria-label="Focus time for each of the last 7 days">${bars}</div>
    </div>`;
}

function breakdown(byActivity) {
  const total = byActivity.reduce((sum, a) => sum + a.focused_seconds, 0);
  const rows = byActivity.slice(0, 5).map((a) => {
    const share = total ? Math.round((a.focused_seconds / total) * 100) : 0;
    return `
      <div class="breakdown-row" style="--c:${activityColor(a.name)}">
        <div class="breakdown-head">
          <span class="name"><span class="dot"></span><span>${esc(a.name)}</span></span>
          <span class="value num">${duration(a.focused_seconds)} · ${share}%</span>
        </div>
        <div class="progress thin"><span style="width:${share}%"></span></div>
      </div>`;
  }).join("");
  return `
    <div class="card">
      <div class="card-header">
        <div class="card-title">${icon("layers")}This week by activity</div>
      </div>
      ${rows ? `<div class="breakdown">${rows}</div>`
        : emptyState({ iconName: "layers", title: "No focus time this week",
                       body: "Finish a session and it will show up here." })}
    </div>`;
}

function recent(sessions) {
  return `
    <div class="card section">
      <div class="card-header">
        <div class="card-title">${icon("history")}Recent sessions</div>
        <a class="link-arrow" href="#/history">View all ${icon("arrow")}</a>
      </div>
      ${sessions.length ? `<div class="session-list">${sessions.map((s) => sessionRow(s)).join("")}</div>`
        : emptyState({ iconName: "timer", title: "No sessions yet",
                       body: 'Start your first one on the <a class="link-arrow" href="#/focus">Focus page</a>.' })}
    </div>`;
}

export async function render(container) {
  const data = await api.dashboard();
  const now = new Date();
  const dateText = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
  const { today, week, all_time: allTime } = data;

  container.innerHTML = `
    <section class="hero">
      <div>
        <h2>${esc(greeting(now))}, <span class="gradient-text">let's focus.</span></h2>
        <p>${esc(dateText)}</p>
      </div>
      ${data.active_session ? "" : `<a class="button primary big" href="#/focus">${icon("play")}Start focusing</a>`}
    </section>

    ${liveBanner(data.active_session)}

    <div class="grid stats-grid">
      ${statCard({ label: "Today", value: duration(today.focused_seconds), iconName: "clock", tint: "tint-violet",
                   meta: plural(today.sessions, "session") })}
      ${statCard({ label: "This week", value: duration(week.focused_seconds), iconName: "trending", tint: "tint-cyan",
                   meta: `${plural(week.sessions, "session")} · avg ${duration(week.average_seconds)}` })}
      ${statCard({ label: "Streak", value: data.streak_days, unit: data.streak_days === 1 ? "day" : "days",
                   iconName: "flame", tint: "tint-amber",
                   meta: data.streak_days ? "Keep it going!" : "Focus today to start one" })}
      ${statCard({ label: "All time", value: duration(allTime.focused_seconds), iconName: "target", tint: "tint-green",
                   meta: `${plural(allTime.sessions, "session")} · ${plural(data.activity_count, "activity", "activities")}` })}
    </div>

    <div class="grid split section">
      ${weekChart(data.last_7_days)}
      ${breakdown(week.by_activity)}
    </div>

    ${recent(data.recent_sessions)}
  `;
}
