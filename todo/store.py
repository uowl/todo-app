"""Task model and JSON-file persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

PRIORITIES = ("low", "medium", "high")
DEFAULT_FILE = Path.home() / ".todo.json"
ENV_VAR = "TODO_FILE"
SORTS = ("priority", "due", "created")
REPEATS = ("daily", "weekly", "monthly")


class TodoError(Exception):
    """User-facing error (bad id, bad input, corrupt file...)."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    priority: str = "medium"
    due: str | None = None  # ISO date YYYY-MM-DD
    tags: list[str] = field(default_factory=list)
    created: str = field(default_factory=_now)
    completed: str | None = None
    note: str = ""
    repeat: str | None = None  # daily/weekly/monthly: completing spawns the next occurrence

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)

    def is_overdue(self, today: date | None = None) -> bool:
        if self.done or not self.due:
            return False
        try:
            return date.fromisoformat(self.due) < (today or date.today())
        except ValueError:  # hand-edited file with a malformed date
            return False


def validate_priority(value: str) -> str:
    value = value.lower()
    if value not in PRIORITIES:
        raise TodoError(f"invalid priority {value!r}; choose from {', '.join(PRIORITIES)}")
    return value


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def parse_due(value: str, today: date | None = None) -> date:
    """Parse YYYY-MM-DD, today/tomorrow, +Nd/+Nw, or a weekday name (next occurrence)."""
    today = today or date.today()
    v = value.strip().lower()
    if v == "today":
        return today
    if v == "tomorrow":
        return today + timedelta(days=1)
    m = re.fullmatch(r"\+(\d+)([dw])", v)
    if m:
        return today + timedelta(days=int(m.group(1)) * (7 if m.group(2) == "w" else 1))
    if v[:3] in WEEKDAYS and v in {w for d in WEEKDAYS for w in (d, _FULL[d])}:
        ahead = (WEEKDAYS.index(v[:3]) - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)
    return date.fromisoformat(v)


_FULL = {"mon": "monday", "tue": "tuesday", "wed": "wednesday", "thu": "thursday",
         "fri": "friday", "sat": "saturday", "sun": "sunday"}


