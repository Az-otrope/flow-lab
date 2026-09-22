"""Flow Lab — find your focus rhythm.

A focus timer built around the Pomodoro technique: work in focused intervals,
take a short break after each one, and a longer break after every few.
Durations are configurable in the sidebar; the timer is deadline-based so it
never drifts, even if a tick is late.

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
    """The structure of a phase. How it *looks* belongs to the active skin."""

    key: str
    setting: str  # session_state key holding this phase's length in minutes


PHASES: dict[str, Phase] = {
    "work": Phase("work", "work_min"),
    "short": Phase("short", "short_min"),
    "long": Phase("long", "long_min"),
}


# ----------------------------------------------------------------- skins ----


@dataclass(frozen=True)
class Skin:
    """A look: what the phases are called, plus the CSS that draws them.

    Everything that differs between light and dark lives in ``vars`` as CSS
    custom properties; ``template`` is written once against those variables.
    The browser therefore decides which palette applies, which matters because
    the user can flip Streamlit's theme at any moment and the server does not
    reliably learn about it until the rerun *after* the change.
    """

    key: str
    label: str
    names: dict[str, str]
    emojis: dict[str, str]
    done: dict[str, str]
    vars: dict[str, dict[str, str]]  # chrome -> custom property -> value
    template: str = ""
    fonts: str = ""
    ornament: str = ""     # stands in for the emoji in the title
    ornate_ring: bool = False

    def css(self) -> str:
        def block(selector: str, chrome: str) -> str:
            decls = " ".join(f"--{n}: {v};" for n, v in self.vars[chrome].items())
            return f"  {selector} {{ {decls} }}"

        # Before the chrome probe has run (or if it cannot), fall back to the
        # OS preference; the explicit attribute outranks both when it lands.
        return "\n".join([
            block(":root", "light"),
            "  @media (prefers-color-scheme: dark) {",
            block(":root", "dark"),
            "  }",
            block('html[data-chrome="light"]', "light"),
            block('html[data-chrome="dark"]', "dark"),
            self.template,
        ])


PLAIN = Skin(
    key="plain",
    label="Plain",
    names={"work": "Focus", "short": "Short break", "long": "Long break"},
    emojis={"work": "\U0001f345", "short": "\u2615", "long": "\U0001f334"},
    done={
        "work": "Pomodoro complete \u2014 time for a break.",
        "short": "Break over \u2014 back to it.",
        "long": "Long break over \u2014 back to it.",
    },
    vars={
        "light": {"c-work": "#e5484d", "c-short": "#30a46c", "c-long": "#0091ff"},
        "dark": {"c-work": "#e5484d", "c-short": "#30a46c", "c-long": "#0091ff"},
    },
)


_ARCANE_CSS = """
  /* ---- backdrop: nebulae, two star layers, then a vignette ----------- */
  .stApp {
    background:
      radial-gradient(125% 125% at 50% 42%, transparent 46%, var(--vignette) 100%),
      radial-gradient(880px 600px at 14% -8%, var(--nebula-a), transparent 62%),
      radial-gradient(760px 520px at 88% 4%, var(--nebula-b), transparent 64%),
      radial-gradient(720px 520px at 52% 108%, var(--nebula-c), transparent 60%),
      var(--base-bg);
  }
  [data-testid="stHeader"] { background: transparent; }

  .stApp::before, .stApp::after {
    content: ""; position: fixed; inset: -50%; z-index: 0; pointer-events: none;
  }
  .stApp::before {
    opacity: var(--star-op);
    background-image:
      radial-gradient(1.4px 1.4px at 20% 28%, var(--star) 50%, transparent 50%),
      radial-gradient(1px 1px at 68% 62%, var(--star) 50%, transparent 50%),
      radial-gradient(1.6px 1.6px at 44% 82%, var(--star) 50%, transparent 50%),
      radial-gradient(1px 1px at 86% 14%, var(--star) 50%, transparent 50%),
      radial-gradient(1.2px 1.2px at 12% 66%, var(--star) 50%, transparent 50%),
      radial-gradient(1px 1px at 76% 38%, var(--star) 50%, transparent 50%);
    background-size: 300px 300px, 420px 420px, 250px 250px,
                     170px 170px, 360px 360px, 210px 210px;
    animation: drift 150s linear infinite;
  }
  .stApp::after {
    opacity: var(--twinkle-hi);
    background-image:
      radial-gradient(2.2px 2.2px at 30% 20%, var(--star-bright) 50%, transparent 50%),
      radial-gradient(2.6px 2.6px at 72% 74%, var(--star-bright) 50%, transparent 50%),
      radial-gradient(2px 2px at 54% 44%, var(--star-bright) 50%, transparent 50%);
    background-size: 520px 520px, 680px 680px, 430px 430px;
    animation: drift 260s linear infinite reverse,
               twinkle 7s ease-in-out infinite;
  }
  @keyframes drift {
    from { transform: translate3d(0, 0, 0); }
    to   { transform: translate3d(-300px, -300px, 0); }
  }
  @keyframes twinkle {
    0%, 100% { opacity: var(--twinkle-hi); }
    50%      { opacity: var(--twinkle-lo); }
  }
  @media (prefers-reduced-motion: reduce) {
    .stApp::before, .stApp::after { animation: none; }
  }
  [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
    position: relative; z-index: 1;
  }

  /* ---- the clock panel ------------------------------------------------ */
  .ring { width: 360px; max-width: 88vw; }
  .clock-card {
    position: relative; overflow: hidden;
    margin: .2rem 0 1.1rem; padding: 1.4rem 1rem .5rem;
    border-radius: 26px; border: 1px solid var(--card-border);
    background: var(--card-bg); box-shadow: var(--card-shadow);
    backdrop-filter: blur(4px);
  }
  .clock-card::before {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background: radial-gradient(62% 46% at 50% 0%, var(--sheen), transparent 72%);
  }
  .phase-title {
    font-family: var(--font-display); font-size: 1.5rem; font-weight: 600;
    letter-spacing: .17em; text-transform: uppercase;
    text-shadow: var(--title-glow);
    display: flex; align-items: center; justify-content: center; gap: .75rem;
  }
  .orn { color: var(--orn); font-size: .75em; }
  .sigil { font-size: .82em; filter: saturate(.9); }
  .phase-sub {
    letter-spacing: .13em; text-transform: uppercase;
    font-size: .68rem; opacity: .45; margin-top: .35rem;
  }
  .ring-time { font-family: var(--font-display); font-weight: 600; letter-spacing: 0; }
  .ring-caption {
    letter-spacing: .15em; text-transform: uppercase; font-size: 11px;
  }
  .pip.on { box-shadow: 0 0 9px var(--orn); }
  .pips-label { letter-spacing: .08em; font-size: .7rem; }

  /* ---- the few widgets worth touching -------------------------------- */
  [data-testid="stSidebar"] {
    background: var(--sidebar-bg); backdrop-filter: blur(8px);
    border-right: 1px solid var(--card-border);
  }
  [data-testid="stBaseButton-primary"] {
    color: var(--button-text);
    box-shadow: 0 0 26px color-mix(in srgb, var(--accent) 35%, transparent);
  }
  [data-testid="stBaseButton-secondary"] {
    background: transparent; border-color: var(--card-border);
  }
