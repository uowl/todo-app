import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from todo.cli import main

ROOT = Path(__file__).resolve().parent.parent


class ExtrasTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.file = str(Path(self._tmp.name) / "t.json")

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *a):
        out, err = io.StringIO(), io.StringIO()
        return main(["--file", self.file, *a], out=out, err=err), out.getvalue(), err.getvalue()

    @staticmethod
    def titles(out):
        return [next(w for w in ("late", "soon", "none") if w in l) for l in out.splitlines()]

    def test_sort_due_and_created(self):
        self.run_cli("add", "late", "-p", "high", "-d", "2031-01-01")
        self.run_cli("add", "soon", "-p", "low", "-d", "2030-01-01")
        self.run_cli("add", "none")
        _, out, _ = self.run_cli("ls", "--sort", "due")
        self.assertEqual(self.titles(out), ["soon", "late", "none"])
        _, out, _ = self.run_cli("ls", "--sort", "created")
        self.assertEqual(self.titles(out), ["late", "soon", "none"])

    def test_export_formats(self):
        self.run_cli("add", "Buy, milk", "-t", "home", "-d", "2030-01-01")
        self.run_cli("done", "1")
        _, out, _ = self.run_cli("export", "-f", "csv")
        self.assertIn('1,"Buy, milk",yes,medium,2030-01-01,home', out)
        _, out, _ = self.run_cli("export", "-f", "markdown")
        self.assertEqual(out.strip(), "- [x] Buy, milk (due 2030-01-01) #home")
        import json
        _, out, _ = self.run_cli("export")
        self.assertEqual(json.loads(out)[0]["title"], "Buy, milk")

    def test_color_only_on_tty_and_respects_no_color(self):
        from todo.cli import format_task, use_color
        from todo.store import Task
        t = Task(id=1, title="x", priority="high")
        self.assertNotIn("", format_task(t))
        self.assertIn("[31m", format_task(t, color=True))
        self.assertFalse(use_color(io.StringIO()))
        class Tty(io.StringIO):
            def isatty(self): return True
        self.assertTrue(use_color(Tty()) or os.environ.get("NO_COLOR"))
        os.environ["NO_COLOR"] = "1"
        try:
            self.assertFalse(use_color(Tty()))
        finally:
            del os.environ["NO_COLOR"]


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.file = str(Path(self._tmp.name) / "todo.json")

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        code = main(["--file", self.file, *args], out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def test_full_workflow(self):
        code, out, _ = self.run_cli("add", "Write", "report", "-p", "high", "-d", "2030-01-01",
                                    "-t", "work")
        self.assertEqual(code, 0)
        self.assertIn("Added task 1: Write report", out)
        self.run_cli("add", "Buy milk", "-t", "home")

        _, out, _ = self.run_cli("list")
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("Write report", lines[0])  # high priority first
        self.assertIn("!!!", lines[0])
        self.assertIn("#work", lines[0])
        self.assertIn("due 2030-01-01", lines[0])

        _, out, _ = self.run_cli("done", "2")
        self.assertIn("Completed task 2", out)
        _, out, _ = self.run_cli("list")
        self.assertNotIn("Buy milk", out)
        _, out, _ = self.run_cli("list", "--done")
        self.assertIn("[x]", out)
        _, out, _ = self.run_cli("ls", "-a")
        self.assertEqual(len(out.strip().splitlines()), 2)

        _, out, _ = self.run_cli("stats")
        self.assertIn("2 total, 1 pending, 1 done", out)

        _, out, _ = self.run_cli("undo", "2")
        self.assertIn("Reopened task 2", out)

        _, out, _ = self.run_cli("edit", "1", "--title", "Write final report", "--no-due",
                                 "--no-tags")
        self.assertIn("Write final report", out)
        self.assertNotIn("due", out)
        self.assertNotIn("#", out)

        _, out, _ = self.run_cli("search", "MILK")
        self.assertIn("Buy milk", out)
        self.assertNotIn("report", out)

        self.run_cli("done", "1", "2")
        _, out, _ = self.run_cli("clear")
        self.assertIn("Removed 2 completed task(s).", out)
        _, out, _ = self.run_cli("list")
        self.assertIn("No tasks.", out)

    def test_filters(self):
        self.run_cli("add", "a", "-t", "work", "-p", "low")
        self.run_cli("add", "b", "-t", "home", "-p", "high")
        _, out, _ = self.run_cli("list", "-t", "work")
        self.assertIn(" a", out)
        self.assertNotIn(" b", out)
        _, out, _ = self.run_cli("list", "-p", "high")
        self.assertIn(" b", out)
        self.assertNotIn(" a", out)

    def test_rm(self):
        self.run_cli("add", "a")
        code, out, _ = self.run_cli("rm", "1")
        self.assertEqual(code, 0)
        self.assertIn("Removed task 1: a", out)

    def test_multi_id_is_all_or_nothing(self):
        self.run_cli("add", "a")
        self.run_cli("add", "b")
        code, out, err = self.run_cli("done", "1", "99")
        self.assertEqual(code, 1)
        self.assertIn("no task with id 99", err)
        self.assertNotIn("[x]", self.run_cli("list", "-a")[1])
        code, _, _ = self.run_cli("rm", "2", "99")
        self.assertEqual(code, 1)
        self.assertEqual(len(self.run_cli("list")[1].splitlines()), 2)

    def test_duplicate_ids_ok(self):
        self.run_cli("add", "a")
        code, out, _ = self.run_cli("rm", "1", "1")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("Removed"), 1)

    def test_empty_title_and_bad_date(self):
        self.assertEqual(self.run_cli("add", " ")[0], 1)
        self.assertEqual(self.run_cli("add", "x", "-d", "2026-13-45")[0], 1)
        self.assertIn("No tasks", self.run_cli("list")[1])

    def test_corrupt_file(self):
        Path(self.file).write_text("garbage", encoding="utf-8")
        code, _, err = self.run_cli("list")
        self.assertEqual(code, 1)
        self.assertIn("could not read", err)

    def test_unicode_and_dash_title(self):
        self.run_cli("add", "--", "-ünï ✓")
        self.assertIn("-ünï ✓", self.run_cli("list")[1])

    def test_ids_not_reused(self):
        self.run_cli("add", "a")
        self.run_cli("rm", "1")
        self.assertIn("Added task 2", self.run_cli("add", "b")[1])

    def test_bare_command_lists(self):
        self.run_cli("add", "hello")
        _, out, _ = self.run_cli()
        self.assertIn("hello", out)

    def test_errors_return_nonzero(self):
        code, _, err = self.run_cli("done", "42")
        self.assertEqual(code, 1)
        self.assertIn("no task with id 42", err)
        code, _, err = self.run_cli("add", "x", "-d", "not-a-date")
        self.assertEqual(code, 1)
        self.assertIn("invalid due date", err)

    def test_argparse_errors_exit_2(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            self.run_cli("add", "x", "-p", "urgent")
        self.assertEqual(cm.exception.code, 2)

    def test_overdue_marker(self):
        self.run_cli("add", "old", "-d", "2000-01-01")
        _, out, _ = self.run_cli("list")
        self.assertIn("OVERDUE", out)
        _, out, _ = self.run_cli("stats")
        self.assertIn("1 overdue", out)

    def test_due_by_filter(self):
        self.run_cli("add", "soon", "-d", "tomorrow")
        self.run_cli("add", "later", "-d", "2999-01-01")
        self.run_cli("add", "undated")
        _, out, _ = self.run_cli("ls", "--due-by", "+3d")
        self.assertIn("soon", out)
        self.assertNotIn("later", out)
        self.assertNotIn("undated", out)
        code, _, err = self.run_cli("ls", "--due-by", "garbage")
        self.assertEqual(code, 1)
        self.assertIn("error", err)

    def test_module_entry_point(self):
        env = {**os.environ, "TODO_FILE": self.file}
        subprocess.run([sys.executable, "-m", "todo", "add", "via subprocess"], cwd=ROOT,
                       env=env, check=True, capture_output=True)
        res = subprocess.run([sys.executable, "-m", "todo", "list"], cwd=ROOT, env=env,
                             check=True, capture_output=True, text=True)
        self.assertIn("via subprocess", res.stdout)


if __name__ == "__main__":
    unittest.main()


class RestoreTests(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "t.json")

    def run_cli(self, *a):
        import io
        from todo.cli import main
        o, e = io.StringIO(), io.StringIO()
        return main(["--file", self.f, *a], o, e), o.getvalue(), e.getvalue()

    def test_restore_rm_batch(self):
        for t in "abc":
            self.run_cli("add", t)
        self.run_cli("rm", "1", "3")
        code, out, _ = self.run_cli("restore")
        self.assertEqual(code, 0)
        self.assertIn("Restored task 1", out)
        self.assertIn("Restored task 3", out)
        self.assertIn("3 total", self.run_cli("stats")[1])

    def test_restore_clear_and_empty(self):
        self.run_cli("add", "a")
        self.run_cli("done", "1")
        self.run_cli("clear")
        self.assertEqual(self.run_cli("restore")[0], 0)
        self.assertIn("1 done", self.run_cli("stats")[1])
        code, _, err = self.run_cli("restore")
        self.assertEqual(code, 1)
        self.assertIn("nothing to restore", err)


class RoundFourTests(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "t.json")

    def run_cli(self, *a):
        import io
        from todo.cli import main
        o, e = io.StringIO(), io.StringIO()
        return main(["--file", self.f, *a], o, e), o.getvalue(), e.getvalue()

    def test_edit_nothing_errors(self):
        self.run_cli("add", "x")
        rc, _, err = self.run_cli("edit", "1")
        self.assertEqual(rc, 1)
        self.assertIn("nothing to edit", err)

    def test_search_matches_tag(self):
        self.run_cli("add", "buy milk", "-t", "home")
        rc, out, _ = self.run_cli("search", "home")
        self.assertIn("buy milk", out)

    def test_done_twice_keeps_timestamp(self):
        from todo.store import TodoStore
        self.run_cli("add", "x"); self.run_cli("done", "1")
        first = TodoStore(self.f).get(1).completed
        self.run_cli("done", "1")
        self.assertEqual(TodoStore(self.f).get(1).completed, first)


class ImportTest(ExtrasTest):
    def test_roundtrip(self):
        self.run_cli("add", "one", "-t", "x", "-d", "2030-01-01")
        self.run_cli("add", "two", "-p", "high")
        self.run_cli("done", "2")
        _, exported, _ = self.run_cli("export")
        src = Path(self._tmp.name) / "e.json"
        src.write_text(exported, encoding="utf-8")
        code, out, _ = self.run_cli("import", str(src))
        self.assertEqual((code, out.strip()), (0, "Imported 2 task(s)."))
        _, out, _ = self.run_cli("ls", "-a")
        self.assertEqual(len(out.splitlines()), 4)
        self.assertIn("#x", out)

    def test_bad_import_is_all_or_nothing(self):
        src = Path(self._tmp.name) / "b.json"
        src.write_text('[{"title": "ok"}, {"title": "bad", "priority": "urgent"}]')
        code, _, err = self.run_cli("import", str(src))
        self.assertEqual(code, 1)
        self.assertIn("priority", err)
        self.assertIn("No tasks", self.run_cli("ls")[1])

    def test_missing_file(self):
        code, _, err = self.run_cli("import", "nope.json")
        self.assertEqual(code, 1)
        self.assertIn("could not read", err)


class NoteTests(unittest.TestCase):
    def test_note_show_edit_search(self):
        import tempfile, os, io
        from todo.cli import main
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "t.json")
            def run(*a):
                out = io.StringIO()
                rc = main(["--file", f, *a], out=out, err=io.StringIO())
                return rc, out.getvalue()
            self.assertEqual(run("add", "Write", "report", "-n", "line1\nline2")[0], 0)
            rc, text = run("show", "1")
            self.assertIn("note: line1", text)
            self.assertIn("line2", text)
            self.assertEqual(run("search", "LINE2")[1].count("Write report"), 1)
            run("edit", "1", "-n", "")
            self.assertNotIn("note:", run("show", "1")[1])
            self.assertEqual(run("show", "9")[0], 1)

    def test_note_marker_and_exports(self):
        import tempfile, os, io
        from todo.cli import main
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "t.json")
            def run(*a):
                out = io.StringIO()
                main(["--file", f, *a], out=out, err=io.StringIO())
                return out.getvalue()
            run("add", "A", "-n", "hello\nworld")
            self.assertIn("[note]", run("ls"))
            self.assertIn("hello", run("export", "-f", "csv"))
            self.assertIn("  > world", run("export", "-f", "markdown"))


