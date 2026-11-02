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
        self.load()

    # ---- persistence -------------------------------------------------
    def load(self) -> None:
        if not self.path.exists():
            self.tasks, self.next_id = [], 1
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            self.tasks = [Task.from_dict(t) for t in raw.get("tasks", [])]
            stored_next = int(raw.get("next_id", 1))
        except (json.JSONDecodeError, TypeError, AttributeError, ValueError, KeyError):
            raise TodoError(f"could not read {self.path}: file is corrupt or not a todo "
                            "file (fix or delete it)") from None
        max_id = max((t.id for t in self.tasks), default=0)
        self.next_id = max(stored_next, max_id + 1)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "next_id": self.next_id, "tasks": [asdict(t) for t in self.tasks]}
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
            tags: list[str] | None = None) -> Task:
        title = title.strip()
        if not title:
            raise TodoError("task title cannot be empty")
        task = Task(id=self.next_id, title=title, priority=validate_priority(priority),
                    due=validate_due(due), tags=normalize_tags(tags))
        self.next_id += 1
        self.tasks.append(task)
        self.save()
        return task

    def set_done(self, task_id: int, done: bool = True) -> Task:
        task = self.get(task_id)
        task.done = done
        task.completed = _now() if done else None
        self.save()
        return task

    def edit(self, task_id: int, title: str | None = None, priority: str | None = None,
             due: str | None = None, tags: list[str] | None = None,
             clear_due: bool = False) -> Task:
        task = self.get(task_id)
        # Validate everything before mutating so a bad field leaves the task untouched.
        new_title = title.strip() if title is not None else None
        if new_title == "":
            raise TodoError("task title cannot be empty")
        new_priority = validate_priority(priority) if priority is not None else None
        new_due = validate_due(due) if due is not None else None
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
        self.save()
        return task

    def remove(self, task_id: int) -> Task:
        task = self.get(task_id)
        self.tasks.remove(task)
        self.save()
        return task

    def clear_done(self) -> int:
        before = len(self.tasks)
        self.tasks = [t for t in self.tasks if not t.done]
        removed = before - len(self.tasks)
        if removed:
            self.save()
        return removed

    def query(self, status: str = "pending", tag: str | None = None,
              priority: str | None = None, text: str | None = None,
              overdue: bool = False, sort: str = "priority") -> list[Task]:
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
        if priority:
            priority = validate_priority(priority)
            result = [t for t in result if t.priority == priority]
        if overdue:
            result = [t for t in result if t.is_overdue()]
        if text:
            needle = text.lower()
            result = [t for t in result if needle in t.title.lower()]
        rank = {"high": 0, "medium": 1, "low": 2}
        if sort == "due":
            return sorted(result, key=lambda t: (t.done, t.due or "9999-12-31", rank.get(t.priority, 1), t.id))
        if sort == "created":
            return sorted(result, key=lambda t: t.id)
        return sorted(result, key=lambda t: (t.done, rank.get(t.priority, 1),
                                             t.due or "9999-12-31", t.id))
