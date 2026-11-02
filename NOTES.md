# NOTES

## Plan
1. Use only the standard library (argparse, JSON, unittest), so there's nothing to install.
2. `todo/store.py` holds the `Task` dataclass and `TodoStore`, which loads, validates, changes and saves tasks.
3. `todo/cli.py` is a thin argparse layer that calls `TodoStore` and formats the output.
4. Test the store and the CLI directly, plus one subprocess test that runs `python -m todo`.

## Decisions / assumptions
- **Storage:** a single JSON file at `~/.todo.json`, which `TODO_FILE` or `--file` can override. Writes are atomic: the data goes to a temp file first, which then replaces the real file.
- **IDs:** IDs only go up and are never reused. `next_id` is stored in the file, and on load it is checked against the highest existing ID.
- **Defaults:** priority is one of low/medium/high, and new tasks default to medium. Due dates must be ISO `YYYY-MM-DD`.
- **Tags:** stored in lowercase. A leading `#` is removed and duplicates are dropped.
- **Unknown fields** in the JSON file are ignored, so older versions can still read files written by newer ones.
- **Bare `todo`** with no command runs `todo list`.
- **Edits are validated first:** `edit` checks every field before changing anything, so one bad field leaves the task unchanged.
- **Unit tests use `unittest`** instead of pytest, because pytest isn't installed and the goal was zero dependencies. pytest can still run these tests.

## Known issues
- There is no file locking, so two `todo` processes running at the same moment could lose an update. That's unlikely for one person using a CLI.
- The `OVERDUE` marker uses the local date.

## Backlog
- Subtasks / notes; recurring tasks.
- `todo import`.
- Undo history for the last destructive action (`rm`, `clear`).
- CI workflow (GitHub Actions) running the tests on several Python versions.

## Test results (testing pass)
- Ran the suite and exercised the real CLI (`python -m todo`) by hand: add/list/ls/search/done/undo/edit/rm/clear/stats, invalid priority/date, empty titles, corrupt or wrong-shape JSON, unicode, dash-leading titles, `--file` in a new directory.
- **Bug fixed:** multi-ID `done`/`undo`/`rm` applied partially when a later ID was missing or duplicated. IDs are now de-duplicated and validated first (all-or-nothing).
- Added 6 CLI tests for this and other edge cases. All tests pass.
- Minor: error text for wrongly-shaped JSON files is technical (e.g. "'list' object has no attribute 'get'") but the exit code is 1 and nothing crashes.

## Improvement round 1
- Added relative due dates (today/tomorrow/+Nd/+Nw/weekday), `ls --overdue`, and a clearer corrupt-file error. Tests updated/added; all pass.

## Improvement round 2
- Added `ls --sort`, ANSI colour (tty only, honours NO_COLOR), `export` (json/csv/markdown). 37 tests pass.
