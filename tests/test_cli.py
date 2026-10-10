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
    assert made["command"] == (
        f'"{sys.executable}" "{showstopper_cli.HERE / "stopwatch.py"}"')
    assert (tmp_path / "s").is_dir()


def test_check_with_nothing_answering_cannot_say_rather_than_fail(tmp_path, capsys):
    # Port 9 is discard: nothing serves HTTP there, and nothing is bound here.
    status = showstopper_cli.main(
        ["check", "--url", "http://127.0.0.1:9/", "--shots", str(tmp_path / "shots")])

    assert status == showstopper_cli.CANNOT_SAY == 3
    assert "nothing answers at http://127.0.0.1:9/" in capsys.readouterr().err
    assert not (tmp_path / "shots").exists()
