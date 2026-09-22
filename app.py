"""Pomodoro Clock — a focus timer you run in the browser.

Classic Pomodoro technique: work in focused intervals, take a short break after
each one, and a longer break after every few. Durations are configurable in the
sidebar; the timer is deadline-based so it never drifts, even if a tick is late.

Run it with:  streamlit run app.py
"""

from __future__ import annotations

import base64
import inspect
import io
import json
import math
import struct
import time
import wave
from dataclasses import dataclass

import streamlit as st
import streamlit.components.v1 as components

# ---------------------------------------------------------------- phases ----


@dataclass(frozen=True)
class Phase:
    key: str
    label: str
    emoji: str
    color: str
    setting: str  # session_state key holding this phase's length in minutes
    done_message: str


PHASES: dict[str, Phase] = {
    "work": Phase(
        "work", "Focus", "🍅", "#e5484d", "work_min",
        "Pomodoro complete — time for a break.",
    ),
    "short": Phase(
        "short", "Short break", "☕", "#30a46c", "short_min",
        "Break over — back to it.",
    ),
    "long": Phase(
        "long", "Long break", "🌴", "#0091ff", "long_min",
        "Long break over — back to it.",
    ),
}

DEFAULTS: dict[str, object] = {
    # settings
    "work_min": 25,
    "short_min": 5,
    "long_min": 15,
    "long_every": 4,
    "auto_start": True,
    "sound": True,
    "task": "",
    # timer
    "phase": "work",
    "running": False,
    "deadline": None,   # epoch seconds; only meaningful while running
    "remaining": 25 * 60,
    # The length this phase actually started with. Editing a duration mid-phase
    # must not distort the ring or the caption of the phase already in flight.
    "phase_total": 25 * 60,
    # history
    "completed": 0,
    "focus_seconds": 0,
    "log": [],
    # one-shot signals
    "chime_id": 0,
    "chime_played": 0,
    "chime_kind": "work",
    "toast": None,
}


def init_state() -> None:
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = list(value) if isinstance(value, list) else value


# ------------------------------------------------------------ timer core ----


def phase_seconds(phase: str) -> int:
    return int(st.session_state[PHASES[phase].setting]) * 60


def remaining_seconds() -> float:
    if st.session_state.running and st.session_state.deadline is not None:
        return max(0.0, st.session_state.deadline - time.time())
    return max(0.0, float(st.session_state.remaining))


def start() -> None:
    if st.session_state.remaining <= 0:
        st.session_state.remaining = phase_seconds(st.session_state.phase)
        st.session_state.phase_total = st.session_state.remaining
    st.session_state.deadline = time.time() + st.session_state.remaining
    st.session_state.running = True


def pause() -> None:
    st.session_state.remaining = remaining_seconds()
    st.session_state.running = False
    st.session_state.deadline = None


def reset() -> None:
    st.session_state.running = False
    st.session_state.deadline = None
    st.session_state.remaining = phase_seconds(st.session_state.phase)
    st.session_state.phase_total = st.session_state.remaining


def go_to(phase: str, autostart: bool) -> None:
    st.session_state.phase = phase
    st.session_state.remaining = phase_seconds(phase)
    st.session_state.phase_total = st.session_state.remaining
    st.session_state.running = False
    st.session_state.deadline = None
    if autostart:
        start()


def finish_phase() -> None:
    """Called when the clock reaches zero on its own."""
    phase = st.session_state.phase
    if phase == "work":
        st.session_state.completed += 1
        st.session_state.focus_seconds += phase_seconds("work")
        st.session_state.log.append(
            {
                "#": st.session_state.completed,
                "Finished": time.strftime("%H:%M"),
                "Minutes": int(st.session_state.work_min),
                "Focus": st.session_state.task.strip() or "—",
            }
        )
        every = max(1, int(st.session_state.long_every))
        next_phase = "long" if st.session_state.completed % every == 0 else "short"
    else:
        next_phase = "work"

    st.session_state.toast = PHASES[phase].done_message
    st.session_state.chime_kind = "work" if phase == "work" else "break"
    st.session_state.chime_id += 1
    go_to(next_phase, autostart=bool(st.session_state.auto_start))


def skip() -> None:
    """Jump to the next phase without crediting the current one."""
    phase = st.session_state.phase
    if phase == "work":
        every = max(1, int(st.session_state.long_every))
        nxt = "long" if (st.session_state.completed + 1) % every == 0 else "short"
    else:
        nxt = "work"
    go_to(nxt, autostart=False)


def on_duration_change() -> None:
    """Keep a paused clock in sync with an edited duration.

    A running clock keeps the length it started with; the new value applies the
    next time that phase comes around.
    """
    if not st.session_state.running:
        st.session_state.remaining = phase_seconds(st.session_state.phase)
        st.session_state.phase_total = st.session_state.remaining


