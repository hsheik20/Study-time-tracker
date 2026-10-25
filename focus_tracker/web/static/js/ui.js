// Shared formatting and small UI building blocks.

/** Escape text for safe insertion into HTML (activity names and notes are user input). */
export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[ch]);
}

export const icon = (name, cls = "") => `<svg class="icon ${cls}"><use href="#i-${name}"/></svg>`;

/** "1h 05m", "45m", "5m 03s", "42s": the same style as the terminal app. */
export function duration(totalSeconds) {
  const total = Math.max(0, Math.floor(totalSeconds || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m) return m < 10 && s ? `${m}m ${String(s).padStart(2, "0")}s` : `${m}m`;
  return `${s}s`;
}

/** Timer display: "04:05" or "1:02:03". */
export function clock(totalSeconds) {
  const total = Math.max(0, Math.ceil(totalSeconds || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mmss = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return h ? `${h}:${mmss}` : mmss;
}

/** Parse the API's local ISO times ("2026-10-22T09:00:00") or dates ("2026-10-22"). */
export function parseLocal(value) {
  if (!value) return null;
  const [datePart, timePart = "00:00:00"] = value.split("T");
  const [y, mo, d] = datePart.split("-").map(Number);
  const [h, mi, s] = timePart.split(":").map(Number);
  return new Date(y, mo - 1, d, h || 0, mi || 0, s || 0);
}

export const timeOfDay = (date) =>
  date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

export function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export function dayLabel(date, now = new Date()) {
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
  const name = date.toLocaleDateString([], {
    weekday: "short", month: "short", day: "numeric",
    ...(date.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}),
  });
  if (sameDay(date, now)) return { tag: "Today", name };
  if (sameDay(date, yesterday)) return { tag: "Yesterday", name };
  return { tag: "", name };
}

export function relativeDay(date, now = new Date()) {
  if (!date) return "Never";
  const start = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((start(now) - start(date)) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function greeting(now = new Date()) {
  const h = now.getHours();
  if (h < 5) return "Burning the midnight oil";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

const STATUS_LABELS = {
  completed: "Completed", running: "Running", paused: "Paused", untimed: "Untimed",
};

export function statusChip(session) {
  const label = session.status === "ended_early"
    ? `Ended at ${Math.min(99, session.percent ?? 0)}%`
    : STATUS_LABELS[session.status] || session.status;
  return `<span class="chip ${esc(session.status)}">${esc(label)}</span>`;
}

// A stable color per activity name, so an activity looks the same everywhere.
const PALETTE = ["#8b5cf6", "#22d3ee", "#f472b6", "#fbbf24", "#34d399", "#60a5fa", "#fb923c", "#a78bfa"];

export function activityColor(name) {
  let hash = 0;
  for (const ch of String(name).toLowerCase()) hash = (hash * 31 + ch.codePointAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

export const plural = (n, word, many = `${word}s`) => `${n} ${n === 1 ? word : many}`;

export function emptyState({ iconName = "clock", title, body = "" }) {
  return `
    <div class="empty">
      <div class="empty-icon">${icon(iconName)}</div>
      <h3>${esc(title)}</h3>
      ${body ? `<p>${body}</p>` : ""}
    </div>`;
}

/** Time range for a session row, e.g. "09:00 – 09:50" or "09:00 – now". */
export function timeRange(session) {
  const start = timeOfDay(parseLocal(session.start));
  return `${start} – ${session.end ? timeOfDay(parseLocal(session.end)) : "now"}`;
}

/** Marks example data preloaded in the public demo. */
export const sampleTag = (isSample) => (isSample
  ? '<span class="row-tag sample" title="Example data that came with the demo">Sample</span>' : "");

export function sessionRow(session, { compact = false } = {}) {
  const color = activityColor(session.activity);
  if (compact) {
    return `
      <div class="session-row">
        <div class="activity"><span class="dot" style="--c:${color}"></span><span>${esc(session.activity)}</span>${sampleTag(session.sample)}</div>
        <div class="focused num">${duration(session.focused_seconds)}</div>
        ${statusChip(session)}
      </div>`;
  }
  return `
    <div class="session-row">
      <div class="time num">${esc(timeRange(session))}</div>
      <div class="activity"><span class="dot" style="--c:${color}"></span><span>${esc(session.activity)}</span>${sampleTag(session.sample)}</div>
      <div class="focused num">${duration(session.focused_seconds)}</div>
      ${statusChip(session)}
      <div class="note" title="${esc(session.note)}">${esc(session.note)}</div>
    </div>`;
}

// ---------- Toasts ----------

/** Brief feedback in the corner. type: "success" | "error" | "info". */
export function toast(message, type = "success") {
  let host = document.getElementById("toasts");
  if (!host) {
    host = document.createElement("div");
    host.id = "toasts";
    host.className = "toasts";
    host.setAttribute("role", "status");
    host.setAttribute("aria-live", "polite");
    document.body.append(host);
  }
  const iconName = { success: "check", error: "alert", info: "sparkles" }[type] || "check";
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `${icon(iconName)}<span>${esc(message)}</span>`;
  host.append(el);
  setTimeout(() => {
    el.classList.add("leaving");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, type === "error" ? 5000 : 3200);
}

// ---------- Dialogs ----------

function openDialog(html, { onSubmit, onOpen, wide = false } = {}) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = `dialog${wide ? " wide" : ""}`;
    dialog.innerHTML = html;
    document.body.append(dialog);
    const form = dialog.querySelector("form");
    const errorEl = dialog.querySelector(".form-error");
    let result = null;

    dialog.addEventListener("close", () => { dialog.remove(); resolve(result); });
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); }); // backdrop
    dialog.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => dialog.close()));
    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const submit = form.querySelector("[type=submit]");
      submit.disabled = true;
      if (errorEl) errorEl.textContent = "";
      try {
        result = onSubmit ? await onSubmit(new FormData(form), dialog) : true;
        dialog.close();
      } catch (error) {
        if (errorEl) errorEl.textContent = error.message;
        else toast(error.message, "error");
        submit.disabled = false;
      }
    });
    dialog.showModal();
    onOpen?.(dialog);
    dialog.querySelector("[autofocus]")?.focus();
  });
}

