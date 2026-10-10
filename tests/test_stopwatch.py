"""The stopwatch, driven headless through Textual's pilot.

The clock is the module's own `monotonic`, swapped for one the test advances by
hand, so every elapsed time below is exact and the screenshots are the same on
every run.
"""

import asyncio
import os
from pathlib import Path

import pytest

import stopwatch
from stopwatch import Stopwatch, StopwatchApp, TimeDisplay

# `showstopper check` points the shutter elsewhere, so a check writes no picture
# into the checkout.
MEDIA = Path(os.environ.get("SHOWSTOPPER_SHOTS")
             or Path(__file__).resolve().parent.parent / "walkthrough" / "media")


class Clock:
    """A monotonic clock that only moves when told to."""

    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(stopwatch, "monotonic", fake)
    return fake


def run(scenario):
    """Run `scenario(app, pilot)` against a headless StopwatchApp."""

    async def main():
        app = StopwatchApp()
        async with app.run_test(size=(80, 24)) as pilot:
            return await scenario(app, pilot)

    return asyncio.run(main())


async def tick(pilot):
    # The display refreshes on a 1/60 s interval; give it a few.
    await pilot.pause(0.1)


async def press(pilot, watch, button_id: str):
    """Click one of a stopwatch's buttons, as a person would.

    Textual ignores a click on a button still showing its previous press (the
    `-active` effect lasts a fraction of a second), and a test is faster than a
    person, so wait that out before clicking the same button again.
    """
    button = watch.query_one(f"#{button_id}")
    for _ in range(40):
        if not button.has_class("-active"):
            break
        await pilot.pause(0.05)
    assert await pilot.click(button), f"#{button_id} was not under the pointer"
    await pilot.pause()


def shoot(app, name: str) -> Path:
    """Record a screenshot for the walkthrough. Recorded, never compared.

    Written with LF line endings on every platform: `save_screenshot` writes
    CRLF on Windows, which git reports as a change to an unchanged picture.
    """
    MEDIA.mkdir(parents=True, exist_ok=True)
    path = MEDIA / f"{name}.svg"
    with open(path, "w", encoding="utf-8", newline="\n") as svg:
        svg.write(app.export_screenshot())
    assert path.exists() and path.stat().st_size > 0, f"{path.name} was not written"
    return path


def test_three_stopwatches_start_at_zero(clock):
    async def scenario(app, pilot):
        watches = app.query(Stopwatch)
        assert len(watches) == 3
        for display in app.query(TimeDisplay):
            assert display.value == "00:00:00.00"

    run(scenario)


def test_start_stop_and_reset(clock):
    async def scenario(app, pilot):
        watch = app.query(Stopwatch).first()
        display = watch.query_one(TimeDisplay)

        await press(pilot, watch, "start")
        assert watch.has_class("started")
        assert not watch.query_one("#start").display
        assert watch.query_one("#stop").display
        assert not watch.query_one("#reset").visible

        clock.advance(65.25)
        await tick(pilot)
        assert display.value == "00:01:05.25"
        shoot(app, "02-the-stopwatch-running")

        await press(pilot, watch, "stop")
        assert not watch.has_class("started")
        assert display.value == "00:01:05.25"

        # Stopped means frozen: the clock moves on and the display does not.
        clock.advance(30)
        await tick(pilot)
        assert display.value == "00:01:05.25"
        shoot(app, "02-the-stopwatch-stopped")

        await press(pilot, watch, "reset")
        assert display.value == "00:00:00.00"

    run(scenario)


def test_start_after_stop_resumes_from_the_total(clock):
    async def scenario(app, pilot):
        watch = app.query(Stopwatch).first()
        display = watch.query_one(TimeDisplay)

        await press(pilot, watch, "start")
        clock.advance(10)
        await press(pilot, watch, "stop")
        clock.advance(500)  # time passing while stopped is not counted
        await press(pilot, watch, "start")
        clock.advance(2.5)
        await tick(pilot)
        assert display.value == "00:00:12.50"

    run(scenario)


def test_stopwatches_are_independent(clock):
    async def scenario(app, pilot):
        first, second, third = app.query(Stopwatch)

        await press(pilot, second, "start")
        clock.advance(3)
        await tick(pilot)
        assert second.has_class("started")
        assert not first.has_class("started") and not third.has_class("started")
        assert first.query_one(TimeDisplay).value == "00:00:00.00"
        assert second.query_one(TimeDisplay).value == "00:00:03.00"
        assert third.query_one(TimeDisplay).value == "00:00:00.00"

    run(scenario)


def test_keys_add_and_remove_stopwatches(clock):
    async def scenario(app, pilot):
        await pilot.press("a")
        assert len(app.query(Stopwatch)) == 4
        await pilot.press("r", "r")
        assert len(app.query(Stopwatch)) == 2

    run(scenario)


def test_d_toggles_dark_mode(clock):
    async def scenario(app, pilot):
        before = app.theme
        await pilot.press("d")
        assert app.theme != before
        await pilot.press("d")
        assert app.theme == before

    run(scenario)
