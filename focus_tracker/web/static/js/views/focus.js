// The interactive focus timer: set up → live countdown → reflection.

import { api } from "../api.js";
import { setSoundEnabled, soundEnabled, unlockAudio } from "../sound.js";
import * as store from "../store.js";
import {
  activityColor, bindReflection, clock, confirmDialog, duration, esc, icon, parseLocal,
  readReflection, reflectionFields, statusChip, timeOfDay, toast,
} from "../ui.js";

const PRESETS = [15, 25, 45, 50, 60, 90];
const LOCATION_IDEAS = ["Home", "Library", "Café", "Office", "Campus"];
const RADIUS = 130;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// ---------- Setup ----------

function takePreselected() {
  try {
    const name = sessionStorage.getItem("focus-preselect");
    sessionStorage.removeItem("focus-preselect");
    return name;
  } catch (_) { return null; }
}

function setupView({ activities, suggested, locations }) {
  const preselected = takePreselected();
  const selected = activities.some((a) => a.name === preselected) ? preselected : activities[0]?.name;
  const minutes = PRESETS.includes(suggested) ? suggested : 25;
  const custom = PRESETS.includes(suggested) ? "" : suggested;
  const places = [...new Set([...locations, ...LOCATION_IDEAS])].slice(0, 8);
  const activityChips = activities.map((a) => `
    <label class="toggle-chip activity-choice" style="--c:${activityColor(a.name)}">
      <input type="radio" name="activity" value="${esc(a.name)}" ${a.name === selected ? "checked" : ""}>
      <span><span class="dot"></span>${esc(a.name)}</span>
    </label>`).join("");
  return `
    <form class="card stage setup" id="setup-form" novalidate>
      <div class="stage-head">
        <div>
          <h2>Start a focus session</h2>
          <p class="card-subtitle">Pick what you're working on and how long you want to focus.</p>
        </div>
        <label class="switch" title="Play a chime when a session completes">
          <input type="checkbox" id="sound-toggle" ${soundEnabled() ? "checked" : ""}>
          <span class="switch-track"><span class="switch-thumb"></span></span>
          <span class="switch-label">${icon("volume")}Sound</span>
        </label>
      </div>

      <fieldset class="form-group">
        <legend>Activity</legend>
        <div class="chip-picker">
          ${activityChips}
          <label class="toggle-chip new-choice">
            <input type="radio" name="activity" value="__new__" ${activities.length ? "" : "checked"}>
            <span>${icon("plus")}New activity</span>
          </label>
        </div>
        <input class="input" id="new-activity" type="text" maxlength="100"
               placeholder="Name your new activity, e.g. Studying" ${activities.length ? "hidden" : ""}>
      </fieldset>

      <fieldset class="form-group">
        <legend>Duration</legend>
        <div class="chip-picker">
          ${PRESETS.map((m) => `
            <label class="toggle-chip">
              <input type="radio" name="preset" value="${m}" ${!custom && m === minutes ? "checked" : ""}>
              <span>${m} min</span>
            </label>`).join("")}
          <label class="custom-minutes ${custom ? "active" : ""}">
            <input class="input" id="custom-minutes" type="number" min="1" max="720" step="1"
                   value="${esc(custom)}" placeholder="Custom" aria-label="Custom minutes">
            <span>min</span>
          </label>
        </div>
      </fieldset>

      <div class="form-row">
        <label class="form-group">
          <span class="label">${icon("map-pin")}Location <span class="optional">Optional</span></span>
          <input class="input" name="location" list="location-ideas" maxlength="100" placeholder="Where are you?">
          <datalist id="location-ideas">${places.map((p) => `<option value="${esc(p)}">`).join("")}</datalist>
        </label>
        <label class="form-group">
          <span class="label">${icon("message")}Note <span class="optional">Optional</span></span>
          <input class="input" name="note" maxlength="500" placeholder="What are you working on?">
        </label>
      </div>

      <p class="form-error" role="alert"></p>
      <button class="button primary big" type="submit">${icon("play")}Start focusing</button>
    </form>`;
}

