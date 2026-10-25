// The completion chime, synthesised with the Web Audio API (no sound files):
// the same rising C-E-G bell arpeggio the terminal app plays.

const KEY = "focus-sound";
const NOTES = [[1046.5, 0], [1318.51, 0.14], [1567.98, 0.28]]; // [Hz, start s]
let context = null;

export function soundEnabled() {
  try { return localStorage.getItem(KEY) !== "off"; } catch (_) { return true; }
}

export function setSoundEnabled(on) {
  try { localStorage.setItem(KEY, on ? "on" : "off"); } catch (_) {}
}

/** Browsers only allow audio after a user gesture: call this from a click. */
export function unlockAudio() {
  try {
    context ??= new (window.AudioContext || window.webkitAudioContext)();
    if (context.state === "suspended") context.resume();
  } catch (_) { /* no audio support */ }
}

export function playChime({ force = false } = {}) {
  if (!force && !soundEnabled()) return;
  unlockAudio();
  if (!context) return;
  const start = context.currentTime + 0.05;
  for (const [freq, offset] of NOTES) {
    for (const [multiple, level] of [[1, 0.22], [2, 0.06]]) { // tone + quiet overtone
      const osc = context.createOscillator();
      const gain = context.createGain();
      osc.type = "sine";
      osc.frequency.value = freq * multiple;
      const t = start + offset;
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(level, t + 0.005);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.75);
      osc.connect(gain).connect(context.destination);
      osc.start(t);
      osc.stop(t + 0.8);
    }
  }
}