def validate_due(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        return parse_due(value).isoformat()
    except ValueError:
        raise TodoError(f"invalid due date {value!r}; use YYYY-MM-DD, today, tomorrow, "
                        "+3d, +2w or a weekday") from None


def validate_repeat(value: str | None) -> str | None:
    if value is None or value == "" or value == "none":
        return None
    value = value.lower()
    if value not in REPEATS:
        raise TodoError(f"invalid repeat {value!r}; choose from {', '.join(REPEATS)}")
    return value


def next_due(base: date, repeat: str) -> date:
    if repeat == "daily":
        return base + timedelta(days=1)
    if repeat == "weekly":
        return base + timedelta(days=7)
    year, month = divmod(base.month, 12)  # monthly; clamp to month length
    year, month = base.year + year, month + 1
    day = base.day
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


def normalize_tags(tags: list[str] | None) -> list[str]:
    out: list[str] = []
    for t in tags or []:
        t = t.strip().lstrip("#").lower()
        if t and t not in out:
            out.append(t)
    return out


def resolve_path(path: str | os.PathLike | None = None) -> Path:
    if path:
        return Path(path)
    env = os.environ.get(ENV_VAR)
    return Path(env) if env else DEFAULT_FILE


class TodoStore:
    """Loads and saves tasks to a JSON file; all mutations go through here."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = resolve_path(path)
        self.tasks: list[Task] = []
        self.next_id = 1
        self.trash: list[Task] = []  # tasks removed by the last rm/clear
        self.load()

    # ---- persistence -------------------------------------------------
    def load(self) -> None:
        if not self.path.exists():
            self.tasks, self.next_id, self.trash = [], 1, []
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            self.tasks = [Task.from_dict(t) for t in raw.get("tasks", [])]
            stored_next = int(raw.get("next_id", 1))
            self.trash = [Task.from_dict(t) for t in raw.get("trash", [])]
        except (json.JSONDecodeError, TypeError, AttributeError, ValueError, KeyError):
            raise TodoError(f"could not read {self.path}: file is corrupt or not a todo "
                            "file (fix or delete it)") from None
        max_id = max((t.id for t in self.tasks), default=0)
        self.next_id = max(stored_next, max_id + 1)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "next_id": self.next_id, "tasks": [asdict(t) for t in self.tasks],
                   "trash": [asdict(t) for t in self.trash]}
        # Atomic write: temp file in the same dir, then replace.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".todo-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # ---- operations --------------------------------------------------
    def get(self, task_id: int) -> Task:
        for t in self.tasks:
            if t.id == task_id:
                return t
        raise TodoError(f"no task with id {task_id}")

    def add(self, title: str, priority: str = "medium", due: str | None = None,
            tags: list[str] | None = None, note: str = "",
            repeat: str | None = None) -> Task:
        title = title.strip()
        if not title:
            raise TodoError("task title cannot be empty")
        task = Task(id=self.next_id, title=title, priority=validate_priority(priority),
                    due=validate_due(due), tags=normalize_tags(tags), note=(note or "").strip(),
                    repeat=validate_repeat(repeat))
        self.next_id += 1
        self.tasks.append(task)
        self.save()
        return task

    def set_done(self, task_id: int, done: bool = True) -> Task:
        task = self.get(task_id)
        if task.done == done:  # already in that state: keep the original completion time
            return task
        task.done = done
        task.completed = _now() if done else None
        self.save()
        return task

    def complete(self, task_id: int) -> tuple[Task, Task | None]:
        """Mark done; a repeating task also spawns its next occurrence (returned second)."""
        task = self.get(task_id)
        if task.done:
            return task, None
        task.done = True
        task.completed = _now()
        spawned = None
        if task.repeat:
            try:
                base = date.fromisoformat(task.due) if task.due else date.today()
            except ValueError:
                base = date.today()
            spawned = Task(id=self.next_id, title=task.title, priority=task.priority,
                           due=next_due(base, task.repeat).isoformat(),
                           tags=list(task.tags), note=task.note, repeat=task.repeat)
            self.next_id += 1
            self.tasks.append(spawned)
        self.save()
        return task, spawned

    def edit(self, task_id: int, title: str | None = None, priority: str | None = None,
             due: str | None = None, tags: list[str] | None = None,
             clear_due: bool = False, note: str | None = None,
             repeat: str | None = None) -> Task:
        task = self.get(task_id)
        # Validate everything before mutating so a bad field leaves the task untouched.
        new_title = title.strip() if title is not None else None
        if new_title == "":
            raise TodoError("task title cannot be empty")
        new_priority = validate_priority(priority) if priority is not None else None
        new_due = validate_due(due) if due is not None else None
        new_repeat = validate_repeat(repeat) if repeat is not None else None
        if new_title is not None:
            task.title = new_title
        if new_priority is not None:
            task.priority = new_priority
        if clear_due:
            task.due = None
        elif due is not None:
            task.due = new_due
        if tags is not None:
            task.tags = normalize_tags(tags)
        if note is not None:
            task.note = note.strip()
        if repeat is not None:
            task.repeat = new_repeat
        self.save()
        return task

    def remove(self, task_id: int) -> Task:
        task = self.get(task_id)
        self.tasks.remove(task)
        self.trash = [task]
        self.save()
        return task

    def rename_tag(self, old: str, new: str) -> int:
        """Rename (or merge into an existing) tag on every task; returns tasks changed."""
        old, new = (normalize_tags([old]) or [""])[0], (normalize_tags([new]) or [""])[0]
        if not old or not new:
            raise TodoError("tag names must not be empty")
        changed = [t for t in self.tasks if old in t.tags]
        if not changed:
            raise TodoError(f"no tasks have tag #{old}")
        for t in changed:
            t.tags = normalize_tags([new if g == old else g for g in t.tags])
        self.save()
        return len(changed)

    def restore(self) -> list[Task]:
        """Bring back the tasks deleted by the most recent rm/clear."""
        if not self.trash:
            raise TodoError("nothing to restore")
        restored, self.trash = self.trash, []
        self.tasks = sorted(self.tasks + restored, key=lambda t: t.id)
        self.save()
        return restored

    def import_tasks(self, items: list) -> list[Task]:
        """Add tasks from export-style dicts under fresh IDs. All-or-nothing."""
        new: list[Task] = []
        next_id = self.next_id
        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise TodoError(f"import item {i} is not an object")
            title = str(item.get("title", "")).strip()
            if not title:
                raise TodoError(f"import item {i} has no title")
            done = bool(item.get("done", False))
            created = item.get("created")
            task = Task(id=next_id, title=title, done=done,
                        priority=validate_priority(str(item.get("priority") or "medium")),
                        due=validate_due(item.get("due")), tags=normalize_tags(item.get("tags")),
                        created=created if isinstance(created, str) else _now(),
                        completed=(item.get("completed") or _now()) if done else None,
                        note=str(item.get("note") or "").strip(),
                        repeat=validate_repeat(item.get("repeat")))
            next_id += 1
            new.append(task)
        if new:
            self.tasks.extend(new)
            self.next_id = next_id
            self.save()
        return new

    def clear_done(self) -> int:
        before = len(self.tasks)
        self.trash = [t for t in self.tasks if t.done]
        self.tasks = [t for t in self.tasks if not t.done]
        removed = before - len(self.tasks)
        if removed:
            self.save()
        return removed

    def query(self, status: str = "pending", tag: str | None = None,
              priority: str | None = None, text: str | None = None,
              overdue: bool = False, sort: str = "priority",
              due_by: str | None = None, untagged: bool = False) -> list[Task]:
        """Filter and sort. Default: pending first, priority (high first), due date, id.

        sort="due" orders by due date (undated last); sort="created" by creation order.
        """
        if sort not in SORTS:
            raise TodoError(f"invalid sort {sort!r}; choose from {', '.join(SORTS)}")
        result = self.tasks
        if status == "pending":
            result = [t for t in result if not t.done]
        elif status == "done":
            result = [t for t in result if t.done]
        if tag:
            tag = tag.lstrip("#").lower()
            result = [t for t in result if tag in t.tags]
        if untagged:
            result = [t for t in result if not t.tags]
        if priority:
            priority = validate_priority(priority)
            result = [t for t in result if t.priority == priority]
        if overdue:
            result = [t for t in result if t.is_overdue()]
        if due_by:
            try:
                limit = parse_due(due_by).isoformat()
            except ValueError as exc:
                raise TodoError(str(exc)) from None
            result = [t for t in result if t.due and t.due <= limit]
        if text:
            needle = text.lower()
            result = [t for t in result
                      if needle in t.title.lower() or needle in t.note.lower() or needle.lstrip('#') in t.tags]
        rank = {"high": 0, "medium": 1, "low": 2}
        if sort == "due":
            return sorted(result, key=lambda t: (t.done, t.due or "9999-12-31", rank.get(t.priority, 1), t.id))
        if sort == "created":
            return sorted(result, key=lambda t: t.id)
        return sorted(result, key=lambda t: (t.done, rank.get(t.priority, 1),
                                             t.due or "9999-12-31", t.id))
