"""`showstopper serve` and `showstopper check`: the performing family's demo contract.

    showstopper serve --host H --port P --state DIR
    showstopper check --url U --shots DIR

The contract is declared once for every member of the performing family, in
the qm corpus's ci/family-demo.yaml. `serve` puts the stopwatch in a browser
through textual-serve, on exactly the address it is given. `check` asks two
things, and says which it asked:

- the served address streams this app: a websocket opened the way the
  browser page opens one carries the app's own Start button. textual-serve
  starts an app per connection, so there is no single running app to drive;
  this is the surface.
- the stopwatch behaves: tests/test_stopwatch.py, driving the app through
  Textual's pilot in this process -- start counts, stop holds, start resumes,
  reset zeroes -- with its pictures written to `--shots`.

Exit 0 when both hold, 1 when either does not, and 3 when there is nothing to
check against (no server answering, or the tests' tools missing), because that
says nothing about ShowStopper.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANNOT_SAY = 3
# How long the served app may take to draw its first screen.
FIRST_FRAME = 20.0


def serve(host: str, port: int, state: Path) -> int:
    """textual-serve on exactly the address given. ShowStopper keeps no state."""
    try:
        from textual_serve.server import Server
    except ImportError:
        print("textual-serve is missing: it comes with the dev group (pdm install)",
              file=sys.stderr)
        return 2
    state.mkdir(parents=True, exist_ok=True)
    command = f'"{sys.executable}" "{HERE / "stopwatch.py"}"'
    Server(command, host=host, port=port, title="ShowStopper").serve()
    return 0


async def first_frame_with(url: str, label: bytes) -> tuple[bool, int]:
    """Open the app's websocket as its page does; did a frame carry `label`?"""
    import aiohttp

    parts = urllib.parse.urlsplit(url)
    socket = f"ws://{parts.netloc}/ws?width=110&height=30"
    frames = 0
    async with aiohttp.ClientSession() as session:
        try:
            ws = await session.ws_connect(socket)
        except aiohttp.ClientError as error:
            print(f"surface: {socket} would not open: {error}", flush=True)
            return False, 0
        async with ws:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + FIRST_FRAME
            while loop.time() < deadline:
                try:
                    message = await ws.receive(timeout=deadline - loop.time())
                except asyncio.TimeoutError:
                    break
                if message.type == aiohttp.WSMsgType.BINARY:
                    frames += 1
                    if label in message.data:
                        return True, frames
                elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
    return False, frames


def check(url: str, shots: Path) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5):
            pass
    except (urllib.error.URLError, OSError, ValueError) as error:
        print(f"check could not run: nothing answers at {url} ({error})", file=sys.stderr)
        return CANNOT_SAY
    try:
        import aiohttp  # noqa: F401  (textual-serve's own client library)
    except ImportError as error:
        print(f"check could not run: {error.name} is missing: pdm install", file=sys.stderr)
        return CANNOT_SAY
    # Python exits 1 when `-m` names a module it cannot run, which is also the
    # status of a failed assertion: a broken pytest would read as ShowStopper failing.
    runner = subprocess.run([sys.executable, "-m", "pytest", "--version"],
                            capture_output=True, text=True, check=False)
    if runner.returncode != 0:
        print(f"check could not run: pytest does not run here: "
              f"{(runner.stderr or runner.stdout).strip()[-200:]}", file=sys.stderr)
        return CANNOT_SAY

    streamed, frames = asyncio.run(first_frame_with(url, b"Start"))
    print(f"surface: {frames} frame(s) from {url}; "
          f"{'one carried' if streamed else 'none carried'} the app's Start button", flush=True)

    shots = shots.resolve()
    shots.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "SHOWSTOPPER_SHOTS": str(shots), "PYTHONDONTWRITEBYTECODE": "1"}
    behaviour = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_stopwatch.py", "-p", "no:cacheprovider"],
        cwd=HERE, env=env, check=False).returncode
    if behaviour not in (0, 1):
        print(f"check could not run: pytest exited {behaviour}", file=sys.stderr)
        return CANNOT_SAY
    return 0 if streamed and behaviour == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="showstopper", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    served = commands.add_parser("serve", help="the stopwatch in a browser, on the address given")
    served.add_argument("--host", default="127.0.0.1")
    served.add_argument("--port", type=int, required=True)
    served.add_argument("--state", type=Path, required=True,
                        help="scratch directory; ShowStopper keeps no state, so it stays empty")
    checked = commands.add_parser("check", help="check a ShowStopper that is already served")
    checked.add_argument("--url", required=True)
    checked.add_argument("--shots", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(args.host, args.port, args.state)
    return check(args.url, args.shots)


if __name__ == "__main__":
    sys.exit(main())