class TestRepeatCli(ExtrasTest):
    def test_repeat_flow(self):
        self.run_cli("add", "water", "-d", "2030-01-01", "-r", "weekly")
        code, out, _ = self.run_cli("done", "1")
        self.assertEqual(code, 0)
        self.assertIn("Next weekly occurrence: task 2 (due 2030-01-08)", out)
        _, out, _ = self.run_cli("ls")
        self.assertIn("(repeats weekly)", out)
        self.run_cli("edit", "2", "-r", "none")
        _, out, _ = self.run_cli("show", "2")
        self.assertNotIn("repeats", out)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.run_cli("add", "x", "-r", "yearly")


class TagsCommandTest(ExtrasTest):
    def test_tags_counts(self):
        self.assertIn("No tags", self.run_cli("tags")[1])
        self.run_cli("add", "a", "-t", "work", "-t", "home")
        self.run_cli("add", "b", "-t", "work")
        self.run_cli("done", "2")
        _, out, _ = self.run_cli("tags")
        self.assertEqual(out.splitlines(), ["#home  1 pending / 1 total", "#work  1 pending / 2 total"])


class NextLimitTest(ExtrasTest):
    def test_untagged(self):
        self.run_cli("add", "plain")
        self.run_cli("add", "tagged", "-t", "x")
        _, out, _ = self.run_cli("ls", "--untagged")
        self.assertIn("plain", out)
        self.assertNotIn("tagged", out.replace("untagged", ""))

    def test_undated(self):
        self.run_cli("add", "nodate")
        self.run_cli("add", "dated", "-d", "2030-01-01")
        _, out, _ = self.run_cli("ls", "--undated")
        self.assertIn("nodate", out)
        self.assertNotIn("2030", out)

    def test_reverse(self):
        self.run_cli("add", "low one", "-p", "low")
        self.run_cli("add", "big one", "-p", "high")
        _, out, _ = self.run_cli("ls", "--reverse")
        self.assertLess(out.index("low one"), out.index("big one"))

    def test_ls_json(self):
        import json
        _, out, _ = self.run_cli("ls", "--json")
        self.assertEqual(json.loads(out), [])
        self.run_cli("add", "a", "-t", "x")
        self.run_cli("add", "b")
        _, out, _ = self.run_cli("ls", "--json", "-t", "x")
        data = json.loads(out)
        self.assertEqual([d["title"] for d in data], ["a"])

    def test_next_and_limit(self):
        self.assertIn("Nothing to do", self.run_cli("next")[1])
        self.run_cli("add", "low one", "-p", "low")
        self.run_cli("add", "big one", "-p", "high")
        self.run_cli("add", "mid one")
        self.assertIn("big one", self.run_cli("next")[1])
        _, out, _ = self.run_cli("ls", "--limit", "2")
        self.assertEqual(len(out.splitlines()), 3)
        self.assertIn("(showing 2 of 3)", out)
        self.assertNotIn("showing", self.run_cli("ls", "--limit", "5")[1])
        self.assertEqual(self.run_cli("ls", "--limit", "0")[0], 1)


