import { api } from "../api.js";
import { isSampleActivity } from "../demo.js";
import {
  activityColor, confirmDialog, duration, emptyState, esc, formDialog, icon, parseLocal, plural,
  relativeDay, sampleTag, toast,
} from "../ui.js";

function card(activity, total) {
  const color = activityColor(activity.name);
  const share = total ? Math.round((activity.focused_seconds / total) * 100) : 0;
  const average = activity.sessions ? activity.focused_seconds / activity.sessions : 0;
  const initial = [...activity.name.trim()][0]?.toUpperCase() || "?";
  return `
    <article class="card hoverable activity-card" style="--c:${color}">
      <div class="activity-top">
        <div class="avatar">${esc(initial)}</div>
        <div class="activity-name">
          <h3 title="${esc(activity.name)}">${esc(activity.name)}</h3>
          <div class="muted">${sampleTag(isSampleActivity(activity.name))} Last session: ${esc(relativeDay(parseLocal(activity.last_session)))}</div>
        </div>
        <div class="card-actions">
          <button class="icon-button small" data-rename="${esc(activity.name)}" title="Rename" aria-label="Rename ${esc(activity.name)}">${icon("pencil")}</button>
          <button class="icon-button small danger" data-delete="${esc(activity.name)}" title="Delete" aria-label="Delete ${esc(activity.name)}">${icon("trash")}</button>
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
      <a class="link-arrow" href="#/focus" data-start="${esc(activity.name)}">Focus on this ${icon("arrow")}</a>
    </article>`;
}

function nameDialog({ title, submitLabel, value = "", onSubmit }) {
  return formDialog({
    title, submitLabel,
    fields: `
      <label class="form-group"><span class="label">Name</span>
        <input class="input" name="name" maxlength="100" required autofocus value="${esc(value)}"
               placeholder="e.g. Studying, Guitar practice"></label>`,
    onSubmit: async (form) => {
      const name = (form.get("name") || "").trim();
      if (!name) throw new Error("Enter a name.");
      return onSubmit(name);
    },
  });
}

export async function render(container) {
  const draw = async () => {
    const { activities } = await api.activities();
    const total = activities.reduce((sum, a) => sum + a.focused_seconds, 0);
    container.innerHTML = `
      <div class="toolbar">
        <span class="toolbar-summary">${plural(activities.length, "activity", "activities")} · ${duration(total)} focused in total</span>
        <span class="spacer"></span>
        <button class="button primary" id="new-activity">${icon("plus")}New activity</button>
      </div>
      ${activities.length
        ? `<div class="grid cards-grid">${activities.map((a) => card(a, total)).join("")}</div>`
        : `<div class="card">${emptyState({ iconName: "layers", title: "No activities yet",
            body: "Create one to start tracking your focus, like Studying or Reading." })}</div>`}`;
    return activities;
  };

  let activities = await draw();

  container.addEventListener("click", async (e) => {
    const rename = e.target.closest("[data-rename]")?.dataset.rename;
    const remove = e.target.closest("[data-delete]")?.dataset.delete;
    const start = e.target.closest("[data-start]")?.dataset.start;
    if (start) {
      try { sessionStorage.setItem("focus-preselect", start); } catch (_) {}
      return; // the link itself navigates to the Focus page
    }
    if (e.target.closest("#new-activity")) {
      const name = await nameDialog({
        title: "New activity", submitLabel: "Create",
        onSubmit: async (value) => (await api.createActivity(value)).name,
      });
      if (name) { toast(`Created “${name}”`); activities = await draw(); }
    } else if (rename) {
      const name = await nameDialog({
        title: "Rename activity", submitLabel: "Rename", value: rename,
        onSubmit: async (value) => (await api.renameActivity(rename, value)).name,
      });
      if (name) { toast(`Renamed to “${name}”`); activities = await draw(); }
    } else if (remove) {
      const activity = activities.find((a) => a.name === remove);
      const count = activity?.sessions || 0;
      const ok = await confirmDialog({
        title: `Delete “${remove}”?`,
        body: count
          ? `This also deletes its <strong>${plural(count, "session")}</strong> (${duration(activity.focused_seconds)} of focus). This can't be undone.`
          : "It has no sessions yet.",
        confirmLabel: "Delete activity", danger: true,
      });
      if (!ok) return;
      try {
        await api.deleteActivity(remove);
        toast(`Deleted “${remove}”`);
        activities = await draw();
      } catch (err) { toast(err.message, "error"); }
    }
  });
}
