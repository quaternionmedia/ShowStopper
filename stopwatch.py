from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request
from time import monotonic
from typing import Callable, Optional

from textual.app import App, ComposeResult
from textual.containers import HorizontalGroup, VerticalGroup, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Button, Digits, Footer, Header, Label


def clock_face(seconds: float) -> str:
    """Seconds as the stopwatch shows them: hh:mm:ss.cc."""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02,.0f}:{minutes:02.0f}:{seconds:05.2f}"


class TimeDisplay(Digits):
    """A widget to display elapsed time."""

    start_time = reactive(monotonic)
    time = reactive(0.0)
    total = reactive(0.0)

    def on_mount(self) -> None:
        """Event handler called when widget is added to the app."""
        self.update_timer = self.set_interval(1 / 60, self.update_time, pause=True)

    def update_time(self) -> None:
        """Method to update time to current."""
        self.time = self.total + (monotonic() - self.start_time)

    def watch_time(self, time: float) -> None:
        """Called when the time attribute changes."""
        self.update(clock_face(time))

    def start(self) -> None:
        """Method to start (or resume) time updating."""
        self.start_time = monotonic()
        self.update_timer.resume()

    def stop(self):
        """Method to stop the time display updating."""
        self.update_timer.pause()
        self.total += monotonic() - self.start_time
        self.time = self.total

    def reset(self):
        """Method to reset the time display to zero."""
        self.total = 0
        self.time = 0


class Stopwatch(HorizontalGroup):
    """A stopwatch widget."""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Event handler called when a button is pressed."""
        button_id = event.button.id
        time_display = self.query_one(TimeDisplay)
        if button_id == "start":
            time_display.start()
            self.add_class("started")
        elif button_id == "stop":
            time_display.stop()
            self.remove_class("started")
        elif button_id == "reset":
            time_display.reset()

    def compose(self) -> ComposeResult:
        """Create child widgets of a stopwatch."""
        yield Button("Start", id="start", variant="success")
        yield Button("Stop", id="stop", variant="error")
        yield Button("Reset", id="reset")
        yield TimeDisplay()


def reader(base: str) -> Callable[[], dict]:
    """Read the show clock that the `showstopper serve` at `base` keeps."""
    url = base.rstrip("/") + "/family/state"

    def read() -> dict:
        with urllib.request.urlopen(url, timeout=2) as answer:
            return json.loads(answer.read())

    return read


class ShowClock(VerticalGroup):
    """The show's clock, which the performing family's hub drives with cues.

    It keeps no time of its own. Every `POLL` seconds it reads the one clock
    the `serve` process holds, and between reads it counts on from the last
    one, so the digits run smoothly and every connected view shows the same
    clock.
    """

    POLL = 0.25

    def __init__(self, read: Callable[[], dict]) -> None:
        super().__init__(id="show-clock")
        self.read = read
        # The last answer shown. The same answer again is not redrawn: a
        # served view sends every redraw down its websocket.
        self.seen: Optional[dict] = None

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="show-row"):
            yield Label("Show clock\nstopped\nno cue yet", id="show-status")
            yield TimeDisplay()
        yield Label("no laps", id="show-laps")

    def on_mount(self) -> None:
        self.set_interval(self.POLL, self.follow)
        self.call_after_refresh(self.follow)

    async def follow(self) -> None:
        """Read the clock once, and show what it says."""
        try:
            snapshot = await asyncio.to_thread(self.read)
            state, cue = snapshot["state"], snapshot["cue"]
            running = bool(state["running"])
            elapsed = float(state["elapsed"])
            laps = [float(lap) for lap in state["laps"]]
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.seen = None
            self.query_one("#show-status", Label).update(
                f"Show clock\nunreachable\n{type(error).__name__}")
            return
        if snapshot == self.seen:
            return
        self.seen = snapshot
        self.show(running, elapsed, laps, cue)

    def show(self, running: bool, elapsed: float, laps: list, cue: Optional[dict]) -> None:
        display = self.query_one(TimeDisplay)
        display.total = elapsed
        display.start_time = monotonic()
        display.time = elapsed
        if running:
            display.update_timer.resume()
            self.add_class("started")
        else:
            display.update_timer.pause()
            self.remove_class("started")
        if isinstance(cue, dict):
            said = f"cue {cue.get('number', '?')} {cue.get('name') or ''}".rstrip()
        else:
            said = "no cue yet"
        self.query_one("#show-status", Label).update(
            f"Show clock\n{'running' if running else 'stopped'}\n{said}")
        self.query_one("#show-laps", Label).update(
            "  ".join(f"lap {n} {clock_face(at)}" for n, at in enumerate(laps, 1))
            or "no laps")


class StopwatchApp(App):
    """A Textual app to manage stopwatches."""

    CSS_PATH = "stopwatch.tcss"

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("a", "add_stopwatch", "Add"),
        ("r", "remove_stopwatch", "Remove"),
    ]

    def __init__(self, family: Optional[Callable[[], dict]] = None) -> None:
        """`family` reads the show clock; without it there is none."""
        super().__init__()
        self.family = family

    def compose(self) -> ComposeResult:
        """Called to add widgets to the app."""
        yield Header()
        yield Footer()
        if self.family is not None:
            yield ShowClock(self.family)
        yield VerticalScroll(Stopwatch(), Stopwatch(), Stopwatch(), id="timers")

    def action_add_stopwatch(self) -> None:
        """An action to add a timer."""
        new_stopwatch = Stopwatch()
        self.query_one("#timers").mount(new_stopwatch)
        new_stopwatch.scroll_visible()

    def action_remove_stopwatch(self) -> None:
        """Called to remove a timer."""
        timers = self.query("Stopwatch")
        if timers:
            timers.last().remove()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = (
            "textual-dark" if self.theme == "textual-light" else "textual-light"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShowStopper's stopwatches")
    parser.add_argument("--family", metavar="URL",
                        help="show the clock kept by the `showstopper serve` at URL")
    args = parser.parse_args()
    app = StopwatchApp(family=reader(args.family) if args.family else None)
    app.run()