"""

_ARCANE_FONT = ('"Cinzel", "Iowan Old Style", "Palatino Linotype", Palatino, '
                "Georgia, serif")

ARCANE = Skin(
    key="arcane",
    label="Arcane",
    names={"work": "Incantation", "short": "Respite", "long": "Long Rest"},
    emojis={"work": "\U0001f52e", "short": "\U0001f319", "long": "\U0001f409"},
    done={
        "work": "The incantation holds. Rest now.",
        "short": "Respite over \u2014 back to the work.",
        "long": "Long rest over \u2014 back to the work.",
    },
    template=_ARCANE_CSS,
    fonts='<style>@import url("https://fonts.googleapis.com/css2'
          '?family=Cinzel:wght@500;600;700&display=swap");</style>',
    ornament="\u2726",
    ornate_ring=True,
    vars={
        "dark": {
            "c-work": "#ffa257", "c-short": "#3ddca8", "c-long": "#bda6ff",
            "base-bg": "#07060f",
            "nebula-a": "rgba(96, 64, 190, .42)",
            "nebula-b": "rgba(22, 118, 150, .30)",
            "nebula-c": "rgba(150, 58, 130, .24)",
            "vignette": "rgba(0, 0, 0, .62)",
            "star": "rgba(228, 234, 255, .85)",
            "star-bright": "rgba(255, 250, 235, .95)",
            "star-op": ".75",
            "twinkle-hi": ".55",
            "twinkle-lo": ".16",
            "card-bg": "radial-gradient(closest-side, rgba(255,255,255,.055),"
                       " rgba(255,255,255,.012))",
            "card-border": "rgba(179, 157, 250, .18)",
            "card-shadow": "inset 0 0 70px rgba(120, 90, 220, .15),"
                           " 0 18px 50px rgba(0, 0, 0, .45)",
            "sheen": "rgba(179, 157, 250, .10)",
            "sidebar-bg": "rgba(9, 8, 20, .70)",
            "button-text": "#100e1c",
            "title-glow": "0 0 24px rgba(179, 157, 250, .40)",
            "orn": "rgba(196, 178, 255, .85)",
            "font-display": _ARCANE_FONT,
        },
        "light": {
            "c-work": "#a8460b", "c-short": "#0f766e", "c-long": "#6d28d9",
            "base-bg": "#f7f1e4",
            "nebula-a": "rgba(190, 150, 60, .30)",
            "nebula-b": "rgba(150, 110, 190, .22)",
            "nebula-c": "rgba(190, 110, 70, .18)",
            "vignette": "rgba(90, 60, 20, .20)",
            "star": "rgba(120, 85, 25, .35)",
            "star-bright": "rgba(150, 100, 20, .45)",
            "star-op": ".50",
            "twinkle-hi": ".40",
            "twinkle-lo": ".12",
            "card-bg": "radial-gradient(closest-side, rgba(255,252,244,.72),"
                       " rgba(255,250,238,.28))",
            "card-border": "rgba(120, 85, 25, .18)",
            "card-shadow": "inset 0 0 60px rgba(180, 120, 40, .09),"
                           " 0 16px 40px rgba(90, 60, 20, .10)",
            "sheen": "rgba(190, 150, 60, .13)",
            "sidebar-bg": "rgba(250, 245, 234, .74)",
            "button-text": "#fffaf2",
            "title-glow": "none",
            "orn": "rgba(150, 100, 25, .78)",
            "font-display": _ARCANE_FONT,
        },
    },
)

SKINS: dict[str, Skin] = {PLAIN.key: PLAIN, ARCANE.key: ARCANE}

DEFAULTS: dict[str, object] = {
    # settings
    "work_min": 25,
    "short_min": 5,
    "long_min": 15,
    "long_every": 4,
    "auto_start": True,
    "sound": True,
    "task": "",
    "skin": "plain",
    "skin_choice": "plain",
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


def skin() -> Skin:
    return SKINS.get(st.session_state.get("skin", "plain"), PLAIN)


def phase_name(phase: str) -> str:
    return skin().names[phase]


def phase_emoji(phase: str) -> str:
    return skin().emojis[phase]


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


def next_break(completed: int, every: int) -> str:
    """Which break follows a work phase, for a given credited count.

    A long break is earned, so it is due only once at least one pomodoro has
    been credited and the count has landed on a multiple. Both the finish path
    and the skip path ask this, so they cannot drift apart.
    """
    every = max(1, every)
    return "long" if completed > 0 and completed % every == 0 else "short"


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
        next_phase = next_break(st.session_state.completed,
                                int(st.session_state.long_every))
    else:
        next_phase = "work"

    st.session_state.toast = skin().done[phase]
    st.session_state.chime_kind = "work" if phase == "work" else "break"
    st.session_state.chime_id += 1
    go_to(next_phase, autostart=bool(st.session_state.auto_start))


def skip() -> None:
    """Jump to the next phase without crediting the current one.

    Because nothing is credited, the cycle position is unchanged -- skipping
    four focus phases leaves you exactly as far from a long break as you were.
    """
    phase = st.session_state.phase
    if phase == "work":
        nxt = next_break(st.session_state.completed,
                         int(st.session_state.long_every))
    else:
        nxt = "work"
    go_to(nxt, autostart=False)


def on_skin_change() -> None:
    """Runs before the rerun, so the CSS and favicon are never a step behind."""
    st.session_state.skin = st.session_state.skin_choice


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


def ring(fraction: float, clock: str, caption: str) -> str:
    """A progress ring that fills as the phase is used up."""
    radius, stroke = 108.0, 14.0
    circumference = 2 * math.pi * radius
    offset = circumference * min(max(fraction, 0.0), 1.0)
    return f"""
