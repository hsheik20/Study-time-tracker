// Thin wrappers around the JSON API. Each view imports only what it needs.
// Errors carry the server's message (written for users), e.g. "Activity 'work' already exists."

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body) {
  const options = { method, headers: { Accept: "application/json" } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch (_) {
    throw new ApiError("Can't reach the Focus Tracker server. Is it still running?", 0);
  }
  if (response.status === 204) return null;
  let data = null;
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) {
    let detail = data?.detail || `${response.status} ${response.statusText}`;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; "); // validation errors
    throw new ApiError(detail, response.status);
  }
  return data;
}

const enc = encodeURIComponent;

export const api = {
  dashboard: () => request("GET", "/dashboard"),
  sessions: ({ activity, limit } = {}) => {
    const params = new URLSearchParams();
    if (activity) params.set("activity", activity);
    if (limit) params.set("limit", limit);
    const query = params.toString();
    return request("GET", `/sessions${query ? `?${query}` : ""}`);
  },
  session: (id) => request("GET", `/sessions/${id}`),
  logSession: (body) => request("POST", "/sessions", body),
  updateSession: (id, body) => request("PATCH", `/sessions/${id}`, body),
  deleteSession: (id) => request("DELETE", `/sessions/${id}`),

  activeSession: () => request("GET", "/sessions/active"),
  startSession: (body) => request("POST", "/sessions/active", body),
  pauseSession: () => request("POST", "/sessions/active/pause"),
  resumeSession: () => request("POST", "/sessions/active/resume"),
  stopSession: () => request("POST", "/sessions/active/stop"),
  cancelSession: () => request("POST", "/sessions/active/cancel"),

  activities: () => request("GET", "/activities"),
  createActivity: (name) => request("POST", "/activities", { name }),
  renameActivity: (name, newName) => request("PATCH", `/activities/${enc(name)}`, { name: newName }),
  deleteActivity: (name) => request("DELETE", `/activities/${enc(name)}`),

  stats: (period = "week") => request("GET", `/stats?period=${enc(period)}`),
  insights: (week = "current") => request("GET", `/insights?week=${enc(week)}`),
  generateInsights: (week = "current") => request("POST", "/insights", { week }),
};