function bindSetup(stage) {
  const form = stage.querySelector("#setup-form");
  const newInput = form.querySelector("#new-activity");
  const custom = form.querySelector("#custom-minutes");
  const error = form.querySelector(".form-error");

  form.addEventListener("change", (e) => {
    if (e.target.name === "activity") {
      newInput.hidden = e.target.value !== "__new__";
      if (!newInput.hidden) newInput.focus();
    }
    if (e.target.name === "preset") { custom.value = ""; custom.parentElement.classList.remove("active"); }
  });
  custom.addEventListener("input", () => {
    const active = custom.value !== "";
    custom.parentElement.classList.toggle("active", active);
    if (active) form.querySelectorAll("[name=preset]").forEach((r) => { r.checked = false; });
  });
  form.querySelector("#sound-toggle").addEventListener("change", (e) => {
    setSoundEnabled(e.target.checked);
    if (e.target.checked) unlockAudio();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    error.textContent = "";
    const data = new FormData(form);
    const choice = data.get("activity");
    const activity = choice === "__new__" ? newInput.value.trim() : choice;
    const minutes = custom.value ? Number(custom.value) : Number(data.get("preset"));
    if (!activity) { error.textContent = "Choose an activity or name a new one."; newInput.focus(); return; }
    if (!minutes || minutes < 1 || minutes > 720) {
      error.textContent = "Choose a duration between 1 and 720 minutes."; custom.focus(); return;
    }
    unlockAudio(); // this click lets the completion chime play later
    const button = form.querySelector("[type=submit]");
    button.disabled = true;
    try {
      await store.start({ activity, minutes, location: data.get("location").trim(), note: data.get("note").trim() });
      toast(`Focus session started: ${minutes} min of ${activity}`);
    } catch (err) {
      error.textContent = err.message;
      button.disabled = false;
    }
  });
}

// ---------- Live timer ----------

function liveView(session) {
  return `
    <div class="card stage live" id="live">
      <div class="live-head">
        <span class="live-activity"><span class="dot" style="--c:${activityColor(session.activity)}"></span>${esc(session.activity)}</span>
        <span id="live-status">${statusChip(session)}</span>
      </div>
      <div class="ring big-ring" id="ring">
        <svg viewBox="0 0 300 300" aria-hidden="true">
          <defs>
            <linearGradient id="ring-gradient" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stop-color="var(--accent)"/><stop offset="1" stop-color="var(--accent-2)"/>
            </linearGradient>
          </defs>
          <circle class="ring-bg" cx="150" cy="150" r="${RADIUS}"/>
          <circle class="ring-fg" id="ring-fg" cx="150" cy="150" r="${RADIUS}"
                  stroke-dasharray="${CIRCUMFERENCE}" stroke-dashoffset="${CIRCUMFERENCE}"/>
        </svg>
        <div class="ring-center">
          <span class="ring-time num" id="ring-time" aria-live="off">--:--</span>
          <span class="ring-caption" id="ring-caption"></span>
        </div>
      </div>
      <div class="live-meta" id="live-meta"></div>
      <div class="controls" id="controls"></div>
      <p class="shortcuts">Shortcuts: <kbd>Space</kbd> pause/resume · <kbd>E</kbd> end early · <kbd>C</kbd> cancel</p>
    </div>`;
}

function controlsHtml(session) {
  return `
    <button class="button primary big" data-action="${session.paused ? "resume" : "pause"}">
      ${icon(session.paused ? "play" : "pause")}${session.paused ? "Resume" : "Pause"}
    </button>
    <button class="button big" data-action="stop">${icon("flag")}End early</button>
    <button class="button big ghost-danger" data-action="cancel">${icon("x")}Cancel</button>`;
}

function metaHtml(session) {
  const parts = [`Started ${esc(timeOfDay(parseLocal(session.start)))}`];
  if (session.location) parts.push(`${icon("map-pin")}${esc(session.location)}`);
  if (session.pause_count) parts.push(`${session.pause_count} pause${session.pause_count === 1 ? "" : "s"} · ${duration(session.paused_seconds)} paused`);
  const note = session.note ? `<div class="live-note">“${esc(session.note)}”</div>` : "";
  return `<div class="meta-row">${parts.map((p) => `<span>${p}</span>`).join("")}</div>${note}`;
}

// ---------- Finished + reflection ----------

const FINISH_COPY = {
  completed: ["Session complete!", "Great work. Keep it going!"],
  ended: ["Session ended", "Every minute counts. Nice effort."],
  elsewhere: ["Session finished", "It was finished from the terminal or another tab."],
};

