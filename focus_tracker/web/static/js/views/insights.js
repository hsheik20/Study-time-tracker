// AI Insights: weekly numbers (computed by the server) + a Claude-written report.

import { api } from "../api.js";
import { activityColor, duration, emptyState, esc, icon, plural, toast } from "../ui.js";

const LOADING_LINES = [
  "Reading your week…",
  "Looking for focus patterns…",
  "Weighing distractions and reflections…",
  "Drafting recommendations…",
];

// Matches the server's limits, so reports saved before they existed also stay short.
const LIMITS = { insights: 3, strengths: 2, improvements: 2, recommendations: 3 };

const minutes = (m) => duration(Math.round((m || 0) * 60));
const percent = (rate) => (rate == null ? "—" : `${Math.round(rate * 100)}%`);

// ---------- Numbers (no AI involved) ----------

function statTiles(m) {
  const t = m.totals;
  const tiles = [
    ["clock", "tint-violet", "Focused", minutes(t.focused_minutes), `${plural(t.sessions, "session")} · ${plural(t.days_active, "day")}`],
    ["check", "tint-green", "Completion", percent(t.completion_rate), `${t.completed_sessions} finished · ${t.ended_early_sessions} ended early`],
    ["timer", "tint-cyan", "Average session", minutes(t.avg_session_minutes), `longest ${minutes(t.longest_session_minutes)}`],
    ["alert", "tint-amber", "Distracted sessions", m.distractions.sessions_reporting_any,
      m.distractions.top[0] ? `most often: ${esc(m.distractions.top[0].distraction)}` : "none recorded"],
  ];
  return `<div class="grid stats-grid">${tiles.map(([i, tint, label, value, meta]) => `
    <div class="card stat hoverable ${tint}">
      <div class="stat-top"><span class="stat-label">${label}</span><span class="stat-icon">${icon(i)}</span></div>
      <div class="stat-value num">${value}</div>
      <div class="stat-meta">${meta}</div>
    </div>`).join("")}</div>`;
}

function patternBars(m) {
  const rows = (items, key) => {
    const max = Math.max(1, ...items.map((r) => r.focused_minutes));
    return items.slice(0, 5).map((r) => `
      <div class="breakdown-row" style="--c:${activityColor(r[key])}">
        <div class="breakdown-head">
          <span class="name"><span class="dot"></span><span>${esc(r[key])}</span></span>
          <span class="value num">${minutes(r.focused_minutes)} · ${r.completion_rate == null ? "untimed" : `${percent(r.completion_rate)} done`}</span>
        </div>
        <div class="progress thin"><span style="width:${(r.focused_minutes / max) * 100}%"></span></div>
      </div>`).join("");
  };
  const block = (title, iconName, items, key) => `
    <div class="card">
      <div class="card-header"><div class="card-title">${icon(iconName)}${title}</div></div>
      ${items.length ? `<div class="breakdown">${rows(items, key)}</div>` : `<p class="muted">No data yet.</p>`}
    </div>`;
  return `<div class="grid three-col section">
    ${block("By activity", "layers", m.by_activity, "activity")}
    ${block("By time of day", "clock", m.by_time_of_day, "time_of_day")}
    ${block("By location", "map-pin", m.by_location, "location")}
  </div>`;
}

// ---------- The Claude report ----------

function insightList(items, limit = LIMITS.insights) {
  return `<ul class="insight-list">${items.slice(0, limit).map((it) => `
    <li class="insight ${it.basis}">
      <span class="basis-chip ${it.basis}" title="${it.basis === "observation" ? "Directly shown by your data" : "A likely interpretation the data doesn't prove"}">
        ${it.basis === "observation" ? "Observed" : "Interpretation"}</span>
      <div><p>${esc(it.text)}</p><p class="evidence">${icon("trending")}${esc(it.evidence)}</p></div>
    </li>`).join("")}</ul>`;
}

