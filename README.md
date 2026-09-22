# 🌊 Flow Lab

*Find your focus rhythm.*

A focus timer that runs in your browser, built with Streamlit. Today it runs the
Pomodoro method — focused intervals, a short break after each, a longer break
after every few — with more methods planned.

**[Use it here → 🌊](https://flow-lab.streamlit.app/)**

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
- **Two themes**, switchable from the sidebar. *Plain* is the default; *Arcane*
  redraws the clock as a glowing spell circle over a starfield. See
  [Themes](#themes).

## Keyboard shortcuts

| Key     | Action        |
| ------- | ------------- |
| `Space` | Start / pause |
| `N`     | Skip phase    |

Shortcuts are ignored while you're typing in a text field.

## Themes

Switch in the sidebar. **Plain** is the default and is exactly what it sounds
like. **Arcane** is a full redraw, not a recolour:

- The ring becomes a spell circle — sixty tick marks, a gradient arc with a
  soft glow, and a lit tip that tracks the leading edge as the phase burns down.
- Phases are renamed (Incantation / Respite / Long Rest) with matching
  completion messages, and the clock sits in a framed panel over a nebula
  backdrop with two drifting star layers, one of which twinkles.
- Display type is [Cinzel][cinzel]; the primary button is tinted to whichever
  phase is running.

A theme is one `Skin` in `app.py`: names, emoji, messages, per-phase colours,
and a CSS template whose bare-word tokens (`BASE_BG`, `STAR`, `CARD_BORDER`…)
are filled per chrome. Adding a third means adding an entry to `SKINS`.

Two things worth knowing about how it is built:

- **Almost no assets.** The starfield is tiled radial gradients and the ring is
  inline SVG, so there are no images. The one exception is Cinzel, which loads
  from Google Fonts behind a system-serif fallback — the clock stays readable
  if that request is slow or blocked, because the SVG time is drawn at a fixed
  `textLength` and so never reflows.
- **No fighting Streamlit for the widgets.** Each skin carries a light *and* a
  dark variant and layers onto whichever chrome you already use, rather than
  restyling every input. The only widgets it touches are the sidebar panel and
  the buttons.

### Light and dark

Use the **⋮ menu, top right** — the first row is `System / Light / Dark`. It's
Streamlit's own control; the skins follow it. `System` tracks your OS, which is
why you'll only ever see one of the two until you pick explicitly.

The palette is chosen *in the browser*, not on the server. Every value that
differs between light and dark is a CSS custom property defined under
`html[data-chrome="light"]` and `html[data-chrome="dark"]`, and a small guarded
script sets that attribute from the background colour Streamlit actually
painted. The server only ever decides which phase is lit
(`:root { --accent: var(--c-work) }`).

That indirection is load-bearing. `st.context.theme.type` still reports the
*previous* theme during the rerun that a theme change triggers, so anything
chosen server-side renders one flip behind — which looked like dark widgets on
a parchment background. Doing it in CSS means the switch can't be a step late.
If the script is ever blocked, `prefers-color-scheme` supplies the fallback.

Both star layers stop moving under `prefers-reduced-motion`.

[cinzel]: https://fonts.google.com/specimen/Cinzel

## Notes

- **Keep the tab open.** State lives in the Streamlit session, so closing the
  tab or reloading resets the timer and the log.
- **Everyone gets their own clock.** Session state isn't shared, so two people on
  the hosted link run independent timers and see only their own log.
- **Skip vs. finish.** A pomodoro counts only when the clock runs it out.
  Skipping moves to the next phase without crediting it and leaves that phase
  paused, so you can adjust things first.
- **Skipping doesn't advance the cycle.** Since nothing is credited, skipping
  through four focus phases leaves you at `0/4 to long break` — the long break
  is earned by finishing focus phases, not by passing through them. To reach one
  quickly, set **Focus** to 1 minute, or set **Long break every** to 1 and
  finish a single focus phase.
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
