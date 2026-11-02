"""argparse-based command-line interface."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict
from typing import Sequence, TextIO

from . import __version__
from .store import PRIORITIES, normalize_tags, REPEATS, SORTS, Task, TodoError, TodoStore

PRIORITY_MARK = {"high": "!!!", "medium": "!! ", "low": "!  "}


def use_color(out: TextIO) -> bool:
    """Colour only on a real terminal, and never when NO_COLOR is set."""
    return not os.environ.get("NO_COLOR") and getattr(out, "isatty", lambda: False)()


def _paint(text: str, code: str, color: bool) -> str:
    return f"[{code}m{text}[0m" if color else text


def format_task(task: Task, color: bool = False) -> str:
    box = "[x]" if task.done else "[ ]"
    mark = PRIORITY_MARK.get(task.priority, "   ")
    if task.priority == "high" and not task.done:
        mark = _paint(mark, "31", color)
    line = f"{task.id:>3} {box} {mark} {task.title}"
    parts = [_paint(line, "2", color) if task.done else line]
    if task.due:
        if task.is_overdue():
            parts.append(_paint(f"(due {task.due} OVERDUE)", "31;1", color))
        else:
            parts.append(f"(due {task.due})")
    if task.tags:
        parts.append(" ".join(f"#{t}" for t in task.tags))
    if task.repeat:
        parts.append(f"(repeats {task.repeat})")
    if task.parent is not None:
        parts.append(f"(subtask of {task.parent})")
    if task.note:
        parts.append("[note]")
    return "  ".join(parts)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="todo", description="A simple command-line todo list.")
    p.add_argument("--file", help="todo JSON file (default: $TODO_FILE or ~/.todo.json)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    a = sub.add_parser("add", help="add a task")
    a.add_argument("title", nargs="+", help="task title")
    a.add_argument("-p", "--priority", default="medium", choices=PRIORITIES)
    a.add_argument("-d", "--due", help="due: YYYY-MM-DD, today, tomorrow, +3d, +2w, weekday")
    a.add_argument("-t", "--tag", action="append", dest="tags", help="tag (repeatable)")
    a.add_argument("-n", "--note", default="", help="longer free-text note")
    a.add_argument("-r", "--repeat", choices=REPEATS, help="recur when completed")
    a.add_argument("--parent", type=int, metavar="ID", help="make this a subtask of task ID")

    ls = sub.add_parser("list", aliases=["ls"], help="list tasks (pending by default)")
    g = ls.add_mutually_exclusive_group()
    g.add_argument("-a", "--all", action="store_const", dest="status", const="all",
                   help="show all tasks")
    g.add_argument("--done", action="store_const", dest="status", const="done",
                   help="show completed tasks only")
    ls.add_argument("--overdue", action="store_true", help="only overdue tasks")
    ls.add_argument("--due-by", metavar="DATE", help="only tasks due on or before DATE (same formats as add -d)")
    ls.add_argument("--undated", action="store_true", help="only tasks with no due date")
    ls.add_argument("-t", "--tag", help="filter by tag")
    ls.add_argument("--untagged", action="store_true", help="only tasks with no tags")
    ls.add_argument("-p", "--priority", choices=PRIORITIES, help="filter by priority")
    ls.add_argument("--sort", choices=SORTS, default="priority", help="sort order")
    ls.add_argument("--reverse", action="store_true", help="reverse the sort order")
    ls.add_argument("--limit", type=int, metavar="N", help="show at most N tasks")
    ls.add_argument("--json", action="store_true", help="print matching tasks as JSON (for scripts)")
    ls.set_defaults(status="pending")
    sub.add_parser("next", help="show the single most urgent pending task")

    s = sub.add_parser("search", help="search titles, tags and notes (all tasks)")
    s.add_argument("text", nargs="+")

    for name, help_ in (("done", "mark task(s) complete"), ("undo", "mark task(s) pending"),
                        ("rm", "delete task(s)")):
        c = sub.add_parser(name, help=help_)
        c.add_argument("ids", nargs="+", type=int, metavar="ID")

    e = sub.add_parser("edit", help="edit a task")
    e.add_argument("id", type=int)
    e.add_argument("--title")
    e.add_argument("-p", "--priority", choices=PRIORITIES)
    due = e.add_mutually_exclusive_group()
    due.add_argument("-d", "--due", help="new due date (same formats as add)")
    due.add_argument("--no-due", action="store_true", help="remove the due date")
    tags = e.add_mutually_exclusive_group()
    tags.add_argument("-t", "--tag", action="append", dest="tags", help="replace tags (repeatable)")
    tags.add_argument("--no-tags", action="store_true", help="remove all tags")
    tags.add_argument("--add-tag", action="append", dest="add_tags", metavar="TAG",
                      help="add a tag, keeping existing ones (repeatable)")
    tags.add_argument("--rm-tag", action="append", dest="rm_tags", metavar="TAG",
                      help="remove a tag, keeping the others (repeatable)")

    e.add_argument("-n", "--note", help="set the note (empty string clears it)")
    e.add_argument("-r", "--repeat", choices=REPEATS + ("none",), help="set recurrence (none clears)")

    sh = sub.add_parser("show", help="show one task in full, including its note")
    sh.add_argument("id", type=int)

    sub.add_parser("restore", help="undo the last rm/clear")
    sub.add_parser("clear", help="delete all completed tasks")
    ex = sub.add_parser("export", help="export all tasks to stdout")
    ex.add_argument("-f", "--format", choices=("json", "csv", "markdown"), default="json")

    im = sub.add_parser("import", help="import tasks from a JSON export (file or - for stdin)")
    im.add_argument("source", metavar="FILE")

    sub.add_parser("stats", help="show task counts")
    rt = sub.add_parser("rename-tag", help="rename a tag on all tasks (merges if NEW exists)")
    rt.add_argument("old")
    rt.add_argument("new")
    sub.add_parser("tags", help="list tags with pending/total counts")
    return p


def export_tasks(tasks: Sequence[Task], fmt: str, out: TextIO) -> None:
    if fmt == "json":
        json.dump([asdict(t) for t in tasks], out, indent=2)
        print(file=out)
    elif fmt == "csv":
        w = csv.writer(out, lineterminator=chr(10))
        w.writerow(["id", "title", "done", "priority", "due", "tags", "note", "repeat", "parent"])
        for t in tasks:
            w.writerow([t.id, t.title, "yes" if t.done else "no", t.priority, t.due or "",
                        ",".join(t.tags), t.note, t.repeat or "", t.parent or ""])
    else:
        ids = {t.id for t in tasks}
        ordered = [t for t in tasks if t.parent not in ids]
        for t in list(ordered):
            ordered[ordered.index(t) + 1:ordered.index(t) + 1] = [c for c in tasks if c.parent == t.id]
        for t in ordered:
            ind = "  " if t.parent in ids else ""
            extra = f" (due {t.due})" if t.due else ""
            extra += "".join(f" #{g}" for g in t.tags)
            print(f"{ind}- [{'x' if t.done else ' '}] {t.title}{extra}", file=out)
            for line in t.note.splitlines():
                print(f"{ind}  > {line}", file=out)


def _checked_ids(store: TodoStore, ids: Sequence[int]) -> list[int]:
    """Dedupe IDs and verify they all exist, so multi-ID commands are all-or-nothing."""
    unique = list(dict.fromkeys(ids))
    for i in unique:
        store.get(i)
    return unique


def run(args: argparse.Namespace, out: TextIO) -> int:
    store = TodoStore(args.file)
    cmd = args.command

    if cmd == "add":
        t = store.add(" ".join(args.title), args.priority, args.due, args.tags, args.note, args.repeat,
                      args.parent)
        print(f"Added task {t.id}: {t.title}", file=out)
    elif cmd in ("list", "ls", "search"):
        if cmd == "search":
            tasks = store.query(status="all", text=" ".join(args.text))
        else:
            tasks = store.query(status=args.status, tag=args.tag, priority=args.priority,
                               overdue=args.overdue, sort=args.sort, due_by=args.due_by, untagged=args.untagged,
                               undated=args.undated)
        if cmd != "search" and args.reverse:
            tasks = tasks[::-1]
        if cmd != "search" and args.limit is not None:
            if args.limit < 1:
                raise TodoError("--limit must be at least 1")
            total = len(tasks)
            tasks = tasks[:args.limit]
        else:
            total = len(tasks)
        if cmd != "search" and args.json:
            export_tasks(tasks, "json", out)
            return 0
        if not tasks:
            print("No tasks.", file=out)
        shown = {t.id for t in tasks}
        tops = [t for t in tasks if t.parent not in shown]
        for t in tops:  # subtasks are grouped, indented, under a listed parent
            print(format_task(t, use_color(out)), file=out)
            for c in tasks:
                if c.parent == t.id:
                    print("    " + format_task(c, use_color(out)), file=out)
        if len(tasks) < total:
            print(f"(showing {len(tasks)} of {total})", file=out)
    elif cmd == "next":
        # Default sort is priority, then due date: the first pending task is the most urgent.
        tasks = store.query(status="pending")[:1]
        print(format_task(tasks[0], use_color(out)) if tasks else "Nothing to do!", file=out)
    elif cmd in ("done", "undo"):
        verb = "Completed" if cmd == "done" else "Reopened"
        for i in _checked_ids(store, args.ids):
            if cmd == "done":
                t, nxt = store.complete(i)
            else:
                t, nxt = store.set_done(i, False), None
            print(f"{verb} task {t.id}: {t.title}", file=out)
            if nxt:
                print(f"  Next {nxt.repeat} occurrence: task {nxt.id} (due {nxt.due})", file=out)
    elif cmd == "rm":
        removed = []
        mark = len(store.history)
        for i in _checked_ids(store, args.ids):
            if i not in {t.id for t in removed}:  # may already be gone as a subtask
                removed.extend([store.get(i), *store.subtasks(i)])
                store.remove(i)
        del store.history[mark:]  # collapse per-id batches into one
        store.trash = removed  # restore brings back the whole batch
        store.save()
        for t in removed:
            print(f"Removed task {t.id}: {t.title}", file=out)
    elif cmd == "edit":
        tags = [] if args.no_tags else args.tags
        if args.add_tags:
            tags = [*store.get(args.id).tags, *args.add_tags]
        if args.rm_tags:
            drop = set(normalize_tags(args.rm_tags))
            tags = [g for g in store.get(args.id).tags if g not in drop]
            if not tags:  # empty list would look like "no change"; use the explicit clear path
                args.no_tags = True
        if all(v in (None, False) for v in (args.title, args.priority, args.due, tags, args.no_tags, args.no_due, args.note, args.repeat)):
            raise TodoError("nothing to edit; pass --title, -p, -d/--no-due, -t/--no-tags, -n or -r")
        t = store.edit(args.id, title=args.title, priority=args.priority, due=args.due,
                       tags=tags, clear_due=args.no_due, note=args.note, repeat=args.repeat)
        print(f"Updated: {format_task(t)}", file=out)
    elif cmd == "show":
        t = store.get(args.id)
        print(format_task(t, use_color(out)), file=out)
        print(f"    created: {t.created}", file=out)
        if t.repeat:
            print(f"    repeats: {t.repeat}", file=out)
        if t.completed:
            print(f"    completed: {t.completed}", file=out)
        subs = store.subtasks(t.id)
        for sub_t in subs:
            print("    - " + format_task(sub_t).strip(), file=out)
        if t.note:
            print("    note: " + t.note.replace(chr(10), chr(10) + " " * 10), file=out)
    elif cmd == "restore":
        for t in store.restore():
            print(f"Restored task {t.id}: {t.title}", file=out)
    elif cmd == "export":
        export_tasks(store.query(status="all", sort="created"), args.format, out)
    elif cmd == "import":
        try:
            if args.source == "-":
                data = json.load(sys.stdin)
            else:
                with open(args.source, encoding="utf-8") as fh:
                    data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise TodoError(f"could not read {args.source}: {exc}") from None
        if isinstance(data, dict):  # also accept a todo data file
            data = data.get("tasks", [])
        if not isinstance(data, list):
            raise TodoError("import file must contain a JSON list of tasks")
        print(f"Imported {len(store.import_tasks(data))} task(s).", file=out)
    elif cmd == "clear":
        print(f"Removed {store.clear_done()} completed task(s).", file=out)
    elif cmd == "rename-tag":
        n = store.rename_tag(args.old, args.new)
        print(f"Renamed #{args.old.lstrip('#').lower()} to #{args.new.lstrip('#').lower()} on {n} task(s).", file=out)
    elif cmd == "tags":
        counts: dict[str, list[int]] = {}
        for t in store.tasks:
            for g in t.tags:
                c = counts.setdefault(g, [0, 0])
                c[1] += 1
                c[0] += not t.done
        if not counts:
            print("No tags.", file=out)
        for g in sorted(counts):
            print(f"#{g}  {counts[g][0]} pending / {counts[g][1]} total", file=out)
    elif cmd == "stats":
        total = len(store.tasks)
        done = sum(t.done for t in store.tasks)
        overdue = sum(t.is_overdue() for t in store.tasks)
        print(f"{total} total, {total - done} pending, {done} done, {overdue} overdue", file=out)
    return 0


def main(argv: Sequence[str] | None = None, out: TextIO | None = None,
         err: TextIO | None = None) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:  # bare `todo` (optionally with --file) lists pending tasks
        args = parser.parse_args([*argv, "list"])
    try:
        return run(args, out)
    except TodoError as exc:
        print(f"error: {exc}", file=err)
        return 1