def clear_history() -> None:
    st.session_state.completed = 0
    st.session_state.focus_seconds = 0
    st.session_state.log = []
    go_to("work", autostart=False)


# --------------------------------------------------------------- display ----


def fmt_clock(seconds: float) -> str:
    total = int(math.ceil(seconds - 1e-6))
    return f"{total // 60:02d}:{total % 60:02d}"


def fmt_duration(seconds: int) -> str:
    hours, minutes = divmod(int(seconds) // 60, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def ring(fraction: float, color: str, clock: str, caption: str) -> str:
    """An SVG progress ring that empties as the phase runs down."""
    radius, stroke = 108.0, 14.0
    circumference = 2 * math.pi * radius
    offset = circumference * min(max(fraction, 0.0), 1.0)
    return f"""
<div class="ring-wrap">
  <svg viewBox="0 0 260 260" class="ring" role="img" aria-label="{caption} {clock}">
    <circle cx="130" cy="130" r="{radius}" fill="none"
            stroke="currentColor" class="ring-track" stroke-width="{stroke}"/>
    <circle cx="130" cy="130" r="{radius}" fill="none"
            stroke="{color}" stroke-width="{stroke}" stroke-linecap="round"
            stroke-dasharray="{circumference:.2f}"
            stroke-dashoffset="{offset:.2f}"
            transform="rotate(-90 130 130)"/>
    <text x="130" y="128" class="ring-time" text-anchor="middle"
          dominant-baseline="middle" fill="{color}">{clock}</text>
    <text x="130" y="168" class="ring-caption" text-anchor="middle"
          dominant-baseline="middle">{caption}</text>
  </svg>
</div>
"""


def dots() -> str:
    every = max(1, int(st.session_state.long_every))
    done = st.session_state.completed % every
    if st.session_state.completed and done == 0 and st.session_state.phase == "long":
        done = every
    pips = "".join(
        f'<span class="pip {"on" if i < done else "off"}"></span>' for i in range(every)
    )
    return (
        f'<div class="pips">{pips}'
        f'<span class="pips-label">{done}/{every} to long break</span></div>'
    )


CSS = """
<style>
  .block-container { padding-top: 2.2rem; max-width: 720px; }
  #MainMenu, footer { visibility: hidden; }

  .phase-title { text-align: center; font-size: 1.55rem; font-weight: 700;
                 letter-spacing: -.02em; margin: 0 0 .1rem; }
  .phase-sub   { text-align: center; opacity: .6; font-size: .9rem;
                 margin: 0 0 .6rem; }

  .ring-wrap { display: flex; justify-content: center; }
  .ring { width: 300px; max-width: 78vw; height: auto; }
  .ring-track { opacity: .12; }
  .ring-time { font-size: 58px; font-weight: 700; letter-spacing: -.03em;
               font-variant-numeric: tabular-nums;
               font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .ring-caption { font-size: 15px; fill: currentColor; opacity: .55; }

  .pips { display: flex; align-items: center; justify-content: center;
          gap: .45rem; margin: .1rem 0 1.1rem; }
  .pip { width: 9px; height: 9px; border-radius: 50%;
         background: currentColor; }
  .pip.on  { opacity: .85; }
  .pip.off { opacity: .2; }
  .pips-label { margin-left: .5rem; font-size: .78rem; opacity: .5; }

  div[data-testid="stButton"] button { width: 100%; border-radius: 10px;
                                       font-weight: 600; }
</style>
"""


def long_break_eta() -> str:
    if st.session_state.phase == "long":
        return "now"
    every = max(1, int(st.session_state.long_every))
    left = every - (st.session_state.completed % every)
    return "next" if left == 1 else f"in {left}"


def sidebar() -> None:
    with st.sidebar:
        st.subheader("Settings")
        st.number_input("Focus (min)", 1, 180, key="work_min", step=1,
                        on_change=on_duration_change)
        st.number_input("Short break (min)", 1, 60, key="short_min", step=1,
                        on_change=on_duration_change)
        st.number_input("Long break (min)", 1, 120, key="long_min", step=1,
                        on_change=on_duration_change)
        st.number_input("Long break every", 1, 12, key="long_every", step=1,
                        help="Number of pomodoros before a long break.")
        st.divider()
        st.toggle("Auto-start next phase", key="auto_start")
        st.toggle("Chime when a phase ends", key="sound")
        st.divider()
        if st.button("Clear history", width="stretch"):
            clear_history()
            st.rerun()
        st.caption("Keep this tab open — the timer lives in the browser session.")


def clock_body() -> None:
    phase = PHASES[st.session_state.phase]
    total = max(1, int(st.session_state.phase_total))
    left = remaining_seconds()

    st.markdown(
        f'<div class="phase-title">{phase.emoji} {phase.label}</div>', unsafe_allow_html=True
    )
    task = st.session_state.task.strip()
    sub = task if (phase.key == "work" and task) else (
        "running" if st.session_state.running else "paused"
    )
    st.markdown(f'<div class="phase-sub">{sub}</div>', unsafe_allow_html=True)

    caption = f"{total // 60} min {phase.label.lower()}"
    st.markdown(ring(left / total, phase.color, fmt_clock(left), caption),
                unsafe_allow_html=True)
    st.markdown(dots(), unsafe_allow_html=True)

    left_col, mid_col, right_col = st.columns(3)
    with left_col:
        if st.session_state.running:
            st.button("Pause", key="btn_pause", type="secondary", on_click=pause,
                      shortcut="Space", width="stretch")
        else:
            st.button("Start", key="btn_start", type="primary", on_click=start,
                      shortcut="Space", width="stretch")
    with mid_col:
        st.button("Reset", key="btn_reset", on_click=reset, width="stretch")
    with right_col:
        # Skipping changes the stats rendered outside this fragment too.
        if st.button("Skip →", key="btn_skip", shortcut="N", width="stretch"):
            skip()
            st.rerun(scope="app")

    if st.session_state.running and left <= 0:
        finish_phase()
        st.rerun(scope="app")


FRAGMENT = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)

