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

    def test_module_entry_point(self):
        env = {**os.environ, "TODO_FILE": self.file}
        subprocess.run([sys.executable, "-m", "todo", "add", "via subprocess"], cwd=ROOT,
                       env=env, check=True, capture_output=True)
        res = subprocess.run([sys.executable, "-m", "todo", "list"], cwd=ROOT, env=env,
                             check=True, capture_output=True, text=True)
        self.assertIn("via subprocess", res.stdout)


if __name__ == "__main__":
    unittest.main()