class AddTagTest(ExtrasTest):
    def test_edit_add_tag_keeps_existing(self):
        self.run_cli("add", "x", "-t", "a")
        self.assertEqual(self.run_cli("edit", "1", "--add-tag", "#b", "--add-tag", "a")[0], 0)
        out = self.run_cli("show", "1")[1]
        self.assertIn("#a #b", out)
        self.assertEqual(self.run_cli("edit", "9", "--add-tag", "z")[0], 1)


class TagMaintenanceTest(ExtrasTest):
    def test_rm_tag_and_rename(self):
        self.run_cli("add", "a", "-t", "x", "-t", "y")
        self.run_cli("add", "b", "-t", "x")
        rc, out, _ = self.run_cli("edit", "1", "--rm-tag", "#X")
        self.assertEqual(rc, 0)
        self.assertNotIn("#x", out)
        self.assertIn("#y", out)
        rc, out, _ = self.run_cli("edit", "2", "--rm-tag", "x")
        self.assertEqual(rc, 0)
        self.assertNotIn("#", out)
        self.run_cli("edit", "2", "--add-tag", "y")
        rc, out, _ = self.run_cli("rename-tag", "y", "Z")
        self.assertEqual(rc, 0)
        self.assertIn("2 task", out)
        self.assertIn("#z", self.run_cli("ls")[1])

    def test_rename_tag_merge_and_missing(self):
        self.run_cli("add", "a", "-t", "x", "-t", "y")
        self.run_cli("rename-tag", "x", "y")
        self.assertEqual(self.run_cli("ls")[1].count("#y"), 1)
        rc, _, err = self.run_cli("rename-tag", "nope", "q")
        self.assertEqual(rc, 1)
        self.assertIn("no tasks have tag", err)