<div class="ring-wrap">
  <svg viewBox="0 0 260 260" class="ring" role="img" aria-label="{caption} {clock}">
    <circle cx="130" cy="130" r="{radius}" fill="none"
            stroke="currentColor" class="ring-track" stroke-width="{stroke}"/>
    <circle cx="130" cy="130" r="{radius}" fill="none"
            style="stroke: var(--accent, currentColor)" stroke-width="{stroke}" stroke-linecap="round"
            stroke-dasharray="{circumference:.2f}"
            stroke-dashoffset="{offset:.2f}"
            transform="rotate(-90 130 130)"/>
    <text x="130" y="128" class="ring-time" text-anchor="middle"
          dominant-baseline="middle" style="fill: var(--accent, currentColor)">{clock}</text>
    <text x="130" y="168" class="ring-caption" text-anchor="middle"
          dominant-baseline="middle">{caption}</text>
  </svg>
</div>
"""


def ornate_ring(fraction: float, clock: str, caption: str) -> str:
    """The same clock drawn as a spell circle: ticks, glow and a comet tip."""
    centre, radius, stroke = 150.0, 104.0, 12.0
    circumference = 2 * math.pi * radius
    left = min(max(fraction, 0.0), 1.0)
    offset = circumference * left
    # The arc grows clockwise from twelve o'clock, so the tip sits at the
    # elapsed fraction of a full turn.
    angle = math.radians(-90.0 + (1.0 - left) * 360.0)
    tip_x = centre + radius * math.cos(angle)
    tip_y = centre + radius * math.sin(angle)

    ticks = []
    for i in range(60):
        rad = math.radians(-90.0 + i * 6.0)
        major = i % 5 == 0
        inner, outer = 120.0, (133.0 if major else 127.0)
        ticks.append(
            f'<line x1="{centre + inner * math.cos(rad):.1f}"'
            f' y1="{centre + inner * math.sin(rad):.1f}"'
            f' x2="{centre + outer * math.cos(rad):.1f}"'
            f' y2="{centre + outer * math.sin(rad):.1f}"'
            f' stroke-width="{1.7 if major else 0.9}"'
            f' opacity="{0.40 if major else 0.16}"/>'
        )
    tick_marks = "".join(ticks)

    return f"""
