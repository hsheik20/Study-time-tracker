import { api } from "../api.js";
import {
  activityColor, bindReflection, confirmDialog, dayLabel, duration, emptyState, esc, formDialog,
  icon, localInputValue, parseLocal, plural, readReflection, reflectionFields, statusChip,
  timeRange, toast,
} from "../ui.js";

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

function detailsHtml(s) {
  const rows = [];
  if (s.target_seconds != null) rows.push(["target", "Planned", duration(s.target_seconds)]);
  if (s.location) rows.push(["map-pin", "Location", esc(s.location)]);
  if (s.pause_count) rows.push(["pause", "Pauses", `${s.pause_count} · ${duration(s.paused_seconds)}`]);
  if (s.note) rows.push(["message", "Note", esc(s.note)]);
  const distractions = s.distractions.length
    ? `<div class="detail-chips">${s.distractions.map((d) => `<span class="chip">${esc(d)}</span>`).join("")}</div>`
    : `<span class="muted">None recorded</span>`;
  return `
    <div class="session-details">
      <div class="detail-grid">
        ${rows.map(([i, label, value]) => `<div class="detail"><span>${icon(i)}${label}</span><strong>${value}</strong></div>`).join("")}
      </div>
      <div class="detail-block"><span class="detail-label">Distractions</span>${distractions}</div>
      <div class="detail-block"><span class="detail-label">Reflection</span>
        ${s.reflection ? `<p class="reflection-text">${esc(s.reflection)}</p>` : `<span class="muted">No reflection yet</span>`}
      </div>
      <div class="detail-actions">
        ${s.end ? `<button class="button small" data-reflect="${s.id}">${icon("pencil")}${s.reflection || s.distractions.length ? "Edit reflection" : "Add reflection"}</button>` : ""}
        ${s.end ? `<button class="button small danger-outline" data-delete="${s.id}">${icon("trash")}Delete session</button>`
                : `<a class="button small" href="#/focus">${icon("timer")}Open timer</a>`}
      </div>
    </div>`;
}

function rowHtml(s, open) {
  const hasDetails = s.reflection || s.distractions.length;
  return `
    <div class="history-item${open ? " open" : ""}" data-id="${s.id}">
      <button class="session-row clickable" data-toggle="${s.id}" aria-expanded="${open}">
        <span class="time num">${esc(timeRange(s))}</span>
        <span class="activity"><span class="dot" style="--c:${activityColor(s.activity)}"></span><span>${esc(s.activity)}</span></span>
        <span class="focused num">${duration(s.focused_seconds)}</span>
        ${statusChip(s)}
        <span class="note">
          ${s.location ? `<span class="row-tag">${icon("map-pin")}${esc(s.location)}</span>` : ""}
          ${hasDetails ? `<span class="row-tag accent">${icon("message")}Reflection</span>` : ""}
          <span class="note-text" title="${esc(s.note)}">${esc(s.note)}</span>
        </span>
        <span class="chevron">${icon("chevron")}</span>
      </button>
      ${open ? detailsHtml(s) : ""}
    </div>`;
}

function activityFieldHtml(activities) {
  return `
    <label class="form-group">
      <span class="label">Activity</span>
      <input class="input" name="activity" list="log-activities" maxlength="100" required
             placeholder="Pick or type an activity" value="${esc(activities[0]?.name || "")}">
      <datalist id="log-activities">${activities.map((a) => `<option value="${esc(a.name)}">`).join("")}</datalist>
    </label>`;
}

async function logSessionDialog(activities) {
  return formDialog({
    title: "Log a session",
    subtitle: "Forgot to start the timer? Add the session here.",
    submitLabel: "Log session",
    fields: `
      ${activityFieldHtml(activities)}
      <div class="form-row">
        <label class="form-group"><span class="label">Minutes focused</span>
          <input class="input" name="minutes" type="number" min="1" max="720" step="1" value="25" required></label>
        <label class="form-group"><span class="label">Ended at</span>
          <input class="input" name="ended_at" type="datetime-local" value="${localInputValue()}" max="${localInputValue()}" required></label>
      </div>
      <div class="form-row">
        <label class="form-group"><span class="label">Location <span class="optional">Optional</span></span>
          <input class="input" name="location" maxlength="100" placeholder="Home, library…"></label>
        <label class="form-group"><span class="label">Note <span class="optional">Optional</span></span>
          <input class="input" name="note" maxlength="500" placeholder="What did you work on?"></label>
      </div>`,
    onSubmit: async (form) => {
      const activity = (form.get("activity") || "").trim();
      const minutes = Number(form.get("minutes"));
      if (!activity) throw new Error("Enter an activity.");
      if (!(minutes >= 1 && minutes <= 720)) throw new Error("Minutes must be between 1 and 720.");
      if (!form.get("ended_at")) throw new Error("Choose when the session ended.");
      const { session } = await api.logSession({
        activity, minutes, ended_at: form.get("ended_at"),
        location: form.get("location").trim(), note: form.get("note").trim(),
      });
      return session;
    },
  });
}