/** Ask a yes/no question. Resolves true if confirmed. */
export async function confirmDialog({ title, body = "", confirmLabel = "Confirm", danger = false }) {
  const result = await openDialog(`
    <form method="dialog">
      <h2>${esc(title)}</h2>
      ${body ? `<p class="dialog-body">${body}</p>` : ""}
      <div class="dialog-actions">
        <button type="button" class="button" data-close>Keep it</button>
        <button type="submit" class="button ${danger ? "danger" : "primary"}" autofocus>${esc(confirmLabel)}</button>
      </div>
    </form>`);
  return result === true;
}

/** A dialog with form fields; `onSubmit(formData)` may throw to show an error and stay open. */
export function formDialog({ title, subtitle = "", fields, submitLabel = "Save", onSubmit, onOpen, wide = false }) {
  return openDialog(`
    <form novalidate>
      <h2>${esc(title)}</h2>
      ${subtitle ? `<p class="dialog-body">${subtitle}</p>` : ""}
      <div class="form-fields">${fields}</div>
      <p class="form-error" role="alert"></p>
      <div class="dialog-actions">
        <button type="button" class="button" data-close>Cancel</button>
        <button type="submit" class="button primary">${esc(submitLabel)}</button>
      </div>
    </form>`, { onSubmit, onOpen, wide });
}

// ---------- Reflection form (used after a session and from History) ----------

export const DISTRACTIONS = [
  "Phone", "Social media", "Notifications", "Noise", "People",
  "Wandering thoughts", "Tiredness", "Hunger",
];

/** HTML for distraction chips + reflection text. Read it back with readReflection(). */
export function reflectionFields(session = {}) {
  const chosen = new Set((session.distractions || []).map((d) => d.toLowerCase()));
  const extra = (session.distractions || []).filter(
    (d) => !DISTRACTIONS.some((x) => x.toLowerCase() === d.toLowerCase()));
  const chip = (label) => `
    <label class="toggle-chip">
      <input type="checkbox" name="distraction" value="${esc(label)}" ${chosen.has(label.toLowerCase()) ? "checked" : ""}>
      <span>${esc(label)}</span>
    </label>`;
  return `
    <fieldset class="form-group">
      <legend>What distracted you? <span class="optional">Pick any</span></legend>
      <div class="chip-picker" data-chips>${[...DISTRACTIONS, ...extra].map(chip).join("")}</div>
      <div class="add-row">
        <input class="input" type="text" data-new-distraction maxlength="100" placeholder="Something else…" aria-label="Add another distraction">
        <button type="button" class="button small" data-add-distraction>${icon("plus")}Add</button>
      </div>
    </fieldset>
    <label class="form-group">
      <span class="label">Reflection <span class="optional">Optional</span></span>
      <textarea class="input" name="reflection" rows="4" maxlength="2000"
        placeholder="What went well? What did you struggle with?">${esc(session.reflection || "")}</textarea>
    </label>`;
}

/** Wire up the "Add" button for custom distractions inside `root`. */
export function bindReflection(root) {
  const input = root.querySelector("[data-new-distraction]");
  const add = () => {
    const value = input.value.trim();
    if (!value) return;
    const chips = root.querySelector("[data-chips]");
    const existing = [...chips.querySelectorAll("input")].find((c) => c.value.toLowerCase() === value.toLowerCase());
    if (existing) { existing.checked = true; }
    else {
      chips.insertAdjacentHTML("beforeend", `
        <label class="toggle-chip"><input type="checkbox" name="distraction" value="${esc(value)}" checked><span>${esc(value)}</span></label>`);
    }
    input.value = "";
    input.focus();
  };
  root.querySelector("[data-add-distraction]").addEventListener("click", add);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); add(); } });
}

export function readReflection(formData) {
  return {
    distractions: formData.getAll("distraction"),
    reflection: (formData.get("reflection") || "").trim(),
  };
}

/** Local "YYYY-MM-DDTHH:MM" for <input type="datetime-local">. */
export function localInputValue(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