class SubtaskTests(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        self.d = tempfile.TemporaryDirectory()
        self.f = os.path.join(self.d.name, "t.json")

    def tearDown(self):
        self.d.cleanup()

    def run_cli(self, *argv):
        import io
        from todo.cli import main
        out, err = io.StringIO(), io.StringIO()
        code = main(["--file", self.f, *argv], out, err)
        return code, out.getvalue(), err.getvalue()

    def test_subtask_flow(self):
        self.run_cli("add", "parent")
        self.assertEqual(self.run_cli("add", "child", "--parent", "1")[0], 0)
        self.assertIn("subtask of 1", self.run_cli("ls")[1])
        self.assertIn("- ", self.run_cli("show", "1")[1])
        self.assertEqual(self.run_cli("add", "x", "--parent", "2")[0], 1)  # one level only
        self.assertEqual(self.run_cli("add", "x", "--parent", "9")[0], 1)

    def test_rm_cascades_and_restore(self):
        self.run_cli("add", "parent")
        self.run_cli("add", "child", "--parent", "1")
        code, out, _ = self.run_cli("rm", "1", "2")
        self.assertEqual(code, 0)
        self.assertIn("No tasks", self.run_cli("ls")[1])
        self.run_cli("restore")
        self.assertIn("child", self.run_cli("ls")[1])
