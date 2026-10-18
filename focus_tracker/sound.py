"""The completion chime, generated on the fly so no sound files are needed.

Played with the operating system's built-in player: afplay on macOS, winsound
on Windows, and paplay / pw-play / aplay on Linux. Falls back to the terminal
bell if none is available. Set FOCUS_TRACKER_SOUND=off to mute it.
"""

from __future__ import annotations

import io
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

SAMPLE_RATE = 22050
# A rising C major arpeggio (C6, E6, G6), each note ringing out like a bell.
NOTES = [(1046.50, 0.00), (1318.51, 0.14), (1567.98, 0.28)]  # (frequency Hz, start s)
NOTE_LENGTH = 0.75  # seconds each note rings for
VOLUME = 0.25
CHIME_SECONDS = NOTES[-1][1] + NOTE_LENGTH

_PLAYERS = [  # (command, extra args) tried in order on macOS / Linux
    ("afplay", []),
    ("paplay", []),
    ("pw-play", []),
    ("aplay", ["-q"]),
]


def chime_wav() -> bytes:
    """A ~1 second chime as 16-bit mono WAV data."""
    samples = []
    for i in range(int(CHIME_SECONDS * SAMPLE_RATE)):
        t = i / SAMPLE_RATE
        value = 0.0
        for freq, start in NOTES:
            dt = t - start
            if 0 <= dt < NOTE_LENGTH:
                attack = min(1.0, dt / 0.005)  # 5 ms fade-in avoids a click
                decay = math.exp(-dt * 5)
                # A quiet octave overtone makes it sound more like a bell.
                tone = math.sin(2 * math.pi * freq * dt) + 0.3 * math.sin(4 * math.pi * freq * dt)
                value += attack * decay * tone
        samples.append(int(max(-1.0, min(1.0, value * VOLUME)) * 32767))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buffer.getvalue()


def sound_enabled() -> bool:
    return os.environ.get("FOCUS_TRACKER_SOUND", "").strip().lower() not in ("0", "off", "false", "no")


def find_player() -> list[str] | None:
    for command, args in _PLAYERS:
        path = shutil.which(command)
        if path:
            return [path, *args]
    return None


def chime_file() -> Path:
    """The chime saved as a WAV file, written once and reused."""
    path = Path(tempfile.gettempdir()) / "focus-tracker-chime-v1.wav"
    if not path.exists():
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(chime_wav())
        os.replace(tmp, path)
    return path


def play_chime() -> None:
    """Play the chime, returning once it has been heard (about a second)."""
    if not sound_enabled():
        return
    try:
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(chime_wav(), winsound.SND_MEMORY)
            return
        player = find_player()
        if player:
            # Players like afplay linger ~1s after the sound ends, so let the
            # player finish in the background and only wait for the chime itself.
            process = subprocess.Popen([*player, str(chime_file())],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(CHIME_SECONDS)
            if process.poll() not in (None, 0):
                raise OSError("audio player failed")
            return
    except (OSError, subprocess.SubprocessError, RuntimeError):
        pass  # no working audio output: fall through to the bell
    sys.stdout.write("\a")
    sys.stdout.flush()
