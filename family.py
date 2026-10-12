"""The show clock: the one clock a served ShowStopper keeps for the hub.

ShowRunner, the performing family's hub, fires a cue and delivers each member
its part of the cue's `family` block. ShowStopper's part is a clock action:

    POST /family/cue    {"cue": {"number": "3", "name": "Second tune", "fired_at": "..."},
                         "action": {"clock": "start" | "stop" | "reset" | "lap"}}
                        200 {"ok": true, "state": {...}}
                        422 {"ok": false, "error": "..."}  for anything else
    GET  /family/state  200 {"member": "showstopper", "cue": {...} | null,
                             "state": {"running": bool, "elapsed": seconds,
                                       "laps": [seconds, ...]}}

Both are served on the same port as the page. There is one clock per served
instance: textual-serve starts an app process for every connection, so the
clock lives here, in the `serve` process, and every view reads it over
`GET /family/state` rather than keeping one of its own.
"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Callable, Dict, List, Optional, Tuple

MEMBER = "showstopper"
ACTIONS = ("start", "stop", "reset", "lap")
# Seconds are reported to the millisecond, which is finer than a cue is fired.
PLACES = 3


class Clock:
    """Start, stop, reset and lap, against a time source that can be swapped."""

    # `perf_counter` rather than `monotonic`, which on Windows moves in steps
    # of about 15 milliseconds: too coarse for a time given to the millisecond.
    def __init__(self, now: Callable[[], float] = perf_counter) -> None:
        self.now = now
        self.running = False
        # Seconds banked by earlier runs, and when the current run began.
        self.total = 0.0
        self.started = 0.0
        self.laps: List[float] = []

    def elapsed(self) -> float:
        return self.total + (self.now() - self.started if self.running else 0.0)

    def start(self) -> None:
        """Run it. Already running, nothing changes."""
        if not self.running:
            self.started = self.now()
            self.running = True

    def stop(self) -> None:
        """Hold it. Time spent stopped is not counted when it starts again."""
        if self.running:
            self.total += self.now() - self.started
            self.running = False

    def reset(self) -> None:
        """Back to a fresh clock: stopped, at zero, with no laps."""
        self.running = False
        self.total = 0.0
        self.laps = []

    def lap(self) -> None:
        """Record the time on the clock now, running or not."""
        self.laps.append(self.elapsed())

    def state(self) -> dict:
        return {
            "running": self.running,
            "elapsed": round(self.elapsed(), PLACES),
            "laps": [round(lap, PLACES) for lap in self.laps],
        }


class Refused(ValueError):
    """A body this member does not understand: answered with 422, never raised."""


def _shown(value: object) -> str:
    text = json.dumps(value) if not isinstance(value, str) else repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def action_of(body: object) -> str:
    """The clock action a cue's body asks for, or `Refused` saying why not."""
    if not isinstance(body, dict):
        raise Refused("the body must be a JSON object with a cue and an action")
    if not isinstance(body.get("cue"), dict):
        raise Refused("cue must be an object: {number, name, fired_at}")
    action = body.get("action")
    if not isinstance(action, dict) or set(action) != {"clock"}:
        raise Refused(f'ShowStopper takes {{"clock": one of {list(ACTIONS)}}}, '
                      f"not {_shown(action)}")
    verb = action["clock"]
    if verb not in ACTIONS:
        raise Refused(f"the clock can {', '.join(ACTIONS)}; it cannot {_shown(verb)}")
    return verb


class Member:
    """What the hub talks to: the clock, and the last cue that moved it."""

    def __init__(self, clock: Optional[Clock] = None) -> None:
        self.clock = clock or Clock()
        self.cue: Optional[Dict] = None

    def receive(self, body: object) -> Tuple[int, dict]:
        """Act on a cue's body. A refused cue changes nothing, its record included."""
        try:
            verb = action_of(body)
        except Refused as refusal:
            return 422, {"ok": False, "error": str(refusal)}
        getattr(self.clock, verb)()
        self.cue = body["cue"]
        return 200, {"ok": True, "state": self.clock.state()}

    def snapshot(self) -> dict:
        return {"member": MEMBER, "cue": self.cue, "state": self.clock.state()}


def routes(member: Member) -> list:
    """`POST /family/cue` and `GET /family/state`, as aiohttp routes on `member`."""
    from aiohttp import web

    async def cue(request: web.Request) -> web.Response:
        try:
            body = json.loads(await request.text())
        except ValueError:  # not JSON, or not text in the charset it claims
            return web.json_response({"ok": False, "error": "the body is not JSON"},
                                     status=422)
        status, answer = member.receive(body)
        return web.json_response(answer, status=status)

    async def state(request: web.Request) -> web.Response:
        return web.json_response(member.snapshot())

    return [web.post("/family/cue", cue), web.get("/family/state", state)]


def served(server_class: type, member: Member) -> type:
    """textual-serve's server, with the family's routes beside the page."""

    class Served(server_class):
        async def _make_app(self):
            app = await super()._make_app()
            app.add_routes(routes(member))
            return app

    return Served


def address(host: str, port: int) -> str:
    """Where an app process on this machine reaches the `serve` process."""
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    elif ":" in host:
        host = f"[{host}]"
    return f"http://{host}:{port}"