if FRAGMENT is not None:
    live_clock = FRAGMENT(run_every=1.0)(clock_body)
else:  # pragma: no cover - fallback for older Streamlit
    def live_clock() -> None:
        clock_body()
        if st.session_state.running:
            time.sleep(1)
            st.rerun()


# ----------------------------------------------------------------- chime ----


@st.cache_data(show_spinner=False)
def chime_wav(kind: str) -> str:
    """A short two-note chime, synthesised so the app needs no asset files."""
    rate = 44100
    notes = [(880.0, 0.18), (1320.0, 0.42)] if kind == "work" else [(660.0, 0.18), (990.0, 0.42)]
    frames = bytearray()
    for freq, duration in notes:
        count = int(rate * duration)
        for i in range(count):
            envelope = math.exp(-3.2 * i / count)
            sample = 0.42 * envelope * math.sin(2 * math.pi * freq * i / rate)
            frames += struct.pack("<h", int(sample * 32767))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


# st.html runs the snippet in the top-level document, which is where autoplay
# and the Notification API actually work. Older Streamlit needs the iframe.
_HTML_RUNS_JS = "unsafe_allow_javascript" in inspect.signature(st.html).parameters


def embed(html: str) -> None:
    """Run a snippet of HTML/JS that renders nothing."""
    if _HTML_RUNS_JS:
        st.html(html, unsafe_allow_javascript=True)
    else:  # pragma: no cover - Streamlit < 1.58
        components.html(html, height=0)


def play_chime(kind: str, message: str) -> None:
    audio = chime_wav(kind)
    body = json.dumps(message)
    embed(
        f"""
<audio autoplay src="data:audio/wav;base64,{audio}"></audio>
<script>
  try {{
    if (window.Notification && Notification.permission === "granted") {{
      new Notification("Pomodoro Clock", {{ body: {body} }});
    }}
  }} catch (e) {{}}
</script>
"""
    )


def ask_notify_permission() -> None:
    embed(
        """
<script>
  try {
    if (window.Notification && Notification.permission === "default") {
      Notification.requestPermission();
    }
  } catch (e) {}
</script>
"""
    )


# ------------------------------------------------------------------ page ----


def main() -> None:
    st.set_page_config(page_title="Pomodoro Clock", page_icon="🍅",
                       layout="centered")
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)

    sidebar()
    live_clock()

    st.text_input("What are you working on?", key="task",
                  placeholder="optional — logged with each pomodoro")

    st.divider()
    stat_a, stat_b, stat_c = st.columns(3)
    stat_a.metric("Pomodoros", st.session_state.completed)
    stat_b.metric("Focus time", fmt_duration(st.session_state.focus_seconds))
    stat_c.metric("Next long break", long_break_eta())

    if st.session_state.log:
        with st.expander(f"Session log ({len(st.session_state.log)})", expanded=False):
            st.dataframe(st.session_state.log[::-1], hide_index=True,
                         width="stretch")

    # One-shot side effects for a phase that just ended.
    if st.session_state.chime_id != st.session_state.chime_played:
        st.session_state.chime_played = st.session_state.chime_id
        if st.session_state.toast:
            st.toast(st.session_state.toast, icon="⏰")
        if st.session_state.sound:
            play_chime(st.session_state.chime_kind, st.session_state.toast or "Time's up")
    elif st.session_state.running:
        ask_notify_permission()


if __name__ == "__main__":
    main()
