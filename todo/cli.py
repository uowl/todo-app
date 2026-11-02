"""argparse-based command-line interface."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence, TextIO

from . import __version__
from .store import PRIORITIES, Task, TodoError, TodoStore

PRIORITY_MARK = {"high": "!!!", "medium": "!! ", "low": "!  "}


def format_task(task: Task) -> str:
    box = "[x]" if task.done else "[ ]"
    parts = [f"{task.id:>3} {box} {PRIORITY_MARK.get(task.priority, '   ')} {task.title}"]
    if task.due:
        parts.append(f"(due {task.due}{' OVERDUE' if task.is_overdue() else ''})")
    if task.tags:
        parts.append(" ".join(f"#{t}" for t in task.tags))
    return "  ".join(parts)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="todo", description="A simple command-line todo list.")
    p.add_argument("--file", help="todo JSON file (default: $TODO_FILE or ~/.todo.json)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    a = sub.add_parser("add", help="add a task")
    a.add_argument("title", nargs="+", help="task title")
    a.add_argument("-p", "--priority", default="medium", choices=PRIORITIES)
    a.add_argument("-d", "--due", help="due date YYYY-MM-DD")
    a.add_argument("-t", "--tag", action="append", dest="tags", help="tag (repeatable)")

    ls = sub.add_parser("list", aliases=["ls"], help="list tasks (pending by default)")
    g = ls.add_mutually_exclusive_group()
    g.add_argument("-a", "--all", action="store_const", dest="status", const="all",
                   help="show all tasks")
    g.add_argument("--done", action="store_const", dest="status", const="done",
                   help="show completed tasks only")
    ls.add_argument("-t", "--tag", help="filter by tag")
    ls.add_argument("-p", "--priority", choices=PRIORITIES, help="filter by priority")
    ls.set_defaults(status="pending")

    s = sub.add_parser("search", help="search task titles (all tasks)")
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
    due.add_argument("-d", "--due", help="new due date YYYY-MM-DD")
    due.add_argument("--no-due", action="store_true", help="remove the due date")
    tags = e.add_mutually_exclusive_group()
    tags.add_argument("-t", "--tag", action="append", dest="tags", help="replace tags (repeatable)")
    tags.add_argument("--no-tags", action="store_true", help="remove all tags")

    sub.add_parser("clear", help="delete all completed tasks")
    sub.add_parser("stats", help="show task counts")
    return p


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
        t = store.add(" ".join(args.title), args.priority, args.due, args.tags)
        print(f"Added task {t.id}: {t.title}", file=out)
    elif cmd in ("list", "ls", "search"):
        if cmd == "search":
            tasks = store.query(status="all", text=" ".join(args.text))
        else:
            tasks = store.query(status=args.status, tag=args.tag, priority=args.priority)
        if not tasks:
            print("No tasks.", file=out)
        for t in tasks:
            print(format_task(t), file=out)
    elif cmd in ("done", "undo"):
        verb = "Completed" if cmd == "done" else "Reopened"
        for i in _checked_ids(store, args.ids):
            t = store.set_done(i, cmd == "done")
            print(f"{verb} task {t.id}: {t.title}", file=out)
    elif cmd == "rm":
        for i in _checked_ids(store, args.ids):
            t = store.remove(i)
            print(f"Removed task {t.id}: {t.title}", file=out)
    elif cmd == "edit":
        tags = [] if args.no_tags else args.tags
        t = store.edit(args.id, title=args.title, priority=args.priority, due=args.due,
                       tags=tags, clear_due=args.no_due)
        print(f"Updated: {format_task(t)}", file=out)
    elif cmd == "clear":
        print(f"Removed {store.clear_done()} completed task(s).", file=out)
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