function finishedView(session, kind) {
  const [title, line] = FINISH_COPY[kind] || FINISH_COPY.ended;
  return `
    <form class="card stage finished" id="reflect-form" novalidate>
      <div class="celebrate ${kind === "completed" ? "success" : ""}">
        <div class="celebrate-icon">${icon(kind === "completed" ? "check" : "flag")}</div>
        <h2>${esc(title)}</h2>
        <p>${esc(line)}</p>
        <div class="summary-chips">
          <span class="chip completed">${duration(session.focused_seconds)} focused</span>
          <span class="chip"><span class="dot" style="--c:${activityColor(session.activity)}"></span>${esc(session.activity)}</span>
          ${session.location ? `<span class="chip">${esc(session.location)}</span>` : ""}
        </div>
      </div>
      <div class="reflect">
        <h3>How did it go?</h3>
        <p class="card-subtitle">A quick note helps you spot patterns, and will power your weekly AI insights.</p>
        ${reflectionFields(session)}
      </div>
      <p class="form-error" role="alert"></p>
      <div class="dialog-actions">
        <button type="button" class="button" data-skip>Skip</button>
        <button type="submit" class="button primary">${icon("check")}Save reflection</button>
      </div>
    </form>`;
}

// ---------- Side panel ----------

function sidePanel(stats, dashboard) {
  const rate = stats.completion_rate == null ? "—" : `${Math.round(stats.completion_rate * 100)}%`;
  const rows = [
    ["clock", "Focused today", duration(dashboard.today.focused_seconds)],
    ["timer", "Sessions today", dashboard.today.sessions],
    ["flame", "Current streak", `${stats.streak_days} day${stats.streak_days === 1 ? "" : "s"}`],
    ["check", "Completion rate (week)", rate],
    ["trending", "Average session (week)", duration(stats.average_seconds)],
  ];
  return `
    <div class="card">
      <div class="card-header"><div class="card-title">${icon("zap")}Your focus</div></div>
      <div class="kv">${rows.map(([i, label, value]) => `
        <div class="kv-row"><span>${icon(i)}${esc(label)}</span><strong class="num">${esc(value)}</strong></div>`).join("")}
      </div>
    </div>`;
}

// ---------- Page ----------

