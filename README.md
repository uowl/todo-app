# todo — a simple CLI todo app

A small command-line todo list. Tasks can have priorities, due dates and tags, and are saved to a JSON file.

## Stack

- **Python 3.10+, standard library only.** It uses `argparse` for the CLI, `dataclasses` and `json` for storage, and `unittest` for tests.
- There are no runtime dependencies. You also don't need anything installed to run the tests.

## Run

From the project root:

```sh
python -m todo add "Write report" -p high -d 2026-11-15 -t work
python -m todo list
```

Optionally, install it as a `todo` command:

```sh
pip install -e .
todo list
```

## Commands

| Command | Description |
|---|---|
| `todo add TITLE... [-p low\|medium\|high] [-d YYYY-MM-DD] [-t TAG]...` | Add a task. You can repeat `-t` to add several tags. |
| `todo list` / `todo ls` / `todo` | List pending tasks. |
| `todo list -a` / `--done` | List all tasks, or only completed tasks. |
| `todo list -t TAG` / `-p PRIORITY` | Show only tasks with a given tag or priority. |
| `todo search TEXT` | Search all task titles and tags. Case doesn't matter. |
| `todo done ID...` / `todo undo ID...` | Mark tasks as completed, or as pending again. |
| `todo edit ID [--title T] [-p P] [-d DATE \| --no-due] [-t TAG... \| --no-tags]` | Edit a task. Passing `-t` replaces all of its tags. |
| `todo rm ID...` | Delete tasks. |
| `todo clear` | Delete all completed tasks. |
| `todo restore` | Undo the last `rm` / `clear` (brings back the whole batch). |
| `todo stats` | Show total, pending, done and overdue counts. |

Lists are sorted with pending tasks first, then by priority (high first), then by due date, then by ID. Priority shows as `!!!` (high), `!!` (medium) or `!` (low). Tasks past their due date are marked `OVERDUE`.

Example output:

```
  1 [ ] !!! Write report  (due 2026-11-15)  #work
  2 [ ] !!  Buy milk  #home
```

## Where data is stored

The CLI looks for the data file in this order:
1. `--file PATH` (put it before the command: `todo --file x.json list`)
2. The `TODO_FILE` environment variable
3. `~/.todo.json`

## Exit codes

- `0` — success
- `1` — app error, such as an unknown ID, a bad date or a corrupt file
- `2` — invalid command-line usage

## Tests

```sh
python -m unittest discover -s tests -t . -v
```

## Due dates and filters

`--due` accepts `YYYY-MM-DD`, `today`, `tomorrow`, `+3d`, `+2w`, or a weekday name (`fri`, `monday`; next occurrence). `todo ls --overdue` shows only overdue tasks.

## Sorting, colour and export
- `todo ls --sort priority|due|created` (default `priority`).
- Output is coloured (overdue/high priority red, done dimmed) only when writing to a terminal; set `NO_COLOR=1` to disable.
- `todo export [-f json|csv|markdown]` prints all tasks to stdout (redirect to a file).
- `todo import FILE` (or `-` for stdin) adds tasks from a JSON export or data file under fresh IDs; invalid input imports nothing.
