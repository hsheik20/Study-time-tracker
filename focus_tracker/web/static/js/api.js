// Thin wrappers around the JSON API. Each view imports only what it needs.

async function get(path) {
  const response = await fetch(`/api${path}`, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return response.json();
}

export const api = {
  dashboard: () => get("/dashboard"),
  sessions: ({ activity, limit } = {}) => {
    const params = new URLSearchParams();
    if (activity) params.set("activity", activity);
    if (limit) params.set("limit", limit);
    const query = params.toString();
    return get(`/sessions${query ? `?${query}` : ""}`);
  },
  activeSession: () => get("/sessions/active"),
  activities: () => get("/activities"),
  stats: (period = "week") => get(`/stats?period=${encodeURIComponent(period)}`),
  insights: () => get("/insights"),
};
