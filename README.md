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
| `todo edit ID [--title T] [-p P] [-d DATE \| --no-due] [-t TAG... \| --no-tags]` | Edit a task. `-t` replaces all tags; `--add-tag TAG` appends without replacing; `--rm-tag TAG` removes one. |
| `todo rename-tag OLD NEW` | Rename a tag on every task (merges if NEW already exists). |
| `todo rm ID...` | Delete tasks. |
| `todo clear` | Delete all completed tasks. |
| `todo restore` | Undo the last `rm` / `clear` batch; repeat to step back (20 levels). |
| `todo add --parent ID TITLE` | Add a subtask (one level). `rm` of a parent also removes its subtasks; `show` lists them. |
| `todo stats` | Show total, pending, done and overdue counts. |
| `todo next` | Show the single most urgent pending task. |
| `todo ls --untagged` | Only tasks with no tags. |
| `todo ls --undated` | Only tasks with no due date. |
| `todo ls --reverse` | Reverse the sort order. |
| `todo ls --json` | Print matching tasks as JSON (for scripts). |
| `todo ls --limit N` | Show at most N tasks (prints "showing N of M" if truncated). |
| `todo tags` | List tags with pending/total counts. |

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

`--due` accepts `YYYY-MM-DD`, `today`, `tomorrow`, `+3d`, `+2w`, or a weekday name (`fri`, `monday`; next occurrence). `todo ls --overdue` shows only overdue tasks; `todo ls --due-by +1w` shows dated tasks due on or before that date.

## Notes

- `todo add "Write report" -n "details..."`, `todo edit 1 -n "new"` (empty string clears), `todo show 1` prints the full task and note. `search` also matches notes.

## Sorting, colour and export
- `todo ls --sort priority|due|created` (default `priority`).
- Output is coloured (overdue/high priority red, done dimmed) only when writing to a terminal; set `NO_COLOR=1` to disable.
- `todo export [-f json|csv|markdown]` prints all tasks to stdout (redirect to a file). CSV and Markdown exports include notes. `ls` marks tasks that have a note with `[note]`.
- `todo import FILE` (or `-` for stdin) adds tasks from a JSON export or data file under fresh IDs; invalid input imports nothing.

## Recurring tasks

- `todo add "Water plants" -d tomorrow -r weekly` (`daily`, `weekly`, `monthly`). Completing it with `todo done ID` also creates the next occurrence (due date advanced from the old one; month-ends are clamped). `todo edit ID -r none` stops repeating.

## Web GUI

`todo web [--port 8765] [--host 127.0.0.1] [--open]` serves a local single-page app on the same data file
Shortcuts: `n` new task, `/` focus search. In the Done view, "Clear completed" removes finished tasks (undo toast restores them).

Appearance (🎨 button): five themes (System, Light, Dark, Midnight, Sepia) and six accent colours, remembered in the browser. The header shows today's date; the **Calendar** tab shows a month grid with task dots, lets you pick a day to see/add its tasks, and the task dialog has a date picker.
(`--file`/`TODO_FILE` honoured). It follows Apple's design language: SF system font, translucent blurred
header, segmented Pending/Done/All control, rounded inset-grouped list, priority-coloured circle checkboxes,
sheet-style edit dialog, undo toast after delete, automatic light/dark mode. Supports add, edit, complete,
delete/undo, search, subtasks, tags, due dates and repeats. It binds to localhost only, rejects foreign
`Host` headers, and requires JSON content-type on writes. JSON API: `/api/tasks` (GET/POST),
`/api/tasks/ID` (PATCH/DELETE), `/api/restore`, `/api/clear` (POST).

### Managing the web service (Windows / PowerShell)

- `./run.ps1 [-Port 8765] [-BindHost 127.0.0.1] [-File path] [-Open]` starts `todo web` in the background (PID in `.todo-web.pid`, logs in `.todo-web.log`).
- `./stop.ps1` stops it.