export async function render(container) {
  container.innerHTML = `
    <div class="focus-layout">
      <div id="stage"></div>
      <aside id="side"><div class="skeleton"></div></aside>
    </div>`;
  const stage = container.querySelector("#stage");
  const side = container.querySelector("#side");
  let mode = null;          // "setup" | "live" | "finished"
  let liveId = null;
  let frame = null;
  let busy = false;

  const refreshSide = async () => {
    try {
      const [stats, dashboard] = await Promise.all([api.stats("week"), api.dashboard()]);
      side.innerHTML = sidePanel(stats, dashboard);
    } catch (_) { /* side panel is optional */ }
  };

  const showSetup = async () => {
    mode = "setup"; liveId = null; stopFrames();
    const [{ activities }, snap] = [await api.activities(), store.getSnapshot()];
    if (mode !== "setup") return; // something else happened meanwhile
    stage.innerHTML = setupView({ activities, suggested: snap.suggested_minutes, locations: snap.recent_locations || [] });
    bindSetup(stage);
  };

  const showFinished = (session, kind) => {
    mode = "finished"; liveId = null; stopFrames();
    stage.innerHTML = finishedView(session, kind);
    const form = stage.querySelector("#reflect-form");
    bindReflection(form);
    const done = () => { store.setPendingReflection(null); showSetup(); refreshSide(); };
    form.querySelector("[data-skip]").addEventListener("click", done);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const button = form.querySelector("[type=submit]");
      button.disabled = true;
      try {
        await api.updateSession(session.id, readReflection(new FormData(form)));
        toast("Reflection saved");
        done();
      } catch (err) {
        form.querySelector(".form-error").textContent = err.message;
        button.disabled = false;
      }
    });
    refreshSide();
  };

  // Smooth ring + countdown, redrawn every animation frame while visible.
  const draw = () => {
    const session = store.getSnapshot().session;
    if (mode !== "live" || !session) return;
    const timed = session.target_seconds != null;
    const value = timed ? store.remainingSeconds(session) : store.focusedSeconds(session);
    const fraction = timed ? store.progress(session) : (store.focusedSeconds(session) % 3600) / 3600;
    stage.querySelector("#ring-time").textContent = clock(value);
    stage.querySelector("#ring-fg").style.strokeDashoffset = String(CIRCUMFERENCE * (1 - fraction));
    stage.querySelector("#ring-caption").textContent = session.paused ? "Paused"
      : timed ? `remaining of ${duration(session.target_seconds)}` : "elapsed";
    document.title = `${clock(value)} · ${session.activity} · Focus Tracker`;
    frame = requestAnimationFrame(draw);
  };
  const stopFrames = () => { if (frame) cancelAnimationFrame(frame); frame = null; };

  const showLive = (session) => {
    if (mode !== "live" || liveId !== session.id) {
      mode = "live"; liveId = session.id;
      stage.innerHTML = liveView(session);
      stage.querySelector("#controls").addEventListener("click", (e) => {
        const action = e.target.closest("[data-action]")?.dataset.action;
        if (action) act(action);
      });
    }
    stage.querySelector("#live").classList.toggle("is-paused", session.paused);
    stage.querySelector("#live-status").innerHTML = statusChip(session);
    stage.querySelector("#live-meta").innerHTML = metaHtml(session);
    stage.querySelector("#controls").innerHTML = controlsHtml(session);
    stopFrames();
    draw();
  };

  const act = async (action) => {
    const session = store.getSnapshot().session;
    if (busy || !session) return;
    if (action === "stop" && !(await confirmDialog({
      title: "End this session early?",
      body: `You've focused for <strong>${duration(store.focusedSeconds(session))}</strong>. That time will be saved.`,
      confirmLabel: "End and save",
    }))) return;
    if (action === "cancel" && !(await confirmDialog({
      title: "Cancel this session?",
      body: "It will be discarded and won't count toward your stats.",
      confirmLabel: "Discard session", danger: true,
    }))) return;
    busy = true;
    try {
      await store[action]();
      if (action === "pause") toast("Paused. Take a breather.", "info");
      if (action === "resume") toast("Back to it!", "info");
    } catch (err) {
      toast(err.message, "error");
      store.sync();
    } finally {
      busy = false;
    }
  };

  const onKey = (e) => {
    if (mode !== "live" || e.target.closest("input, textarea, select, dialog") || e.metaKey || e.ctrlKey) return;
    const key = e.key.toLowerCase();
    const session = store.getSnapshot().session;
    if (key === " " || key === "p") { e.preventDefault(); act(session?.paused ? "resume" : "pause"); }
    else if (key === "e") act("stop");
    else if (key === "c") act("cancel");
  };
  document.addEventListener("keydown", onKey);

  const onChange = async (session, event) => {
    if (event?.type === "completed") return showFinished(event.session, "completed");
    if (event?.type === "ended") { toast(`Saved ${duration(event.session.focused_seconds)} of focus`); return showFinished(event.session, "ended"); }
    if (event?.type === "cancelled") { toast("Session discarded", "info"); return showSetup(); }
    if (event?.type === "gone") {
      try {
        const { session: saved } = await api.session(event.session.id);
        store.setPendingReflection(saved.id);
        return showFinished(saved, saved.status === "completed" ? "completed" : "elsewhere");
      } catch (_) {
        toast("The session was cancelled elsewhere", "info");
        return showSetup();
      }
    }
    if (session) return showLive(session);
    if (mode === "live" || mode === null) return startIdle();
  };

  // With no running session, offer the reflection for the last finished one
  // (e.g. it completed while you were on another page, or before a refresh).
  const startIdle = async () => {
    const pending = store.pendingReflection();
    if (pending) {
      try {
        const { session } = await api.session(pending);
        if (!session.end || session.reflection || session.distractions.length) throw new Error("done");
        return showFinished(session, session.status === "completed" ? "completed" : "ended");
      } catch (_) {
        store.setPendingReflection(null);
      }
    }
    return showSetup();
  };

  await store.sync();
  const unsubscribe = store.subscribe(onChange);
  refreshSide();

  return () => {
    unsubscribe();
    stopFrames();
    document.removeEventListener("keydown", onKey);
    document.title = "Focus Sessions · Focus Tracker";
  };
}
