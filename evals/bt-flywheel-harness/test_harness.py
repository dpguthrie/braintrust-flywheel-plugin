import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from harness.core import build_claude_argv, load_scenarios, prepare_workspace, run_scenario


class FakeBtTests(unittest.TestCase):
    def test_fake_bt_strict_mode_accepts_configured_route(self):
        scenario = load_scenarios(["measurement_gap"])[0]
        with tempfile.TemporaryDirectory() as tmp:
            workspace = prepare_workspace(scenario, "none", Path(tmp))
            proc = subprocess.run(
                ["bt", "sql", "SELECT * FROM logs WHERE search(output, 'citation')"],
                cwd=str(workspace.repo),
                env=workspace.env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("trace-cite-001", proc.stdout)

    def test_fake_bt_strict_mode_rejects_unexpected_route(self):
        scenario = load_scenarios(["measurement_gap"])[0]
        with tempfile.TemporaryDirectory() as tmp:
            workspace = prepare_workspace(scenario, "none", Path(tmp))
            proc = subprocess.run(
                ["bt", "projects"],
                cwd=str(workspace.repo),
                env=workspace.env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 17)
            self.assertIn("Unexpected fake bt command", proc.stderr)


class ScriptedHarnessTests(unittest.TestCase):
    def test_scripted_scenarios_score_perfectly(self):
        for scenario in load_scenarios():
            with self.subTest(scenario=scenario.id):
                result = run_scenario(
                    scenario.id,
                    skill_variant="current",
                    runner="scripted",
                    keep_workspace=False,
                )
                self.assertEqual(result["score"], 1.0, json.dumps(result["checks"], indent=2))
                self.assertIsNone(result["workspace"])


class ClaudeRunnerTests(unittest.TestCase):
    def test_build_claude_argv_includes_repo_skill_and_prompt(self):
        scenario = load_scenarios(["agent_bug"])[0]
        with tempfile.TemporaryDirectory() as tmp:
            workspace = prepare_workspace(scenario, "current", Path(tmp))
            prompt = "Use the skill and write the handoff."
            argv = build_claude_argv(workspace, prompt)

            self.assertEqual(argv[0], "claude")
            self.assertIn("--print", argv)
            self.assertIn("--bare", argv)
            self.assertIn("--no-session-persistence", argv)
            self.assertIn("--permission-mode", argv)
            self.assertIn("bypassPermissions", argv)
            self.assertIn("--add-dir", argv)
            self.assertIn(str(workspace.repo), argv)
            self.assertIn(str(workspace.skill_path), argv)
            self.assertEqual(argv[-2:], ["-p", prompt])

    def test_build_claude_argv_respects_environment_options(self):
        scenario = load_scenarios(["agent_bug"])[0]
        old_env = {
            key: os.environ.get(key)
            for key in [
                "FLYWHEEL_CLAUDE_BIN",
                "FLYWHEEL_CLAUDE_MODEL",
                "FLYWHEEL_CLAUDE_MAX_BUDGET_USD",
                "FLYWHEEL_CLAUDE_EXTRA_ARGS",
            ]
        }
        try:
            os.environ["FLYWHEEL_CLAUDE_BIN"] = "claude-test"
            os.environ["FLYWHEEL_CLAUDE_MODEL"] = "sonnet"
            os.environ["FLYWHEEL_CLAUDE_MAX_BUDGET_USD"] = "2.50"
            os.environ["FLYWHEEL_CLAUDE_EXTRA_ARGS"] = "--debug-file /tmp/claude-debug.log"
            with tempfile.TemporaryDirectory() as tmp:
                workspace = prepare_workspace(scenario, "none", Path(tmp))
                argv = build_claude_argv(workspace, "prompt")
            self.assertEqual(argv[0], "claude-test")
            self.assertIn("--model", argv)
            self.assertIn("sonnet", argv)
            self.assertIn("--max-budget-usd", argv)
            self.assertIn("2.50", argv)
            self.assertIn("--debug-file", argv)
            self.assertIn("/tmp/claude-debug.log", argv)
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
