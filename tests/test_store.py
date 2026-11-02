import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from todo.store import Task, TodoError, TodoStore, resolve_path


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "todo.json"
        self.store = TodoStore(self.path)

    def tearDown(self):
        self._tmp.cleanup()


class TestAdd(StoreTestCase):
    def test_add_assigns_incrementing_ids_and_persists(self):
        a = self.store.add("first")
        b = self.store.add("second", priority="high", due="2030-01-02", tags=["#Work", "work", "home"])
        self.assertEqual((a.id, b.id), (1, 2))
        reloaded = TodoStore(self.path)
        self.assertEqual([t.title for t in reloaded.tasks], ["first", "second"])
        t2 = reloaded.get(2)
        self.assertEqual(t2.priority, "high")
        self.assertEqual(t2.due, "2030-01-02")
        self.assertEqual(t2.tags, ["work", "home"])

    def test_add_rejects_empty_title(self):
        with self.assertRaises(TodoError):
            self.store.add("   ")

    def test_add_rejects_bad_priority_and_due(self):
        with self.assertRaises(TodoError):
            self.store.add("x", priority="urgent")
        with self.assertRaises(TodoError):
            self.store.add("x", due="someday")
        self.assertEqual(self.store.tasks, [])

    def test_ids_not_reused_after_delete(self):
        self.store.add("a")
        self.store.add("b")
        self.store.remove(2)
        self.assertEqual(TodoStore(self.path).add("c").id, 3)


class TestMutations(StoreTestCase):
    def test_done_and_undo(self):
        self.store.add("a")
        t = self.store.set_done(1)
        self.assertTrue(t.done)
        self.assertIsNotNone(t.completed)
        t = self.store.set_done(1, False)
        self.assertFalse(t.done)
        self.assertIsNone(t.completed)

    def test_unknown_id_raises(self):
        for op in (self.store.get, self.store.set_done, self.store.remove):
            with self.assertRaises(TodoError):
                op(99)

    def test_edit_fields(self):
        self.store.add("a", due="2030-01-01", tags=["x"])
        t = self.store.edit(1, title="b", priority="low", tags=["y"])
        self.assertEqual((t.title, t.priority, t.tags, t.due), ("b", "low", ["y"], "2030-01-01"))
        t = self.store.edit(1, clear_due=True, tags=[])
        self.assertIsNone(t.due)
        self.assertEqual(t.tags, [])

    def test_edit_invalid_leaves_task_unchanged(self):
        self.store.add("a")
        with self.assertRaises(TodoError):
            self.store.edit(1, title="new", due="bad-date")
        self.assertEqual(TodoStore(self.path).get(1).title, "a")
        self.assertEqual(self.store.get(1).title, "a")

    def test_clear_done(self):
        for name in "abc":
            self.store.add(name)
        self.store.set_done(1)
        self.store.set_done(3)
        self.assertEqual(self.store.clear_done(), 2)
        self.assertEqual([t.title for t in TodoStore(self.path).tasks], ["b"])