function sectionCard(title, iconName, tint, section, delay) {
  return `
    <section class="card report-card ${tint}" style="animation-delay:${delay}ms">
      <div class="card-header"><div class="card-title"><span class="stat-icon">${icon(iconName)}</span>${title}</div></div>
      <p class="report-summary">${esc(section.summary)}</p>
      ${insightList(section.insights)}
    </section>`;
}

function reportHtml(report) {
  const generated = new Date(report.generated_at).toLocaleString([], {
    weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  const limited = report.data_limitations && !/^none\.?$/i.test(report.data_limitations.trim());
  return `
    <div class="report">
      <div class="card report-hero">
        <span class="chip soon">${icon("sparkles")}AI report</span>
        <h2>${esc(report.headline)}</h2>
        <p class="report-meta">Generated ${esc(generated)} · ${esc(report.model)} ·
          ${plural(report.sessions_analysed, "session")} analysed</p>
      </div>
      ${limited ? `<div class="notice limitation">${icon("alert")}<span><strong>About this data:</strong> ${esc(report.data_limitations)}</span></div>` : ""}
      <div class="grid report-grid">
        ${sectionCard("Weekly overview", "calendar", "tint-violet", report.overview, 0)}
        ${sectionCard("Focus patterns", "target", "tint-cyan", report.focus_patterns, 80)}
        ${sectionCard("Distraction analysis", "alert", "tint-amber", report.distraction_analysis, 160)}
        <section class="card report-card tint-green" style="animation-delay:240ms">
          <div class="card-header"><div class="card-title"><span class="stat-icon">${icon("check")}</span>Strengths &amp; improvements</div></div>
          <h4 class="sub-head good">What went well</h4>
          ${insightList(report.strengths, LIMITS.strengths)}
          <h4 class="sub-head grow">What could improve</h4>
          ${insightList(report.improvements, LIMITS.improvements)}
        </section>
      </div>
      <section class="card recommendations" style="animation-delay:320ms">
        <div class="card-header"><div class="card-title"><span class="stat-icon">${icon("zap")}</span>Recommendations for next week</div></div>
        <ol class="rec-list">${report.recommendations.slice(0, LIMITS.recommendations).map((r, i) => `
          <li class="rec">
            <span class="rec-num">${i + 1}</span>
            <div><h4>${esc(r.title)}</h4><p>${esc(r.action)}</p><p class="evidence">${icon("trending")}${esc(r.why)}</p></div>
          </li>`).join("")}</ol>
      </section>
    </div>`;
}

function loadingHtml() {
  return `
    <div class="card generating" role="status" aria-live="polite">
      <div class="orb">${icon("sparkles")}</div>
      <h3 id="loading-line">${LOADING_LINES[0]}</h3>
      <p class="muted">Claude is writing your report. This usually takes 20–40 seconds.</p>
      <div class="skeleton-lines wide"><span></span><span></span><span></span></div>
    </div>`;
}

// ---------- Page ----------

export async function render(container) {
  const state = { week: "current", data: null, busy: false, error: null };
  let loadingTimer = null;
  let cooldownTimer = null;

  const stopTimers = () => { clearInterval(loadingTimer); clearInterval(cooldownTimer); };

  const generateButton = () => {
    const { data } = state;
    const wait = data?.limits?.retry_after_seconds || 0;
    const noData = !data?.metrics.totals.sessions;
    const disabled = state.busy || !data?.configured || noData || wait > 0;
    const label = state.busy ? "Generating…" : data?.report ? "Regenerate insights" : "Generate Weekly Insights";
    return `<button class="button primary big" id="generate" ${disabled ? "disabled" : ""}>
      ${icon("sparkles")}${label}${wait > 0 && !state.busy ? ` <span class="wait">(${wait}s)</span>` : ""}</button>`;
  };

  const draw = () => {
    const { data } = state;
    const m = data.metrics;
    const noData = !m.totals.sessions;
    let body;
    if (state.busy) body = loadingHtml();
    else if (!data.configured) {
      body = `<div class="card">${emptyState({ iconName: "alert", title: "Connect your Claude API key",
        body: "Add <code>ANTHROPIC_API_KEY=…</code> to the <code>.env</code> file in the project folder, then restart <code>focus web</code>. The key stays on your computer and is never sent to the browser." })}</div>`;
    } else if (noData) {
      body = `<div class="card">${emptyState({ iconName: "timer", title: "No finished sessions this week",
        body: 'Insights need at least one completed or ended session. <a class="link-arrow" href="#/focus">Start a focus session</a>.' })}</div>`;
    } else if (data.report) body = reportHtml(data.report);
    else {
      body = `<div class="card">${emptyState({ iconName: "sparkles", title: "Your report is ready to generate",
        body: "Claude will read this week's numbers, notes and reflections and write a personal report with patterns and next steps." })}</div>`;
    }
    const errorHtml = state.error ? `<div class="notice error-notice">${icon("alert")}<span>${esc(state.error)}</span></div>` : "";
    const sample = m.data_quality.sample_sessions || 0;
    const sampleHtml = sample ? `<div class="notice limitation">${icon("alert")}<span><strong>Sample data:</strong>
      ${sample === m.totals.sessions ? "All" : sample} of this week's ${plural(m.totals.sessions, "session")}
      ${sample === 1 ? "is" : "are"} example data from the demo. The report will say so; add your own sessions to make it personal.</span></div>` : "";

    container.innerHTML = `
      <div class="insights-head">
        <div>
          <div class="segmented" role="tablist" aria-label="Week">
            <button role="tab" data-week="current" aria-selected="${state.week === "current"}">This week</button>
            <button role="tab" data-week="previous" aria-selected="${state.week === "previous"}">Last week</button>
          </div>
          <p class="muted week-label">${esc(m.week.label)}${m.week.in_progress ? ` · day ${m.week.days_elapsed} of 7` : ""}</p>
        </div>
        <div class="generate-wrap">
          ${generateButton()}
          <p class="muted limit-note">${data.configured ? `${data.limits.remaining_this_hour} reports left this hour · ${esc(data.model)}` : "Not connected"}</p>
        </div>
      </div>
      ${errorHtml}
      ${sampleHtml}
      ${noData ? "" : statTiles(m)}
      <div class="section">${body}</div>
      ${noData || state.busy ? "" : patternBars(m)}
      <p class="muted footnote">${icon("sparkles")}Numbers are calculated by Focus Tracker; Claude only interprets them.
        Reports are generated on demand and saved on this computer.</p>`;

    container.querySelector("#generate")?.addEventListener("click", generate);
    container.querySelectorAll("[data-week]").forEach((b) => b.addEventListener("click", () => {
      if (state.busy || b.dataset.week === state.week) return;
      state.week = b.dataset.week; state.error = null; load();
    }));
    if (state.busy) {
      let i = 0;
      loadingTimer = setInterval(() => {
        const line = container.querySelector("#loading-line");
        if (line) line.textContent = LOADING_LINES[++i % LOADING_LINES.length];
      }, 3500);
    }
    if (!state.busy && data.limits.retry_after_seconds > 0) {
      cooldownTimer = setInterval(() => {
        data.limits.retry_after_seconds = Math.max(0, data.limits.retry_after_seconds - 1);
        const button = container.querySelector("#generate");
        if (button) button.outerHTML = generateButton();
        container.querySelector("#generate")?.addEventListener("click", generate);
        if (!data.limits.retry_after_seconds) clearInterval(cooldownTimer);
      }, 1000);
    }
  };

  const load = async () => {
    stopTimers();
    state.data = await api.insights(state.week);
    draw();
  };

  async function generate() {
    if (state.busy) return;
    stopTimers();
    state.busy = true; state.error = null;
    draw();
    try {
      state.data = await api.generateInsights(state.week);
      toast("Your weekly insights are ready");
    } catch (err) {
      state.error = err.message;
      if (err.status !== 0) {
        try { state.data = await api.insights(state.week); } catch (_) {}
      }
      toast(err.message, "error");
    } finally {
      state.busy = false;
      stopTimers();
      draw();
    }
  }

  await load();
  return stopTimers;
}
