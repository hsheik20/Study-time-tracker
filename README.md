# Focus Tracker

A command-line tool for tracking how much time you spend focusing on different
activities: studying, working, meditating, personal projects, or anything else.

Pure Python standard library, no dependencies. Requires Python 3.10+.

## Install

```bash
pip install -e .        # installs the `focus` command
# or run without installing:
python3 -m focus_tracker
python3 focus_tracker/__main__.py
```

In VS Code you can also open `focus_tracker/__main__.py` and click **Run Python File**.

## Usage

### Interactive menu

Run `focus` with no arguments to open the menu:

```
========== FOCUS TRACKER ==========

1. Start Focus Session
2. View Session History
3. View Statistics
4. Manage Activities
5. Exit

Select an option:
```

- **Start Focus Session**: pick an activity (or create one), choose a length in
  minutes (default 25, or whatever you used last), and a live countdown starts:

  ```
  ╭──────────────────────────────────────────────────────────────╮
  │ FOCUS SESSION  ·  CSE 373 homework                  ● ACTIVE │
  ╰──────────────────────────────────────────────────────────────╯

                   ██  ██ ██████    ██████ ██████
                   ██  ██ ██  ██ ██ ██  ██ ██  ██
                   ██████ ██  ██    ██  ██ ██  ██
                       ██ ██  ██ ██ ██  ██ ██  ██
                       ██ ██████    ██████ ██████
                          remaining of 50m

      ·········o=o>········································|▚▞
      ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   20%

  ────────────────────────────────────────────────────────────────
             [P] Pause     [E] End early     [C] Cancel
  ```

  The car drives toward the finish line as you make progress, and stays put
  while the session is paused. In a short terminal panel the clock switches to
  normal-size digits, and in a very small one the screen collapses to a single
  status line. Set `NO_COLOR=1` to turn colors off.

  | Key | Action |
  |---|---|
  | `P` or Space | pause / resume (paused time isn't counted) |
  | `E` or Enter | end early and save the time actually focused (asks y/n) |
  | `C` | cancel and discard the session (asks y/n) |
  | Ctrl+C | end immediately and save |

  When the countdown reaches zero the session is saved automatically, a short
  chime plays, and a big "WELL DONE!" message celebrates the finished session.
  Ending early or cancelling doesn't chime. The chime uses your system's audio
  player (afplay on macOS, winsound on Windows, paplay/pw-play/aplay on Linux)
  and falls back to the terminal bell; set `FOCUS_TRACKER_SOUND=off` to mute it. Pauses are saved as they happen, so if you close the app
  mid-session nothing is lost: choose "Start Focus Session" again to continue,
  and a session whose time ran out while the app was closed is saved for you.

  The single-key controls need a real terminal (VS Code's integrated terminal
  works). If input is piped, type the letter and press Enter instead.
- **View Session History**: recent sessions, all sessions, one activity's sessions,
  or delete a session. Sessions are grouped by day with a daily total, and each
  one shows its time range, focused time and status: ✓ Completed, ■ Ended at 70%
  (ended early), ● Running, ‖ Paused, or · Untimed (logged manually or open-ended).
- **View Statistics**: totals per activity, session count, average and longest
  session, and your daily streak, for today, this week, this month or all time.
- **Manage Activities**: view, add, rename or delete activities, and log a
  session you forgot to time.

Every submenu has a "Back to Main Menu" option. Invalid input shows a message
and asks again.

### Commands

The same features are available as one-off commands, which is handy for scripts:

```bash
focus start studying -n "CSE 373 hw"   # start an open-ended session
focus start studying -m 50             # 50-minute timed session
focus pause / focus resume
focus status                           # what's running and for how long
focus stop                             # stop and save the session
focus cancel                           # discard the running session

focus add work 1h30m                   # log a session you forgot to time
focus add reading 45m --ended "2026-10-14 18:30"

focus log                              # recent sessions (with ids)
focus log -a studying -l 0             # all studying sessions
focus summary                          # totals per activity this week
focus summary today|week|month|all
focus delete 3                         # remove a session by id
```

Durations accept `90` (minutes), `45m`, `2h`, or `1h30m`. Weeks start on Monday.
In summaries, a session that crosses the start of the period only counts the
part inside the period.

## Data

Sessions and activities are stored as JSON in `~/.focus_tracker/sessions.json`. Set
`FOCUS_TRACKER_DATA=/path/to/file.json` to use a different file.

## Development

```bash
python3 -m unittest discover -s tests -v
```

## Layout

- `focus_tracker/menu.py`: interactive menu
- `focus_tracker/timer.py`: live countdown and keypress handling
- `focus_tracker/display.py`: drawing the session screen (big digits, track, bar)
- `focus_tracker/sound.py`: the generated completion chime
- `focus_tracker/history_view.py`: the session history screen
- `focus_tracker/cli.py`: argument parsing and one-off commands
- `focus_tracker/tracker.py`: sessions, activities, summaries and statistics
- `focus_tracker/storage.py`: JSON persistence (atomic writes)
- `focus_tracker/models.py`: the `Session` data type
- `focus_tracker/formatting.py`: duration parsing and display