function reflectionDialog(session) {
  return formDialog({
    title: "Reflection",
    subtitle: `${esc(session.activity)} · ${duration(session.focused_seconds)} · ${esc(timeRange(session))}`,
    fields: reflectionFields(session),
    submitLabel: "Save reflection",
    wide: true,
    onOpen: (dialog) => bindReflection(dialog),
    onSubmit: async (form) => (await api.updateSession(session.id, readReflection(form))).session,
  });
}

export async function render(container) {
  const state = { activity: "", query: "", pages: 1, open: new Set(), all: [], activities: [] };

  const load = async () => {
    const [{ activities }, { sessions }] = await Promise.all([api.activities(), api.sessions()]);
    state.activities = activities;
    state.all = sessions;
  };
  await load();

  container.innerHTML = `
    <div class="toolbar">
      <label class="field">${icon("layers")}
        <select id="filter-activity" aria-label="Filter by activity"></select>
      </label>
      <label class="field search">${icon("search")}
        <input id="filter-search" type="search" placeholder="Search sessions…" aria-label="Search sessions">
      </label>
      <span class="spacer"></span>
      <span class="toolbar-summary num" id="history-summary"></span>
      <button class="button primary" id="log-session">${icon("plus")}Log session</button>
    </div>
    <div class="card" id="history-body"></div>`;

  const body = container.querySelector("#history-body");
  const summary = container.querySelector("#history-summary");
  const select = container.querySelector("#filter-activity");

  const fillSelect = () => {
    if (state.activity && !state.activities.some((a) => a.name === state.activity)) state.activity = "";
    select.innerHTML = `<option value="">All activities</option>` + state.activities
      .map((a) => `<option value="${esc(a.name)}" ${a.name === state.activity ? "selected" : ""}>${esc(a.name)}</option>`).join("");
  };

  const draw = () => {
    const query = state.query.trim().toLowerCase();
    const sessions = state.all.filter((s) =>
      (!state.activity || s.activity === state.activity) &&
      (!query || [s.activity, s.note, s.location, s.reflection, ...s.distractions]
        .some((text) => text.toLowerCase().includes(query))));
    const focused = sessions.reduce((sum, s) => sum + s.focused_seconds, 0);
    summary.textContent = `${plural(sessions.length, "session")} · ${duration(focused)} focused`;

    if (!sessions.length) {
      body.innerHTML = state.all.length
        ? emptyState({ iconName: "search", title: "No matching sessions", body: "Try a different activity or search." })
        : emptyState({ iconName: "history", title: "No sessions yet",
                       body: "Start a focus session, or log one you forgot to track." });
      return;
    }
    const groups = groupByDay(sessions);
    const shown = groups.slice(0, state.pages * PAGE_DAYS);
    const now = new Date();
    body.innerHTML = shown.map((g) => {
      const { tag, name } = dayLabel(g.date, now);
      return `
        <section class="day-group">
          <div class="day-head">
            <h3>${tag ? `<em>${esc(tag)}</em>` : ""}${esc(name)}</h3>
            <span class="num">${plural(g.sessions.length, "session")} · ${duration(g.focused)} focused</span>
          </div>
          <div class="session-list">${g.sessions.map((s) => rowHtml(s, state.open.has(s.id))).join("")}</div>
        </section>`;
    }).join("") + (shown.length < groups.length
      ? `<div class="empty" style="padding:24px 0 4px"><button class="button" id="show-more">Show more</button></div>` : "");
  };

  const reload = async () => { await load(); fillSelect(); draw(); };

  body.addEventListener("click", async (e) => {
    const toggle = e.target.closest("[data-toggle]");
    const del = e.target.closest("[data-delete]");
    const reflect = e.target.closest("[data-reflect]");
    if (e.target.closest("#show-more")) { state.pages += 1; draw(); return; }
    if (toggle) {
      const id = Number(toggle.dataset.toggle);
      state.open.has(id) ? state.open.delete(id) : state.open.add(id);
      draw();
    } else if (del) {
      const session = state.all.find((s) => s.id === Number(del.dataset.delete));
      const ok = await confirmDialog({
        title: "Delete this session?",
        body: `<strong>${esc(session.activity)}</strong> · ${duration(session.focused_seconds)} · ${esc(timeRange(session))}<br>This can't be undone.`,
        confirmLabel: "Delete session", danger: true,
      });
      if (!ok) return;
      try {
        await api.deleteSession(session.id);
        state.open.delete(session.id);
        toast("Session deleted");
        await reload();
      } catch (err) { toast(err.message, "error"); }
    } else if (reflect) {
      const session = state.all.find((s) => s.id === Number(reflect.dataset.reflect));
      const saved = await reflectionDialog(session);
      if (saved) { toast("Reflection saved"); await reload(); }
    }
  });

  container.querySelector("#log-session").addEventListener("click", async () => {
    const session = await logSessionDialog(state.activities);
    if (session) {
      toast(`Logged ${duration(session.focused_seconds)} of ${session.activity}`);
      state.open.add(session.id);
      await reload();
    }
  });
  select.addEventListener("change", (e) => { state.activity = e.target.value; state.pages = 1; draw(); });
  container.querySelector("#filter-search").addEventListener("input", (e) => {
    state.query = e.target.value; state.pages = 1; draw();
  });

  fillSelect();
  draw();
}
