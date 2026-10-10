# 01 — Onboarding

> **Runtime: hermetic.** No port, no network, no browser: Textual runs
> headless here. If this page passes, your checkout is built.

ShowStopper is a stopwatch for timing a show: a column of independent timers in
the terminal, one for each thing being timed. This page is the first build, and
it is executed by the test command, so the examples below ran on your machine.

## What you need

Python 3.9 or newer, and [PDM](https://pdm-project.org):

```python
>>> import sys
>>> sys.version_info >= (3, 9)
True

```

## The first build

```sh
pdm install
```

That installs the app and its `dev` group: Textual's developer tools, which
provide the `textual` command, and pytest. `pdm install --prod` leaves the
group out, and then `pdm start` fails with `textual: command not found`
(`'textual' is not recognized` on Windows). `python stopwatch.py` runs the app
without it.

## Proving it worked

The app boots headless with three stopwatches, all at zero:

```python
>>> import asyncio
>>> from stopwatch import StopwatchApp, TimeDisplay
>>> async def boot():
...     app = StopwatchApp()
...     async with app.run_test():
...         return [display.value for display in app.query(TimeDisplay)]
>>> asyncio.run(boot())
['00:00:00.00', '00:00:00.00', '00:00:00.00']

```

## Running it

```sh
pdm start    # in this terminal
pdm serve    # in a browser, through textual-serve
```

`showstopper serve --host H --port P --state DIR` serves it in a browser on
exactly that address, and `showstopper check --url U --shots DIR` checks a
ShowStopper already served there: that the address streams this app, and that
the stopwatch behaves, with the suite's pictures written to `DIR`. The two are
the performing family's demo contract, which the qm corpus declares once for
every member.

## Running the tests

```sh
pdm test
```

That runs the suite and these pages:

```python
>>> import re
>>> from pathlib import Path
>>> scripts = Path("pyproject.toml").read_text().split("[tool.pdm.scripts]")[1]
>>> dict(re.findall(r'^(\w+) = "(.*)"$', scripts, re.M))["test"]
'pytest tests walkthrough --doctest-glob=*.md'

```

Both paths are named on purpose: pytest ignores `testpaths` as soon as it is
given a path, so pages wired that way would be collected by nobody.

The same run redraws the pictures in `02-the-stopwatch.md`. If `git status`
shows one changed after a change of yours, the screen changed: commit the
picture with the change.
