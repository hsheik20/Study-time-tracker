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

- **Start Focus Session**: pick an activity (or create one) and start the timer.
  Press Enter to stop and save, or type `C` to cancel. Ctrl+C also stops and saves.
- **View Session History**: recent sessions, all sessions, one activity's sessions,
  or delete a session.
- **View Statistics**: totals per activity, session count, average and longest
  session, and your daily streak, for today, this week, this month or all time.
- **Manage Activities**: view, add, rename or delete activities, and log a
  session you forgot to time.

Every submenu has a "Back to Main Menu" option. Invalid input shows a message
and asks again.

### Commands

The same features are available as one-off commands, which is handy for scripts:

```bash
focus start studying -n "CSE 373 hw"   # start a timer
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
- `focus_tracker/cli.py`: argument parsing and one-off commands
- `focus_tracker/tracker.py`: sessions, activities, summaries and statistics
- `focus_tracker/storage.py`: JSON persistence (atomic writes)
- `focus_tracker/models.py`: the `Session` data type
- `focus_tracker/formatting.py`: duration parsing and display
