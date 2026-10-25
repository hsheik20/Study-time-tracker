// The running session, shared by every page.
//
// The server is the source of truth (so the CLI and other tabs stay in sync).
// Between syncs the countdown is extrapolated locally from the last server
// snapshot, which keeps it accurate across page switches and refreshes; paused
// time never counts because the server excludes it.

import { api } from "./api.js";
import { playChime } from "./sound.js";

const SYNC_MS = 10000;
const PENDING_KEY = "focus-pending-reflection";

const listeners = new Set();
let snapshot = { session: null, suggested_minutes: 25, recent_locations: [] };
let syncedAt = performance.now();
let completing = false;
let started = false;

function emit(event = null) {
  for (const fn of listeners) fn(snapshot.session, event);
}

/** Call `fn(session, event)` now and on every change; returns an unsubscribe function. */
export function subscribe(fn) {
  listeners.add(fn);
  fn(snapshot.session, null);
  return () => listeners.delete(fn);
}

export const getSnapshot = () => snapshot;

function apply(data, event = null) {
  const previous = snapshot.session;
  snapshot = { ...snapshot, ...data };
  syncedAt = performance.now();
  // The session vanished without us ending it: finished in the CLI or another tab.
  if (previous && !snapshot.session && !event) event = { type: "gone", session: previous };
  emit(event);
}

/** Seconds elapsed since the last server snapshot (0 while paused). */
function drift(session) {
  return session && !session.paused ? (performance.now() - syncedAt) / 1000 : 0;
}

export function focusedSeconds(session = snapshot.session) {
  return session ? session.focused_seconds + drift(session) : 0;
}

export function remainingSeconds(session = snapshot.session) {
  if (!session || session.target_seconds == null) return null;
  return Math.max(0, session.remaining_seconds - drift(session));
}

export function progress(session = snapshot.session) {
  if (!session || !session.target_seconds) return 0;
  return Math.min(1, focusedSeconds(session) / session.target_seconds);
}

export async function sync() {
  try {
    apply(await api.activeSession());
  } catch (_) { /* offline for a moment; keep extrapolating */ }
}

// --- Reflection prompt bookkeeping ---------------------------------------
// Remembered across refreshes so a finished session still gets its prompt.

export function pendingReflection() {
  try { return Number(localStorage.getItem(PENDING_KEY)) || null; } catch (_) { return null; }
}

export function setPendingReflection(id) {
  try {
    if (id) localStorage.setItem(PENDING_KEY, String(id));
    else localStorage.removeItem(PENDING_KEY);
  } catch (_) {}
}

// --- Actions ----------------------------------------------------------------

export async function start(body) {
  apply(await api.startSession(body), { type: "started" });
}

export async function pause() {
  apply(await api.pauseSession(), { type: "paused" });
}

export async function resume() {
  apply(await api.resumeSession(), { type: "resumed" });
}

/** End early, keeping the focused time. */
export async function stop() {
  const { session } = await api.stopSession();
  setPendingReflection(session.id);
  apply({ session: null }, { type: "ended", session });
  return session;
}

export async function cancel() {
  const { session } = await api.cancelSession();
  apply({ session: null }, { type: "cancelled", session });
  return session;
}

// --- Completion at zero ------------------------------------------------------

async function checkCompletion() {
  const session = snapshot.session;
  if (completing || !session || session.paused || remainingSeconds(session) > 0) return;
  completing = true;
  try {
    // Reading the session makes the server save it if its time is up.
    const { session: saved } = await api.session(session.id);
    if (saved.status === "completed") {
      setPendingReflection(saved.id);
      playChime();
      const fresh = await api.activeSession();
      apply(fresh, { type: "completed", session: saved });
    } else if (saved.status === "running") {
      apply(await api.activeSession()); // clocks disagreed slightly; re-sync and retry
    }
  } catch (_) {
    await sync();
  } finally {
    completing = false;
  }
}

/** Start background syncing (called once by the app shell). */
export function startStore() {
  if (started) return;
  started = true;
  sync();
  setInterval(sync, SYNC_MS);
  setInterval(checkCompletion, 250);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) sync(); });
  window.addEventListener("focus", sync);
}
