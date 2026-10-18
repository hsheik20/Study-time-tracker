# Focus Tracker — Artifact 2 Development Log

**Project:** Focus Tracker (Python command-line productivity tool)  
**Course assignment:** Artifact 2 — Something You Will Use  
**Purpose of this log:** Record what I planned, what changed as I developed the application with Claude Code, issues encountered, and checks I performed.

> **Record accuracy:** This log was assembled from my planning discussions with ChatGPT, the screenshots and results I shared during development, and my descriptions of testing. It is a retrospective summary, not a verbatim transcript of every Claude Code prompt. Some features were already present by the time I inspected them, so the exact prompt that introduced each feature is not always known. No Git commit IDs or automated-test results are asserted here without direct verification.

## 1. Interactive main menu and activity tracking

**Planned:** The original command-based interface was confusing: launching without a subcommand showed a usage error. I wanted a numbered menu immediately on startup:

```text
========== FOCUS TRACKER ==========
1. Start Focus Session
2. View Session History
3. View Statistics
4. Manage Activities
5. Exit
Select an option:
```

**Changed / outcome:** Claude added an interactive menu and navigation for starting sessions, viewing history, viewing statistics, and managing activities. The application retained its command-based functionality while presenting a clearer starting experience. I could select an activity, add an optional note, end a session, and return to the menu.

**Checks performed:** I ran the application, recorded a session, and confirmed it appeared in Session History. I also reviewed the menu and available sections. Claude reported automated tests during this stage, but this log does not independently verify a test count.

**Version control:** After testing the early working application, I reported that I had committed and pushed it to GitHub. Exact commit identifiers are not included here.

## 2. Configurable timer and session controls

**Planned:** Allow users to choose how long to focus, see time remaining, pause and resume, end a session early, or cancel. Paused time should not count as focused time.

**Changed / outcome:** When I inspected the developing app, Claude had already implemented several of these features: custom session durations, a live countdown, a completion percentage/progress bar, and controls for pause/resume, end early, and cancel. I used a meditation activity with a 30-minute target when examining the timer.

**Checks performed:** I observed the countdown updating and confirmed that pausing stopped timer progress. Because these functions were already present, I did not need to request them again.

## 3. Terminal car and finish-line animation

**Planned:** Make a study session more engaging by showing a small car moving toward a finish line as time passes. The car should freeze on pause and advance on resume.

**Changed / outcome:** Claude enhanced the progress display with a simple text-based moving car and finish line. The first version was functional but looked cramped because the car, track, and percentage shared a narrow line.

**Feedback / next change:** I asked for a cleaner focus-session screen instead of squeezing all the information together.

## 4. Focus-session screen redesign

**Planned:** Improve visual hierarchy with a session header, activity name, prominent countdown, separate car/track area, progress percentage, and clearly labeled controls. Keep the display compatible with the VS Code terminal.

**Changed / outcome:** Claude redesigned the active-session view into more distinct sections with a large remaining-time display, an ACTIVE status indicator, separated progress visuals, and controls along the bottom.

**Check performed:** I viewed the redesigned screen during a running session and confirmed that it was clearer and easier to read. I chose not to pursue a full graphical interface for this assignment.

## 5. Completion chime and finished-session feedback

**Planned:** Play a brief chime when a countdown naturally reaches zero, without treating an early stop or cancellation as a normal completion. Display clear feedback afterward.

**Changed / outcome:** Claude added the completion sound and a finished-session screen. The display showed `00:00`, a completed progress track, a COMPLETE status, and a completion message before returning to the menu.

**Checks performed:** I ran a one-minute focus session through completion and **heard the chime**. I also saw the 100% completion screen, and later confirmed that the completed session appeared in Session History. The separate no-chime behavior for early stops/cancellations was requested but was not independently confirmed in the material used for this log.

## 6. Session History presentation redesign

**Planned:** Replace the basic text table with a more visually appealing, easy-to-scan history section, while preserving stored data and navigation.

**Changed / outcome:** Claude redesigned the history view to group sessions by date, distinguish session statuses visually, display session details and progress toward intended duration, and show daily and overall totals.

**Checks performed:** I opened the redesigned Session History and confirmed that records, including the recent completed session, were present. The new layout showed session totals and was noticeably easier to read.

## 7. Scope and future improvements

**Current working features observed during development:**
- Numbered terminal main menu
- Activities/categories and focus-session notes
- Configurable timed focus sessions
- Live countdown, progress indicator, pause/resume, end early, and cancel controls
- Animated terminal car moving toward a finish line
- Sound notification and completion feedback for a naturally finished session
- Saved session history, statistics, and redesigned history presentation

**Ideas intentionally postponed or not verified as implemented:**
- Optional break timers between focus sessions
- Daily and weekly focus goals
- More advanced productivity insights and end-of-session reflections
- A graphical desktop or web interface

These were part of the broader product vision, but the priority for Artifact 2 was to deliver a small program I could run and use.

---

*Compiled retrospectively from my recorded development discussions and testing observations. Future entries can be added as I continue building Focus Tracker.*