class TestQuery(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.store.add("low task", priority="low")
        self.store.add("high later", priority="high", due="2030-05-01", tags=["work"])
        self.store.add("high sooner", priority="high", due="2030-01-01")
        self.store.add("Buy milk", tags=["home"])
        self.store.set_done(1)

    def test_default_is_pending_sorted(self):
        titles = [t.title for t in self.store.query()]
        self.assertEqual(titles, ["high sooner", "high later", "Buy milk"])

    def test_status_filters(self):
        self.assertEqual([t.id for t in self.store.query(status="done")], [1])
        self.assertEqual(len(self.store.query(status="all")), 4)
        self.assertEqual(self.store.query(status="all")[-1].id, 1)  # done tasks last

    def test_tag_priority_text_filters(self):
        self.assertEqual([t.id for t in self.store.query(tag="#WORK")], [2])
        self.assertEqual([t.id for t in self.store.query(priority="high")], [3, 2])
        self.assertEqual([t.id for t in self.store.query(status="all", text="MILK")], [4])


class TestPersistence(StoreTestCase):
    def test_missing_file_is_empty(self):
        self.assertEqual(self.store.tasks, [])
        self.assertFalse(self.path.exists())

    def test_corrupt_file_raises_todo_error(self):
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(TodoError):
            TodoStore(self.path)

    def test_unknown_fields_ignored_and_next_id_recovered(self):
        self.path.write_text(json.dumps({"tasks": [{"id": 7, "title": "x", "extra": 1}]}),
                             encoding="utf-8")
        s = TodoStore(self.path)
        self.assertEqual(s.get(7).title, "x")
        self.assertEqual(s.add("y").id, 8)

    def test_creates_parent_directories(self):
        nested = Path(self._tmp.name) / "a" / "b" / "todo.json"
        TodoStore(nested).add("x")
        self.assertTrue(nested.exists())

    def test_no_temp_files_left_behind(self):
        self.store.add("x")
        leftovers = [p for p in self.path.parent.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [])

    def test_resolve_path_precedence(self):
        with mock.patch.dict(os.environ, {"TODO_FILE": "from_env.json"}):
            self.assertEqual(resolve_path("explicit.json"), Path("explicit.json"))
            self.assertEqual(resolve_path(), Path("from_env.json"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_path().name, ".todo.json")


class TestTask(unittest.TestCase):
    def test_overdue(self):
        today = date(2030, 1, 10)
        self.assertTrue(Task(1, "x", due="2030-01-09").is_overdue(today))
        self.assertFalse(Task(1, "x", due="2030-01-10").is_overdue(today))
        self.assertFalse(Task(1, "x", due="2030-01-09", done=True).is_overdue(today))
        self.assertFalse(Task(1, "x").is_overdue(today))
        self.assertFalse(Task(1, "x", due="garbage").is_overdue(today))


if __name__ == "__main__":
    unittest.main()


class DueParsingTests(unittest.TestCase):
    def test_formats(self):
        from datetime import date
        from todo.store import parse_due
        wed = date(2026, 11, 4)
        self.assertEqual(parse_due("today", wed), wed)
        self.assertEqual(parse_due("Tomorrow", wed), date(2026, 11, 5))
        self.assertEqual(parse_due("+2w", wed), date(2026, 11, 18))
        self.assertEqual(parse_due("+3d", wed), date(2026, 11, 7))
        self.assertEqual(parse_due("fri", wed), date(2026, 11, 6))
        self.assertEqual(parse_due("wednesday", wed), date(2026, 11, 11))
        self.assertEqual(parse_due("2027-01-02", wed), date(2027, 1, 2))
        with self.assertRaises(ValueError):
            parse_due("someday", wed)
        with self.assertRaises(ValueError):
            parse_due("monkey", wed)


class TestRepeat(StoreTestCase):
    def test_complete_spawns_next(self):
        t = self.store.add("water plants", due="2030-01-31", repeat="monthly", tags=["home"])
        done, nxt = self.store.complete(t.id)
        self.assertTrue(done.done)
        self.assertEqual((nxt.due, nxt.repeat, nxt.tags, nxt.id), ("2030-02-28", "monthly", ["home"], 2))
        self.assertEqual(len(TodoStore(self.path).tasks), 2)

    def test_complete_twice_and_non_repeating(self):
        t = self.store.add("x", due="2030-01-01", repeat="weekly")
        self.store.complete(t.id)
        self.assertIsNone(self.store.complete(t.id)[1])
        u = self.store.add("y")
        self.assertIsNone(self.store.complete(u.id)[1])

    def test_invalid_repeat_and_edit(self):
        with self.assertRaises(TodoError):
            self.store.add("x", repeat="yearly")
        t = self.store.add("x", repeat="daily")
        self.assertIsNone(self.store.edit(t.id, repeat="none").repeat)
