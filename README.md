# 🍅 Pomodoro Clock

A focus timer that runs in your browser, built with Streamlit. Work in focused
intervals, take a short break after each one, and a longer break after every few.

**[Use it here → 🍅](https://another-pomodoro-clock.streamlit.app/)**

## Run it locally

```bash
./run.sh
```

First run creates a virtual environment in `.venv/` and installs Streamlit into
it, then opens the app at http://localhost:8501. Nothing is installed
system-wide. Later runs reuse the venv and start immediately.

If you'd rather do it by hand:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/streamlit run app.py
```

## What it does

- **Three phases** — focus, short break, long break — each with its own length
  and colour. The long break arrives after every *n* pomodoros (default 4).
- **Deadline-based timer.** The countdown is computed from a target timestamp
  rather than accumulated ticks, so it stays accurate even if a refresh is late
  or the browser throttles the tab.
- **Auto-start** the next phase when one ends, or leave it off to start each
  phase yourself.
- **Chime and desktop notification** when a phase ends. The chime is synthesised
  at runtime, so there are no audio files to ship.
- **Session tracking** — pomodoros completed, total focus time, and a log of
  what you worked on. Tag the current pomodoro in the "What are you working on?"
  box and the label lands in the log.

## Keyboard shortcuts

| Key     | Action        |
| ------- | ------------- |
| `Space` | Start / pause |
| `N`     | Skip phase    |

Shortcuts are ignored while you're typing in a text field.

## Notes

- **Keep the tab open.** State lives in the Streamlit session, so closing the
  tab or reloading resets the timer and the log.
- **Everyone gets their own clock.** Session state isn't shared, so two people on
  the hosted link run independent timers and see only their own log.
- **Skip vs. finish.** A pomodoro only counts toward your stats when the clock
  runs it out. Skipping moves to the next phase without crediting it, and leaves
  the new phase paused so you can adjust things first.
- **Browser autoplay.** The end-of-phase chime plays because starting the timer
  counts as the user gesture browsers require. Allow notifications when prompted
  if you want an alert while the tab is in the background.
- Changing a duration while the clock is paused updates it immediately; changing
  it mid-phase applies from the next time that phase comes around — the phase in
  flight keeps the length it started with, ring and caption included.

## Deploying

The hosted copy runs on [Streamlit Community Cloud][cloud] from `main` of this
repo, with `app.py` as the entrypoint. Push to `main` and it redeploys itself.

Two things worth knowing:

- **`requirements.txt` is the deploy's dependency list.** Cloud installs from it
  on every rebuild, so the `streamlit>=1.64` floor matters: `app.py` calls
  `st.button(shortcut=...)` and `width="stretch"`, which older releases reject
  outright.
- **The app sleeps when idle.** A first visit after a quiet spell takes a few
  seconds to wake. It won't drop a running timer out from under you: an open tab
  holds a live connection, which counts as activity.

## Layout

| File               | Purpose                                      |
| ------------------ | -------------------------------------------- |
| `app.py`           | The whole app — timer, UI, chime synthesis    |
| `run.sh`           | Bootstraps the venv and launches Streamlit    |
| `requirements.txt` | Python dependencies                           |