<div class="ring-wrap">
  <svg viewBox="0 0 300 300" class="ring" role="img" aria-label="{caption} {clock}">
    <defs>
      <linearGradient id="arcGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color: var(--accent, currentColor); stop-opacity: .40"/>
        <stop offset="55%" style="stop-color: var(--accent, currentColor); stop-opacity: .92"/>
        <stop offset="100%" style="stop-color: var(--accent, currentColor)"/>
      </linearGradient>
      <filter id="softGlow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="5" result="blurred"/>
        <feMerge>
          <feMergeNode in="blurred"/><feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>
    </defs>
    <g stroke="currentColor" class="ring-ticks">{tick_marks}</g>
    <circle cx="{centre}" cy="{centre}" r="{radius}" fill="none"
            stroke="currentColor" class="ring-track" stroke-width="{stroke}"/>
    <circle cx="{centre}" cy="{centre}" r="{radius}" fill="none"
            stroke="url(#arcGrad)" stroke-width="{stroke}" stroke-linecap="round"
            stroke-dasharray="{circumference:.2f}"
            stroke-dashoffset="{offset:.2f}"
            transform="rotate(-90 {centre} {centre})" filter="url(#softGlow)"/>
    <circle cx="{tip_x:.2f}" cy="{tip_y:.2f}" r="5.5"
            style="fill: var(--accent, currentColor)" filter="url(#softGlow)"/>
    <circle cx="{centre}" cy="{centre}" r="84" fill="none"
            stroke="currentColor" stroke-width="1" opacity=".10"/>
    <text x="{centre}" y="144" class="ring-time" text-anchor="middle"
          dominant-baseline="middle" style="fill: var(--accent, currentColor)"
          textLength="172" lengthAdjust="spacing">{clock}</text>
    <text x="{centre}" y="192" class="ring-caption" text-anchor="middle"
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


