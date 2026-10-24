import { api } from "../api.js";
import { dayLabel, duration, emptyState, esc, icon, parseLocal, plural, sessionRow } from "../ui.js";

const PAGE_DAYS = 40; // day groups rendered at a time; "Show more" adds another page

function groupByDay(sessions) {
  const groups = [];
  for (const session of sessions) {
    const date = parseLocal(session.start);
    const key = date.toDateString();
    let group = groups[groups.length - 1];
    if (!group || group.key !== key) {
      group = { key, date, sessions: [], focused: 0 };
      groups.push(group);
    }
    group.sessions.push(session);
    group.focused += session.focused_seconds;
  }
  return groups;
}

function dayGroup(group, now) {
  const { tag, name } = dayLabel(group.date, now);
  return `
    <section class="day-group">
      <div class="day-head">
        <h3>${tag ? `<em>${esc(tag)}</em>` : ""}${esc(name)}</h3>
        <span class="num">${plural(group.sessions.length, "session")} · ${duration(group.focused)} focused</span>
      </div>
      <div class="session-list">${group.sessions.map((s) => sessionRow(s)).join("")}</div>
    </section>`;
}

export async function render(container) {
  const [{ activities }, all] = await Promise.all([api.activities(), api.sessions()]);
  const state = { activity: "", query: "", pages: 1 };

  container.innerHTML = `
    <div class="toolbar">
      <label class="field">${icon("layers")}
        <select id="filter-activity" aria-label="Filter by activity">
          <option value="">All activities</option>
          ${activities.map((a) => `<option value="${esc(a.name)}">${esc(a.name)}</option>`).join("")}
        </select>
      </label>
      <label class="field search">${icon("search")}
        <input id="filter-search" type="search" placeholder="Search notes or activities" aria-label="Search sessions">
      </label>
      <span class="spacer"></span>
      <span class="toolbar-summary num" id="history-summary"></span>
    </div>
    <div class="card" id="history-body"></div>`;

  const body = container.querySelector("#history-body");
  const summary = container.querySelector("#history-summary");

  const draw = () => {
    const query = state.query.trim().toLowerCase();
    const sessions = all.sessions.filter((s) =>
      (!state.activity || s.activity === state.activity) &&
      (!query || s.activity.toLowerCase().includes(query) || s.note.toLowerCase().includes(query)));
    const focused = sessions.reduce((sum, s) => sum + s.focused_seconds, 0);
    summary.textContent = `${plural(sessions.length, "session")} · ${duration(focused)} focused`;

    if (!sessions.length) {
      body.innerHTML = all.sessions.length
        ? emptyState({ iconName: "search", title: "No matching sessions", body: "Try a different activity or search." })
        : emptyState({ iconName: "history", title: "No sessions yet",
                       body: "Sessions you track in the terminal will show up here." });
      return;
    }
    const groups = groupByDay(sessions);
    const shown = groups.slice(0, state.pages * PAGE_DAYS);
    const now = new Date();
    body.innerHTML = shown.map((g) => dayGroup(g, now)).join("") + (shown.length < groups.length
      ? `<div class="empty" style="padding:24px 0 4px"><button class="button" id="show-more">Show more</button></div>`
      : "");
    body.querySelector("#show-more")?.addEventListener("click", () => { state.pages += 1; draw(); });
  };

  container.querySelector("#filter-activity").addEventListener("change", (e) => {
    state.activity = e.target.value; state.pages = 1; draw();
  });
  container.querySelector("#filter-search").addEventListener("input", (e) => {
    state.query = e.target.value; state.pages = 1; draw();
  });
  draw();
}
