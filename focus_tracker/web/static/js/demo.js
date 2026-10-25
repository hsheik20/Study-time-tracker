// Public demo mode: the visitor's sessions, activities and AI reports live in
// this browser's localStorage. Every API call is sent to /api/demo together
// with that data; the server runs the normal route against it and returns any
// changes, which are saved here. Nothing is stored on the server.

import { ApiError } from "./api.js";

const KEYS = {
  data: "focus-demo-data",            // { activities, sessions } in the server's file format
  reports: "focus-demo-reports",      // saved AI reports by week
  sample: "focus-demo-sample-activities",
};
const memory = {}; // fallback when localStorage is unavailable (e.g. blocked cookies)

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (raw != null) return JSON.parse(raw);
  } catch (_) {}
  return key in memory ? memory[key] : fallback;
}

function write(key, value) {
  memory[key] = value;
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) {}
}

const tzOffset = () => new Date().getTimezoneOffset();

// ---------- Is this the demo? ----------

let enabledPromise = null;

/** Resolves to true when the server runs in demo mode (asked once). */
export function enabled() {
  enabledPromise ??= fetch("/api/health")
    .then((r) => r.json())
    .then((d) => Boolean(d.demo))
    .catch(() => { enabledPromise = null; return false; });
  return enabledPromise;
}

// ---------- Starter data ----------

let seeding = null;

function ensureData() {
  if (read(KEYS.data, null)) return Promise.resolve();
  seeding ??= fetch(`/api/demo/sample?tz_offset=${tzOffset()}`)
    .then((r) => {
      if (!r.ok) throw new ApiError("Couldn't load the sample data.", r.status);
      return r.json();
    })
    .then((sample) => {
      write(KEYS.data, sample.data);
      write(KEYS.sample, sample.sample_activities);
    })
    .catch((error) => {
      if (error instanceof ApiError) throw error;
      throw new ApiError("Can't reach the demo server. It may be waking up; try again in a moment.", 0);
    })
    .finally(() => { seeding = null; });
  return seeding;
}

// ---------- Requests ----------

// Requests run one at a time, so a slow read can never overwrite a newer change.
let queue = Promise.resolve();

function enqueue(task) {
  const result = queue.then(task, task);
  queue = result.catch(() => {});
  return result;
}

export function request(method, path, body) {
  const run = () => ensureData().then(() => send(method, path, body));
  // Writing a report takes ~30 s and doesn't change session data, so it
  // doesn't hold up the timer and other pages.
  if (method === "POST" && path === "/insights") return run();
  return enqueue(run);
}

async function send(method, path, body) {
  const [route, query = ""] = path.split("?");
  const envelope = {
    method, path: route, query, body: body ?? null,
    data: read(KEYS.data, null),
    tz_offset: tzOffset(),
  };
  if (route.startsWith("/insights")) envelope.reports = read(KEYS.reports, {});

  let response;
  try {
    response = await fetch("/api/demo", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(envelope),
    });
  } catch (_) {
    throw new ApiError("Can't reach the demo server. It may be waking up; try again in a moment.", 0);
  }
  let payload = null;
  try { payload = await response.json(); } catch (_) {}
  if (payload?.state) write(KEYS.data, payload.state);
  if (payload?.reports) write(KEYS.reports, payload.reports);
  if (!response.ok) {
    let detail = payload?.data?.detail || payload?.detail || `${response.status} ${response.statusText}`;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; ");
    throw new ApiError(detail, response.status);
  }
  return payload?.data ?? null;
}

// ---------- Sample data ----------

/** Activities that came with the demo (until the visitor renames them). */
export function isSampleActivity(name) {
  const key = String(name).toLowerCase();
  return read(KEYS.sample, []).some((n) => n.toLowerCase() === key);
}

export function sampleSessionCount() {
  return (read(KEYS.data, null)?.sessions || []).filter((s) => s.sample).length;
}

/** Delete the sample sessions, and sample activities that no longer have any. */
export function removeSampleData() {
  return enqueue(() => {
    const data = read(KEYS.data, { activities: [], sessions: [] });
    const sessions = (data.sessions || []).filter((s) => !s.sample);
    const used = new Set(sessions.map((s) => s.activity.toLowerCase()));
    const sampleNames = new Set(read(KEYS.sample, []).map((n) => n.toLowerCase()));
    const activities = (data.activities || []).filter(
      (a) => used.has(a.toLowerCase()) || !sampleNames.has(a.toLowerCase()));
    write(KEYS.data, { activities, sessions });
    write(KEYS.sample, []);
  });
}

/** Forget everything; the sample data is loaded again on the next request. */
export function resetDemo() {
  return enqueue(() => {
    for (const key of Object.values(KEYS)) {
      delete memory[key];
      try { localStorage.removeItem(key); } catch (_) {}
    }
    try { localStorage.removeItem("focus-pending-reflection"); } catch (_) {}
  });
}
