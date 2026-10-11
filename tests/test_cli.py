"""`showstopper serve` and `showstopper check`: the performing family's demo contract.

Neither may run for real here -- `serve` binds a port -- so what is held is what
`serve` hands textual-serve, and that a check with nothing to check against says
so rather than failing.
"""

import sys

import showstopper_cli


def test_serve_hands_textual_serve_the_address_and_this_app(tmp_path, monkeypatch):
    import textual_serve.server

    made = {}

    class Server:
        def __init__(self, command, host, port, title):
            made.update(command=command, host=host, port=port, title=title)

        def serve(self):
            made["served"] = True

    monkeypatch.setattr(textual_serve.server, "Server", Server)
    status = showstopper_cli.main(
        ["serve", "--host", "127.0.0.1", "--port", "18410", "--state", str(tmp_path / "s")])

    assert status == 0
    assert made["host"] == "127.0.0.1" and made["port"] == 18410 and made["served"]
    # Each connection's app process is told where the one show clock is kept.
    assert made["command"] == (
        f'"{sys.executable}" "{showstopper_cli.HERE / "stopwatch.py"}" '
        f"--family http://127.0.0.1:18410")
    assert (tmp_path / "s").is_dir()


def test_serve_on_every_interface_points_the_views_at_loopback(tmp_path, monkeypatch):
    import textual_serve.server

    made = {}

    class Server:
        def __init__(self, command, host, port, title):
            made.update(command=command, host=host)

        def serve(self):
            pass

    monkeypatch.setattr(textual_serve.server, "Server", Server)
    showstopper_cli.main(
        ["serve", "--host", "0.0.0.0", "--port", "18410", "--state", str(tmp_path / "s")])

    assert made["host"] == "0.0.0.0"
    assert made["command"].endswith("--family http://127.0.0.1:18410")


def test_the_served_port_carries_the_family_routes_beside_the_page():
    # textual-serve's own app, built the way `serve` builds it: the page, its
    # websocket, and the two routes the hub calls, all on one port.
    import asyncio

    import family
    from textual_serve.server import Server

    served = family.served(Server, family.Member())("unused", host="127.0.0.1", port=18410)
    app = asyncio.run(served._make_app())
    routes = {(route.method, route.resource.canonical) for route in app.router.routes()}

    assert {("GET", "/"), ("GET", "/ws")} <= routes
    assert {("POST", "/family/cue"), ("GET", "/family/state")} <= routes


def test_check_with_nothing_answering_cannot_say_rather_than_fail(tmp_path, capsys):
    # Port 9 is discard: nothing serves HTTP there, and nothing is bound here.
    status = showstopper_cli.main(
        ["check", "--url", "http://127.0.0.1:9/", "--shots", str(tmp_path / "shots")])

    assert status == showstopper_cli.CANNOT_SAY == 3
    assert "nothing answers at http://127.0.0.1:9/" in capsys.readouterr().err
    assert not (tmp_path / "shots").exists()


def test_check_with_a_broken_pytest_cannot_say_rather_than_fail(tmp_path, monkeypatch, capsys):
    # Python exits 1 for a module it cannot run: a failed assertion's status.
    class Answering:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(showstopper_cli.urllib.request, "urlopen", lambda *a, **k: Answering())
    broken = showstopper_cli.subprocess.CompletedProcess([], 1, "", "No module named pytest.__main__")
    monkeypatch.setattr(showstopper_cli.subprocess, "run", lambda *a, **k: broken)

    status = showstopper_cli.main(
        ["check", "--url", "http://127.0.0.1:18410/", "--shots", str(tmp_path / "shots")])

    assert status == showstopper_cli.CANNOT_SAY
    assert "pytest does not run here" in capsys.readouterr().err
