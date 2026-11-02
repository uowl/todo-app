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
- Subtask follow-ups: import/export of `parent`, indented display in `ls`.
- `todo import`.
- Multi-level undo history (only the last rm/clear is restorable now).

## Test results (testing pass)
- Ran the suite and exercised the real CLI (`python -m todo`) by hand: add/list/ls/search/done/undo/edit/rm/clear/stats, invalid priority/date, empty titles, corrupt or wrong-shape JSON, unicode, dash-leading titles, `--file` in a new directory.
- **Bug fixed:** multi-ID `done`/`undo`/`rm` applied partially when a later ID was missing or duplicated. IDs are now de-duplicated and validated first (all-or-nothing).
- Added 6 CLI tests for this and other edge cases. All tests pass.
- Minor: error text for wrongly-shaped JSON files is technical (e.g. "'list' object has no attribute 'get'") but the exit code is 1 and nothing crashes.

## Improvement round 1
- Added relative due dates (today/tomorrow/+Nd/+Nw/weekday), `ls --overdue`, and a clearer corrupt-file error. Tests updated/added; all pass.

## Improvement round 2
- Added `ls --sort`, ANSI colour (tty only, honours NO_COLOR), `export` (json/csv/markdown). 37 tests pass.

## Improvement round 3
- Added `todo restore`: undoes the last `rm`/`clear` batch (kept in a `trash` list in the JSON file; older files load fine). 39 tests pass.

## Improvement round 4
- `search` now also matches tags; `edit` with no fields errors instead of silently succeeding; `done`/`undo` on a task already in that state no longer rewrites the completion timestamp. 42 tests pass.

## Improvement round 5
- Added `todo import FILE|-` (JSON list from `export json`, or a todo data file). IDs are reassigned; validation is all-or-nothing. 48 tests pass. Removed from backlog: import.

## Improvement round 6
- Added task notes: `add -n/--note`, `edit -n` (empty clears), new `todo show ID`; search and import/export cover notes. 49 tests pass. Removed from backlog: notes (subtasks and recurring still open).

## Improvement round 7
- Notes now appear in csv/markdown exports; `ls` shows a `[note]` marker; `edit` no-field error mentions `-n`. 50 tests pass.

## Improvement round 8
- Added recurring tasks (`add/edit -r daily|weekly|monthly`); `done` spawns the next occurrence. Next due is computed from the old due date (or today if none), so finishing late still yields a past-due next task. 57 tests pass. Removed from backlog: recurring (subtasks still open).

## Improvement round 9
- Added `ls --due-by DATE` (accepts relative dates; bad date gives a clean error). Backlog still: subtasks, multi-level undo, CI.

## Improvement round 10
- Added `todo tags` (pending/total per tag) and a GitHub Actions workflow (`.github/workflows/tests.yml`, Python 3.10-3.13). 59 tests pass. Backlog: subtasks, multi-level undo.

## Improvement round 11 (no changes)


## Improvement round 12
- Added `edit --add-tag` (append tags without replacing). Backlog: subtasks, multi-level undo.

## Improvement round 13
- Added `edit --rm-tag` and `todo rename-tag OLD NEW` (merges into existing tag). Backlog: subtasks, multi-level undo.

## Improvement round 14
- `ls --limit` now prints "(showing N of M)" when truncated. Backlog: subtasks, multi-level undo.

## Improvement round 15
- Added `ls --untagged`. Backlog: subtasks, multi-level undo.

## Improvement round 16
- Added `ls --undated`. Backlog: subtasks, multi-level undo.

## Improvement round 17
- Added `ls --reverse`. Backlog: subtasks, multi-level undo.

## Improvement round 18
- Added `ls --json` for scripting (respects filters/sort/limit). Backlog: subtasks, multi-level undo.

## Improvement round 19 (no changes)
- Reviewed; 79 tests pass, input validation verified. Backlog: subtasks, multi-level undo.

## Improvement round 20 (no changes)
- Reviewed; 79 tests pass. Backlog: subtasks, multi-level undo.

## Improvement round 21 (no changes)
- Reviewed; 79 tests pass, tree clean. Remaining backlog (subtasks, multi-level undo) is larger than a focused tweak.

## Improvement round 22 (no changes)
- Reviewed; 79 tests pass, tree clean. Backlog (subtasks, multi-level undo) remains larger than a focused tweak.

## Improvement round 23 (no changes)
- Reviewed; 79 tests pass. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 25 (no changes)
- Reviewed; 79 tests pass. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 26 (no changes)
- Reviewed; 79 tests pass. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 27 (no changes)
- Reviewed; 79 tests pass. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 28 (no changes)
- Reviewed; 79 tests pass, tree clean. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 29 (no changes)
- Reviewed; 79 tests pass, tree clean. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 30 (no changes)
- Reviewed; 79 tests pass. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 31
- Fixed `search` help text to mention notes. 79 tests pass. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 32 (no changes)
- Reviewed; 79 tests pass. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 33 (no changes)
- Reviewed; 79 tests pass. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 34 (no changes)
- Reviewed; 79 tests pass. Backlog (subtasks, multi-level undo) unchanged.

## Improvement round 35
- Added one-level subtasks: `add --parent ID`, shown in `ls` as "(subtask of N)" and under `show`; `rm` cascades to subtasks (restorable). 81 tests pass. Remaining: parent in import/export, indented `ls`, multi-level undo.

## Improvement round 36
- Subtasks now round-trip: `export json` keeps `parent`, `import` re-links parents to new IDs, csv has a `parent` column, markdown indents subtasks. Tests pass. Remaining: indented `ls`, multi-level undo.

## Improvement round 37
- Multi-level undo: `restore` steps back through up to 20 rm/clear batches (`trash_history` in the JSON; legacy `trash` still loads). `ls` now groups/indents subtasks under a listed parent. 115 tests pass. Backlog now empty.
