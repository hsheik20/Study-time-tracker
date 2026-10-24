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

export function sessionRow(session, { compact = false } = {}) {
  const color = activityColor(session.activity);
  if (compact) {
    return `
      <div class="session-row">
        <div class="activity"><span class="dot" style="--c:${color}"></span><span>${esc(session.activity)}</span></div>
        <div class="focused num">${duration(session.focused_seconds)}</div>
        ${statusChip(session)}
      </div>`;
  }
  return `
    <div class="session-row">
      <div class="time num">${esc(timeRange(session))}</div>
      <div class="activity"><span class="dot" style="--c:${color}"></span><span>${esc(session.activity)}</span></div>
      <div class="focused num">${duration(session.focused_seconds)}</div>
      ${statusChip(session)}
      <div class="note" title="${esc(session.note)}">${esc(session.note)}</div>
    </div>`;
}