BASE_CSS = """
<style>
  .block-container { padding-top: 2.2rem; max-width: 720px; }
  /* The main menu stays: Settings > Appearance is where light/dark lives. */
  footer { visibility: hidden; }

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
  [data-testid="stBaseButton-primary"] {
    background: var(--accent, #e5484d); border-color: var(--accent, #e5484d);
  }
  [data-testid="stBaseButton-primary"]:hover {
    background: var(--accent, #e5484d); border-color: var(--accent, #e5484d);
    filter: brightness(1.08);
  }
/* SKIN */
</style>
"""


def page_css() -> str:
    """Palette and structure. The lit phase is declared by the clock itself."""
    look = skin()
    css = BASE_CSS.replace("/* SKIN */", look.css())
    # @import has to lead its own stylesheet, so fonts ship as a separate tag.
    return look.fonts + css


def clock_card(key: str, left: float, total: int) -> str:
    """Title, ring and pips as a single block the skin can draw a frame around."""
    look = skin()
    name = phase_name(key)
    sigil = f'<span class="sigil">{phase_emoji(key)}</span>'
    if look.ornament:
        orn = f'<span class="orn">{look.ornament}</span>'
        head = f"{orn}{sigil}{name}{orn}"
    else:
        head = f"{sigil} {name}"

    task = st.session_state.task.strip()
    sub_line = task if (key == "work" and task) else (
        "running" if st.session_state.running else "paused"
    )
    caption = f"{total // 60} min {name.lower()}"
    draw = ornate_ring if look.ornate_ring else ring
    return (
        f"<style>:root {{ --accent: var(--c-{key}); }}</style>"
        '<div class="clock-card">'
        f'<div class="phase-title">{head}</div>'
        f'<div class="phase-sub">{sub_line}</div>'
        f'{draw(left / total, fmt_clock(left), caption)}'
        f'{dots()}'
        "</div>"
    )


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
        st.segmented_control("Theme", list(SKINS), key="skin_choice",
                             required=True, on_change=on_skin_change,
                             format_func=lambda k: SKINS[k].label,
                             width="stretch")
        st.divider()
        if st.button("Clear history", width="stretch"):
            clear_history()
            st.rerun()
        st.caption("Keep this tab open — the timer lives in the browser session.")


def clock_body() -> None:
    key = st.session_state.phase
    total = max(1, int(st.session_state.phase_total))
    left = remaining_seconds()

    st.markdown(clock_card(key, left, total), unsafe_allow_html=True)

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
      new Notification("Flow Lab", {{ body: {body} }});
    }}
  }} catch (e) {{}}
</script>
"""
    )


def install_chrome_probe() -> None:
    """Publish Streamlit's real theme as html[data-chrome].

    Streamlit's theme is the user's to change mid-session, and the server is
    told about it a beat late, so the palette is chosen in the browser from the
    body colour Streamlit actually painted. Guarded: reruns re-run this script,
    and we only ever want one observer and one timer.
    """
    embed(
        """
<script>
(function () {
  const read = function () {
    const parts = getComputedStyle(document.body).backgroundColor.match(/\\d+/g);
    if (!parts) { return; }
    const r = +parts[0], g = +parts[1], b = +parts[2];
    const want = (0.299 * r + 0.587 * g + 0.114 * b) < 128 ? "dark" : "light";
    if (document.documentElement.dataset.chrome !== want) {
      document.documentElement.dataset.chrome = want;
    }
  };
  read();
  if (window.__pomodoroChrome) { return; }
  window.__pomodoroChrome = read;
  const app = document.querySelector('[data-testid="stApp"]') || document.body;
  new MutationObserver(read).observe(app, {
    attributes: true, attributeFilter: ["class", "style"],
  });
  setInterval(read, 1000);
})();
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
    init_state()
    st.set_page_config(page_title="Flow Lab", layout="centered",
                       page_icon=phase_emoji("work"))
    sidebar()
    st.markdown(page_css(), unsafe_allow_html=True)
    install_chrome_probe()
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
