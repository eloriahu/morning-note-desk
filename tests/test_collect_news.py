"""Portability checks for the collector launcher; no subprocess or network runs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collect_news.py"
SPEC = importlib.util.spec_from_file_location("collect_news", SCRIPT)
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class CollectorLauncherTests(unittest.TestCase):
    def invoke(self, workspace, *args, returncode=0):
        argv = [str(SCRIPT), "--workspace", str(workspace), *args]
        completed = subprocess.CompletedProcess([], returncode)
        with patch.object(sys, "argv", argv), patch.object(collector, "select_python", return_value=sys.executable), \
             patch.object(collector.subprocess, "run", return_value=completed) as run:
            result = collector.main()
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[2], "run")
        self.assertEqual(command[command.index("--mode") + 1], "market-first")
        self.assertIn("--dry-run", command)
        self.assertEqual(run.call_args.kwargs, {"cwd": str(workspace.resolve()), "check": False})
        self.assertEqual(result, returncode)
        return command

    @staticmethod
    def local_project(workspace):
        project = workspace / "morning-note"
        project.mkdir()
        (project / "morning_note.py").write_text("# Existing local collector fixture\n", encoding="utf-8")
        (project / "config.json").write_text('{"watchlist_file":"watchlist.json","local_marker":true}', encoding="utf-8")
        (project / "watchlist.json").write_text('[{"ticker":"EXAMPLE JP","name":"Existing priority fixture"}]', encoding="utf-8")
        return project

    def test_existing_local_project_preserves_config_and_priorities(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            project = self.local_project(workspace)
            before = {name: (project / name).read_bytes() for name in ("config.json", "watchlist.json")}
            command = self.invoke(workspace, "--hours", "12", "--as-of", "2026-09-24T08:00:00+08:00")
            self.assertTrue(Path(command[1]).samefile(project / "morning_note.py"))
            self.assertTrue(Path(command[command.index("--config") + 1]).samefile(project / "config.json"))
            self.assertEqual(command[command.index("--hours") + 1], "12")
            self.assertEqual(command[command.index("--as-of") + 1], "2026-09-24T08:00:00+08:00")
            self.assertEqual(before, {name: (project / name).read_bytes() for name in before})
            self.assertFalse((workspace / "morning-note-runs").exists())

    def test_fresh_workspace_uses_bundled_defaults_and_empty_priorities(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            command = self.invoke(workspace)
            self.assertEqual(Path(command[1]), collector.ROOT / "collector" / "morning_note.py")
            config_path = Path(command[command.index("--config") + 1])
            self.assertTrue(config_path.parent.parent.samefile(workspace / "morning-note-runs"))
            expected = json.loads((collector.ROOT / "collector" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8")), expected)
            self.assertEqual(json.loads((config_path.parent / "watchlist.json").read_text(encoding="utf-8")), [])
            self.assertEqual(json.loads((config_path.parent / "inbox.json").read_text(encoding="utf-8")), [])
            self.assertEqual(command[command.index("--hours") + 1], "24")
            self.assertNotIn("--as-of", command)

    def test_explicit_priority_file_is_copied_without_changing_local_list(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            project = self.local_project(workspace)
            previous = (project / "watchlist.json").read_bytes()
            priorities = [{"ticker": "TEST JP", "name": "Supplied priority fixture", "aliases": ["テスト企業"]}]
            supplied = workspace / "supplied-priorities.json"
            supplied.write_text(json.dumps(priorities, ensure_ascii=False), encoding="utf-8-sig")
            supplied_before = supplied.read_bytes()
            command = self.invoke(workspace, "--priority-file", str(supplied), "--hours", "48")
            self.assertEqual(Path(command[1]), collector.ROOT / "collector" / "morning_note.py")
            config_path = Path(command[command.index("--config") + 1])
            self.assertEqual(json.loads((config_path.parent / "watchlist.json").read_text(encoding="utf-8")), priorities)
            self.assertEqual((project / "watchlist.json").read_bytes(), previous)
            self.assertEqual(supplied.read_bytes(), supplied_before)
            self.assertEqual(command[command.index("--hours") + 1], "48")

    def test_invalid_priority_object_raises_before_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            supplied = workspace / "invalid-priorities.json"
            supplied.write_text('{"ticker":"not-a-list"}', encoding="utf-8")
            argv = [str(SCRIPT), "--workspace", str(workspace), "--priority-file", str(supplied)]
            with patch.object(sys, "argv", argv), patch.object(collector.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "Priority file must be a JSON list"):
                    collector.main()
            run.assert_not_called()

    def test_collector_failure_code_is_returned_to_caller(self):
        with tempfile.TemporaryDirectory() as temp:
            self.invoke(Path(temp), returncode=2)

    def test_workspace_environment_is_used_when_dependencies_are_present(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            python = workspace / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
            with patch.object(collector.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
                self.assertEqual(collector.select_python(workspace), str(python))
            self.assertEqual(run.call_args.args[0], [str(python), "-c", "import lxml, pypdf, tzdata"])

    def test_missing_dependencies_stop_before_a_run_folder_is_created(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            argv = [str(SCRIPT), "--workspace", str(workspace)]
            with patch.object(sys, "argv", argv), patch.object(collector.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)) as run:
                with self.assertRaisesRegex(ValueError, "No scan was started"):
                    collector.main()
            self.assertFalse((workspace / "morning-note-runs").exists())
            self.assertGreaterEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
