import { api } from "../api.js";
import { activityColor, duration, emptyState, esc, parseLocal, plural, relativeDay } from "../ui.js";

function card(activity, total) {
  const color = activityColor(activity.name);
  const share = total ? Math.round((activity.focused_seconds / total) * 100) : 0;
  const average = activity.sessions ? activity.focused_seconds / activity.sessions : 0;
  const initial = [...activity.name.trim()][0]?.toUpperCase() || "?";
  return `
    <article class="card hoverable activity-card" style="--c:${color}">
      <div class="activity-top">
        <div class="avatar">${esc(initial)}</div>
        <div style="min-width:0">
          <h3 title="${esc(activity.name)}">${esc(activity.name)}</h3>
          <div class="muted">Last session: ${esc(relativeDay(parseLocal(activity.last_session)))}</div>
        </div>
      </div>
      <div class="activity-stats">
        <div class="mini-stat"><span>Total focus</span><strong class="num">${duration(activity.focused_seconds)}</strong></div>
        <div class="mini-stat"><span>Sessions</span><strong class="num">${activity.sessions}</strong></div>
      </div>
      <div class="share">
        <div class="share-head"><span>${share}% of all focus time</span><span>avg ${duration(average)}</span></div>
        <div class="progress thin"><span style="width:${share}%"></span></div>
      </div>
    </article>`;
}

export async function render(container) {
  const { activities } = await api.activities();
  if (!activities.length) {
    container.innerHTML = `<div class="card">${emptyState({
      iconName: "layers", title: "No activities yet",
      body: "Create one by starting a session in the terminal: <code>focus start studying</code>.",
    })}</div>`;
    return;
  }
  const total = activities.reduce((sum, a) => sum + a.focused_seconds, 0);
  container.innerHTML = `
    <div class="toolbar">
      <span class="toolbar-summary">${plural(activities.length, "activity", "activities")} · ${duration(total)} focused in total</span>
    </div>
    <div class="grid cards-grid">${activities.map((a) => card(a, total)).join("")}</div>`;
}
