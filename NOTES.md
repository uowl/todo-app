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
- Commands that take several IDs (`done 1 99`, `rm 1 99`) handle them one at a time. Valid IDs before the bad one have already been changed and saved when the error appears.
- There is no file locking, so two `todo` processes running at the same moment could lose an update. That's unlikely for one person using a CLI.
- The `OVERDUE` marker uses the local date.

## Backlog
- Validate all IDs before applying a multi-ID command, so it changes all or nothing.
- Natural-language due dates ("tomorrow", "fri").
- Coloured output (ANSI), with a `--no-color` option or support for `NO_COLOR`.
- Subtasks / notes; recurring tasks.
- `todo export` / `import` (CSV / Markdown).
- Undo history for the last destructive action (`rm`, `clear`).
- Sort options (`--sort due|created`).
- CI workflow (GitHub Actions) running the tests on several Python versions.
