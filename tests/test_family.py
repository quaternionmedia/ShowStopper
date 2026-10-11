"""The show clock the hub drives: `POST /family/cue` and `GET /family/state`.

The clock and its member are held to first in this process. Then a real
`showstopper serve` is started on a port of its own, and the routes are called
over HTTP the way the hub calls them, with views connected to its websocket the
way a browser connects them. `SHOWSTOPPER_TEST_PORT` names that port; without
it the operating system picks a free one.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import family

HERE = Path(__file__).resolve().parent.parent


class Now:
    """A clock that only moves when told to."""

    def __init__(self) -> None:
        self.at = 500.0

    def __call__(self) -> float:
        return self.at


def cue(number: str, action, name: str = "A cue") -> dict:
    return {"cue": {"number": number, "name": name, "fired_at": "2026-10-10T20:00:00+00:00"},
            "action": action}


# Bodies the hub might send that ShowStopper does not understand. Every one is
# a 422 with a reason, never a 500 and never a change to the clock.
NOT_UNDERSTOOD = {
    "an unknown clock action": cue("9", {"clock": "rewind"}),
    "another member's action": cue("9", {"patch": "moog.dfam.complex"}),
    "a clock action with company": cue("9", {"clock": "start", "and": "more"}),
    "an action that is not an object": cue("9", "start"),
    "an action that is not text": cue("9", {"clock": 1}),
    "no action": {"cue": {"number": "9"}},
    "no cue": {"action": {"clock": "start"}},
    "a cue that is not an object": {"cue": "9", "action": {"clock": "start"}},
    "a body that is a list": [cue("9", {"clock": "start"})],
    "a body that is null": None,
}


# --- the clock ---------------------------------------------------------------


def test_a_clock_starts_stopped_at_zero():
    assert family.Clock(Now()).state() == {"running": False, "elapsed": 0.0, "laps": []}


def test_start_runs_stop_holds_and_start_again_resumes():
    now = Now()
    clock = family.Clock(now)
    clock.start()
    now.at += 10
    clock.stop()
    now.at += 500  # stopped: not counted
    clock.start()
    now.at += 2.5
    assert clock.state() == {"running": True, "elapsed": 12.5, "laps": []}


def test_starting_a_running_clock_or_stopping_a_stopped_one_changes_nothing():
    now = Now()
    clock = family.Clock(now)
    clock.stop()
    clock.start()
    now.at += 3
    clock.start()
    now.at += 4
    assert clock.state()["elapsed"] == 7.0


def test_lap_records_the_time_on_the_clock_and_it_runs_on():
    now = Now()
    clock = family.Clock(now)
    clock.start()
    now.at += 3.25
    clock.lap()
    now.at += 1.5
    clock.lap()
    assert clock.state() == {"running": True, "elapsed": 4.75, "laps": [3.25, 4.75]}


def test_reset_is_a_fresh_clock_even_from_running():
    now = Now()
    clock = family.Clock(now)
    clock.start()
    now.at += 8
    clock.lap()
    clock.reset()
    now.at += 8
    assert clock.state() == {"running": False, "elapsed": 0.0, "laps": []}


# --- the member: what a cue does ---------------------------------------------


@pytest.mark.parametrize("verb, running", [("start", True), ("stop", False),
                                           ("reset", False), ("lap", False)])
def test_every_clock_action_answers_200_with_the_state(verb, running):
    member = family.Member(family.Clock(Now()))
    status, answer = member.receive(cue("3", {"clock": verb}, "Second tune"))

    assert status == 200
    assert answer == {"ok": True, "state": member.clock.state()}
    assert answer["state"]["running"] is running
    assert member.snapshot()["cue"] == {"number": "3", "name": "Second tune",
                                        "fired_at": "2026-10-10T20:00:00+00:00"}


def test_the_state_names_the_member_and_no_cue_before_the_first():
    assert family.Member(family.Clock(Now())).snapshot() == {
        "member": "showstopper", "cue": None,
        "state": {"running": False, "elapsed": 0.0, "laps": []}}


@pytest.mark.parametrize("what", sorted(NOT_UNDERSTOOD))
def test_an_action_it_does_not_understand_is_422_and_changes_nothing(what):
    member = family.Member(family.Clock(Now()))
    member.receive(cue("1", {"clock": "start"}))
    before = member.snapshot()

    status, answer = member.receive(NOT_UNDERSTOOD[what])

    assert status == 422
    assert answer["ok"] is False and isinstance(answer["error"], str) and answer["error"]
    assert member.snapshot() == before


# --- a real `showstopper serve`, called over HTTP -----------------------------


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def call(method: str, url: str, body: bytes = None):
    """One HTTP call: the status and the answer, decoded when it is JSON.

    Errors included, and an answer that is not JSON comes back as its text, so
    a 500's page fails the assertion about the status rather than this helper.
    """
    request = urllib.request.Request(url, data=body, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as answer:
            status, raw = answer.status, answer.read()
    except urllib.error.HTTPError as refused:
        status, raw = refused.code, refused.read()
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw.decode("utf-8", "replace")


class Served:
    def __init__(self, port: int, process: subprocess.Popen) -> None:
        self.base = f"http://127.0.0.1:{port}"
        self.socket = f"ws://127.0.0.1:{port}/ws?width=100&height=30"
        self.process = process

    def post(self, body) -> tuple:
        return call("POST", self.base + "/family/cue", json.dumps(body).encode())

    def state(self) -> tuple:
        return call("GET", self.base + "/family/state")


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    port = int(os.environ.get("SHOWSTOPPER_TEST_PORT") or free_port())
    process = subprocess.Popen(
        [sys.executable, str(HERE / "showstopper_cli.py"), "serve", "--host", "127.0.0.1",
         "--port", str(port), "--state", str(tmp_path_factory.mktemp("state"))],
        cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    server = Served(port, process)
    try:
        deadline = time.monotonic() + 30
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"serve exited: {process.stderr.read().decode()[-500:]}")
            try:
                if server.state()[0] == 200:
                    break
            except (OSError, ValueError):
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(f"{server.base}/family/state never answered")
            time.sleep(0.2)
        yield server
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def test_the_served_state_names_the_member_and_the_clock(served):
    status, answer = served.state()

    assert status == 200
    assert answer["member"] == "showstopper"
    assert set(answer) == {"member", "cue", "state"}
    assert set(answer["state"]) == {"running", "elapsed", "laps"}


def test_each_action_posted_answers_200_and_the_state_shows_the_cue(served):
    for number, verb in (("21", "reset"), ("22", "start"), ("23", "lap"), ("24", "stop")):
        status, answer = served.post(cue(number, {"clock": verb}))
        assert status == 200 and answer["ok"] is True, (verb, answer)
        assert served.state()[1]["cue"]["number"] == number
        time.sleep(0.05)  # so the lap and the stop each have time to measure

    state = served.state()[1]["state"]
    assert state["running"] is False and len(state["laps"]) == 1
    assert state["elapsed"] >= state["laps"][0] > 0

    status, answer = served.post(cue("25", {"clock": "reset"}))
    assert (status, answer["state"]) == (200, {"running": False, "elapsed": 0.0, "laps": []})


@pytest.mark.parametrize("what", sorted(NOT_UNDERSTOOD))
def test_a_body_it_does_not_understand_is_422_over_http_too(served, what):
    before = served.state()[1]
    status, answer = served.post(NOT_UNDERSTOOD[what])

    assert status == 422 and answer["ok"] is False and answer["error"]
    assert served.state()[1]["cue"] == before["cue"]


def test_a_body_that_is_not_json_is_422_not_500(served):
    status, answer = call("POST", served.base + "/family/cue", b"clock: start")
    assert status == 422 and answer == {"ok": False, "error": "the body is not JSON"}

    status, answer = call("POST", served.base + "/family/cue", b"\xff\xfe{")
    assert status == 422 and answer["ok"] is False


async def seen(ws, *wanted: bytes, seconds: float = 20.0) -> None:
    """Read the view's frames until every one of `wanted` has been drawn.

    From the frame after the last one read: a view redraws only what changed,
    so what it drew before this call says nothing about what it shows now.
    """
    import aiohttp

    missing = set(wanted)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while missing and loop.time() < deadline:
        # The whole wait, not `receive(timeout=...)`: that restarts after each
        # of the server's 15-second pings, so a longer wait never ends.
        try:
            message = await asyncio.wait_for(ws.receive(), deadline - loop.time())
        except asyncio.TimeoutError:
            break
        if message.type == aiohttp.WSMsgType.BINARY:
            missing = {text for text in missing if text not in message.data}
        elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            break
    assert not missing, f"no frame drew {sorted(missing)} within {seconds}s"


def test_a_cue_posted_changes_what_every_connected_view_shows(served):
    # Two views, which textual-serve runs as two app processes. One POST, and
    # both show it: the clock is the served instance's, not either view's.
    import aiohttp

    async def scenario():
        assert served.post(cue("30", {"clock": "reset"}, "From the top"))[0] == 200
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(served.socket) as one, \
                    session.ws_connect(served.socket) as two:
                for view in (one, two):
                    await seen(view, b"cue 30 From the top")

                async with session.post(served.base + "/family/cue",
                                        json=cue("31", {"clock": "start"}, "Overture")) as sent:
                    assert sent.status == 200
                for view in (one, two):
                    await seen(view, b"running", b"cue 31 Overture")

                assert served.post(cue("32", {"clock": "lap"}, "Act two"))[0] == 200
                for view in (one, two):
                    await seen(view, b"lap 1")

                assert served.post(cue("33", {"clock": "stop"}, "Curtain"))[0] == 200
                for view in (one, two):
                    await seen(view, b"stopped", b"cue 33 Curtain")

    asyncio.run(scenario())


def test_the_checks_wait_for_a_frame_ends_on_time_through_the_servers_pings(
        served, monkeypatch):
    # textual-serve pings every 15 seconds, and a wait that outlasted one ping
    # used to restart and never end: `check` hung rather than answering 1. A
    # stopped clock leaves the view idle, so nothing but the ping arrives.
    import showstopper_cli

    assert served.post(cue("40", {"clock": "reset"}))[0] == 200
    monkeypatch.setattr(showstopper_cli, "FIRST_FRAME", 16.0)
    started = time.monotonic()
    found, frames = asyncio.run(asyncio.wait_for(
        showstopper_cli.first_frame_with(served.base + "/", b"never drawn"), 45))

    assert (found, frames > 0) == (False, True)
    assert time.monotonic() - started < 30
