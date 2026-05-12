"""Reusable offline harness for bt-flywheel skill evaluation.

The harness intentionally separates deterministic scenario execution from the
Braintrust Eval wrapper. That keeps local smoke tests cheap while still allowing
Braintrust to compare skill variants and runner configurations.
"""

import fnmatch
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


IGNORED_DIRS = {
    ".agent-skills",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
}

SUMMARY_FILE = "bt-flywheel-summary.json"
NARRATIVE_FILE = "bt-flywheel-narrative.md"


@dataclass
class Scenario:
    id: str
    path: Path
    manifest: Dict[str, Any]
    fixture_dir: Path


@dataclass
class Workspace:
    root: Path
    repo: Path
    bin_dir: Path
    command_log: Path
    skill_path: Optional[Path]
    env: Dict[str, str]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def harness_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_scenarios(ids: Optional[Iterable[str]] = None) -> List[Scenario]:
    wanted = set(ids or [])
    scenario_dir = harness_root() / "scenarios"
    scenarios = []
    for path in sorted(scenario_dir.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        scenario_id = manifest["id"]
        if wanted and scenario_id not in wanted:
            continue
        fixture_dir = harness_root() / "fixtures" / manifest["fixture"]
        scenarios.append(
            Scenario(
                id=scenario_id,
                path=path,
                manifest=manifest,
                fixture_dir=fixture_dir,
            )
        )
    if wanted and len(scenarios) != len(wanted):
        found = {scenario.id for scenario in scenarios}
        missing = sorted(wanted - found)
        raise ValueError("Unknown scenario id(s): " + ", ".join(missing))
    return scenarios


def _copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(str(dst))
    shutil.copytree(str(src), str(dst))


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def snapshot_files(repo: Path) -> Dict[str, str]:
    snapshot = {}
    for path in sorted(repo.rglob("*")):
        rel = path.relative_to(repo)
        if _is_ignored(rel) or not path.is_file():
            continue
        snapshot[rel.as_posix()] = _hash_file(path)
    return snapshot


def changed_files(before: Dict[str, str], after: Dict[str, str]) -> List[str]:
    changed = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            changed.append(path)
    return changed


def _install_fake_bt(workspace_root: Path, scenario: Scenario) -> Path:
    bin_dir = workspace_root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper = bin_dir / "bt"
    fake_bt = harness_root() / "harness" / "fake_bt.py"
    wrapper.write_text(
        "#!/usr/bin/env python3\n"
        "import runpy, sys\n"
        f"sys.argv = [{str(fake_bt)!r}] + sys.argv[1:]\n"
        f"runpy.run_path({str(fake_bt)!r}, run_name='__main__')\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return bin_dir


def _install_skill(workspace_root: Path, skill_variant: str) -> Optional[Path]:
    if skill_variant == "none":
        return None

    if skill_variant == "current":
        src = repository_root() / "skills" / "bt-flywheel"
    else:
        src = Path(skill_variant)
        if not src.is_absolute():
            src = (Path.cwd() / src).resolve()

    if not src.exists():
        raise FileNotFoundError("Skill variant path does not exist: " + str(src))

    dst = workspace_root / "skills" / ("bt-flywheel-" + skill_variant.replace("/", "_"))
    _copytree(src, dst)
    return dst


def prepare_workspace(
    scenario: Scenario,
    skill_variant: str,
    workspace_root: Optional[Path] = None,
) -> Workspace:
    root = workspace_root or Path(tempfile.mkdtemp(prefix="bt-flywheel-harness-"))
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    _copytree(scenario.fixture_dir, repo)
    bin_dir = _install_fake_bt(root, scenario)
    command_log = root / "bt-command-log.jsonl"
    skill_path = _install_skill(root, skill_variant)

    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["FAKE_BT_FIXTURE"] = str(scenario.path)
    env["FAKE_BT_COMMAND_LOG"] = str(command_log)
    env["FAKE_BT_STRICT"] = env.get("FAKE_BT_STRICT", "1")
    env["BT_FLYWHEEL_HARNESS_REPO"] = str(repo)
    if skill_path:
        env["BT_FLYWHEEL_SKILL_PATH"] = str(skill_path)

    return Workspace(
        root=root,
        repo=repo,
        bin_dir=bin_dir,
        command_log=command_log,
        skill_path=skill_path,
        env=env,
    )


def build_prompt(scenario: Scenario, workspace: Workspace, skill_variant: str) -> str:
    skill_block = (
        "Do not use the bt-flywheel skill for this run; use general coding-agent judgment."
        if skill_variant == "none"
        else "Use the bt-flywheel skill at: {0}".format(workspace.skill_path)
    )
    return textwrap.dedent(
        """\
        You are running an offline bt-flywheel harness scenario against a fixture repo.

        Repository: {repo}
        Braintrust access: use the fake `bt` command already on PATH. Do not look for real credentials.
        Skill mode: {skill_block}

        Task:
        {task}

        On exit, write:
        - bt-flywheel-summary.json
        - bt-flywheel-narrative.md

        The summary must use the adapter-neutral bt-flywheel handoff contract.
        """
    ).format(
        repo=workspace.repo,
        skill_block=skill_block,
        task=scenario.manifest["task"],
    )


def _run_command(
    argv: List[str],
    cwd: Path,
    env: Dict[str, str],
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        return {
            "argv": argv,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_seconds": round(time.time() - started, 3),
        }
    except subprocess.TimeoutExpired as e:
        return {
            "argv": argv,
            "returncode": 124,
            "stdout": e.stdout or "",
            "stderr": e.stderr or "command timed out",
            "duration_seconds": round(time.time() - started, 3),
        }


def _run_bt(workspace: Workspace, *args: str) -> Dict[str, Any]:
    return _run_command(["bt"] + list(args), workspace.repo, workspace.env)


def _summary_base(
    scenario: Scenario,
    outcome: str,
    severity: str,
    blocking: bool,
    confidence: str,
    summary: str,
    findings: List[str],
    changes: Dict[str, List[str]],
    verification: Dict[str, Any],
    next_steps: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "contract_version": "bt-flywheel-handoff/v1",
        "run_id": "offline-harness:{0}:scripted".format(scenario.id),
        "timestamp": "2026-05-12T00:00:00Z",
        "mode": "offline_harness",
        "goal": scenario.manifest["goal"],
        "phases_run": ["orient", "discover", "diagnose", "improve", "verify_decide"],
        "outcome": outcome,
        "severity": severity,
        "blocking": blocking,
        "confidence": confidence,
        "summary": summary,
        "findings": findings,
        "changes": {
            "agent": changes.get("agent", []),
            "measurement": changes.get("measurement", []),
            "datasets": changes.get("datasets", []),
            "instrumentation": changes.get("instrumentation", []),
        },
        "verification": verification,
        "regressions": [],
        "links": [],
        "artifacts": [
            {"path": SUMMARY_FILE, "kind": "handoff"},
            {"path": NARRATIVE_FILE, "kind": "narrative"},
        ],
        "next_steps": next_steps,
    }


def _scripted_measurement_gap(scenario: Scenario, workspace: Workspace) -> None:
    _run_bt(
        workspace,
        "sql",
        "SELECT id, input, output FROM project_logs WHERE search(output, 'citation') LIMIT 20",
    )
    _run_bt(workspace, "view", "trace-cite-001")

    scorer_dir = workspace.repo / "scorers"
    scorer_dir.mkdir(exist_ok=True)
    (scorer_dir / "citation_compliance.py").write_text(
        textwrap.dedent(
            """\
            def score_citation_compliance(answer):
                text = (answer or "").lower()
                has_source = "source:" in text or "[source" in text
                return 1.0 if has_source else 0.0
            """
        ),
        encoding="utf-8",
    )
    evals_dir = workspace.repo / "evals"
    evals_dir.mkdir(exist_ok=True)
    (evals_dir / "citation_cases.jsonl").write_text(
        '{"input":"What is the escalation policy?","expected":"include citation"}\n',
        encoding="utf-8",
    )

    findings = [
        "Measurement gap: 38 citation-policy traces omit required sources while helpfulness remains high.",
        "bt sql search(output, 'citation') surfaced repeated missing-citation failures.",
        "bt view trace-cite-001 shows a factually plausible answer with no source citation.",
    ]
    summary = _summary_base(
        scenario,
        outcome="needs_work",
        severity="warning",
        blocking=False,
        confidence="high",
        summary="Added measurement for missing citation compliance before changing agent behavior.",
        findings=findings,
        changes={
            "measurement": ["scorers/citation_compliance.py: Added citation-compliance scorer."],
            "datasets": ["evals/citation_cases.jsonl: Added seed citation compliance case."],
        },
        verification={
            "status": "smoke_passed",
            "metric_delta": {"citation-compliance": 0.0},
            "regression_count": 0,
        },
        next_steps=[
            {
                "intent": "review_change",
                "priority": "normal",
                "blocking": False,
                "suggested_destination": "code_review",
                "title": "Review citation-compliance measurement",
                "body_markdown": "New scorer exposes missing-citation failures before agent iteration.",
                "requires_human_review": True,
                "idempotency_key": "offline-harness:measurement-gap:review_change",
            }
        ],
    )
    _write_json(workspace.repo / SUMMARY_FILE, summary)
    (workspace.repo / NARRATIVE_FILE).write_text("\n".join(findings) + "\n", encoding="utf-8")


def _scripted_agent_bug(scenario: Scenario, workspace: Workspace) -> None:
    _run_bt(
        workspace,
        "sql",
        "SELECT id, scores FROM project_logs WHERE metadata.query_type = 'math' LIMIT 20",
    )
    _run_bt(workspace, "view", "trace-math-042")
    agent_path = workspace.repo / "src" / "agent.py"
    content = agent_path.read_text(encoding="utf-8")
    content = content.replace(
        'SYSTEM_PROMPT = "Answer math questions concisely."',
        'SYSTEM_PROMPT = "Answer math questions step-by-step and verify intermediate arithmetic before finalizing."',
    )
    agent_path.write_text(content, encoding="utf-8")

    findings = [
        "Math traces average 0.38 versus 0.81 for non-math traffic.",
        "bt view trace-math-042 shows the agent skips intermediate arithmetic verification.",
        "Root cause is the system prompt: it asks for concise answers but not step-by-step verification.",
    ]
    summary = _summary_base(
        scenario,
        outcome="improved",
        severity="info",
        blocking=False,
        confidence="high",
        summary="Added step-by-step arithmetic verification to the agent prompt.",
        findings=findings,
        changes={
            "agent": [
                "src/agent.py: Added step-by-step arithmetic verification instruction to SYSTEM_PROMPT."
            ]
        },
        verification={
            "status": "full_passed",
            "metric_delta": {"math-accuracy": 0.21, "combined-score": 0.09},
            "regression_count": 0,
        },
        next_steps=[
            {
                "intent": "review_change",
                "priority": "normal",
                "blocking": False,
                "suggested_destination": "code_review",
                "title": "Review math prompt improvement",
                "body_markdown": "Trace evidence showed skipped arithmetic steps; fixture checks now pass.",
                "requires_human_review": True,
                "idempotency_key": "offline-harness:agent-bug:review_change",
            }
        ],
    )
    _write_json(workspace.repo / SUMMARY_FILE, summary)
    (workspace.repo / NARRATIVE_FILE).write_text("\n".join(findings) + "\n", encoding="utf-8")


def _scripted_blocked_no_convergence(scenario: Scenario, workspace: Workspace) -> None:
    _run_bt(workspace, "sql", "SELECT experiment_id, score FROM experiments ORDER BY created DESC LIMIT 4")
    _run_bt(workspace, "view", "experiment-exp-003")
    findings = [
        "Three prior iterations oscillated between 0.49 and 0.52 with no durable improvement.",
        "The latest prompt change regressed two previously passing traces and was reverted.",
        "No safe local code, dataset, or measurement change has a clear evidence-backed next step.",
    ]
    summary = _summary_base(
        scenario,
        outcome="no_convergence",
        severity="warning",
        blocking=False,
        confidence="medium",
        summary="Stopped after repeated non-converging iterations and handed off investigation.",
        findings=findings,
        changes={},
        verification={
            "status": "not_run",
            "metric_delta": {"combined-score": -0.01},
            "regression_count": 0,
        },
        next_steps=[
            {
                "intent": "investigate",
                "priority": "normal",
                "blocking": False,
                "suggested_destination": "issue_tracker",
                "title": "Investigate non-converging flywheel run",
                "body_markdown": "Three attempts failed to create durable score movement; human diagnosis is needed.",
                "requires_human_review": True,
                "idempotency_key": "offline-harness:no-convergence:investigate",
            }
        ],
    )
    summary["phases_run"] = [
        "orient",
        "discover",
        "diagnose",
        "improve",
        "verify_decide",
        "improve",
        "verify_decide",
        "improve",
        "verify_decide",
    ]
    _write_json(workspace.repo / SUMMARY_FILE, summary)
    (workspace.repo / NARRATIVE_FILE).write_text("\n".join(findings) + "\n", encoding="utf-8")


SCRIPTED_RUNNERS = {
    "measurement_gap": _scripted_measurement_gap,
    "agent_bug": _scripted_agent_bug,
    "blocked_no_convergence": _scripted_blocked_no_convergence,
}


def run_scripted(scenario: Scenario, workspace: Workspace, prompt: str) -> Dict[str, Any]:
    del prompt
    handler = SCRIPTED_RUNNERS.get(scenario.id)
    if not handler:
        return {"returncode": 2, "stdout": "", "stderr": "No scripted runner for " + scenario.id}
    handler(scenario, workspace)
    return {"returncode": 0, "stdout": "scripted runner completed", "stderr": ""}


def run_external_command(
    scenario: Scenario,
    workspace: Workspace,
    prompt: str,
    command_template: str,
) -> Dict[str, Any]:
    prompt_path = workspace.root / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    rendered = command_template.format(
        repo=str(workspace.repo),
        prompt_file=str(prompt_path),
        prompt=prompt.replace("\n", "\\n"),
        skill_path=str(workspace.skill_path or ""),
        scenario_id=scenario.id,
    )
    argv = shlex.split(rendered)
    return _run_command(argv, workspace.repo, workspace.env, timeout_seconds=1800)


def build_claude_argv(workspace: Workspace, prompt: str) -> List[str]:
    """Build a Claude Code non-interactive command for a single harness scenario."""
    claude_bin = os.getenv("FLYWHEEL_CLAUDE_BIN", "claude")
    output_format = os.getenv("FLYWHEEL_CLAUDE_OUTPUT_FORMAT", "text")
    argv = [
        claude_bin,
        "--print",
        "--bare",
        "--no-session-persistence",
        "--permission-mode",
        os.getenv("FLYWHEEL_CLAUDE_PERMISSION_MODE", "bypassPermissions"),
        "--output-format",
        output_format,
        "--add-dir",
        str(workspace.repo),
    ]
    if workspace.skill_path:
        argv.extend(["--add-dir", str(workspace.skill_path)])

    model = os.getenv("FLYWHEEL_CLAUDE_MODEL")
    if model:
        argv.extend(["--model", model])

    max_budget = os.getenv("FLYWHEEL_CLAUDE_MAX_BUDGET_USD")
    if max_budget:
        argv.extend(["--max-budget-usd", max_budget])

    extra_args = os.getenv("FLYWHEEL_CLAUDE_EXTRA_ARGS")
    if extra_args:
        argv.extend(shlex.split(extra_args))

    argv.extend(["-p", prompt])
    return argv


def run_claude(
    scenario: Scenario,
    workspace: Workspace,
    prompt: str,
) -> Dict[str, Any]:
    del scenario
    argv = build_claude_argv(workspace, prompt)
    return _run_command(argv, workspace.repo, workspace.env, timeout_seconds=1800)


def _read_summary(repo: Path) -> Dict[str, Any]:
    path = repo / SUMMARY_FILE
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        return {"_parse_error": str(e)}


def _read_command_log(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"raw": line})
    return entries


def _matches_any(path: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _flatten_summary_text(summary: Dict[str, Any]) -> str:
    return json.dumps(summary, sort_keys=True).lower()


def _check_handoff_contract(summary: Dict[str, Any]) -> Dict[str, Any]:
    required = {
        "contract_version",
        "run_id",
        "timestamp",
        "mode",
        "goal",
        "phases_run",
        "outcome",
        "severity",
        "blocking",
        "confidence",
        "summary",
        "findings",
        "changes",
        "verification",
        "regressions",
        "links",
        "artifacts",
        "next_steps",
    }
    missing = sorted(required - set(summary))
    next_steps = summary.get("next_steps") if isinstance(summary.get("next_steps"), list) else []
    step_required = {
        "intent",
        "priority",
        "blocking",
        "title",
        "body_markdown",
        "requires_human_review",
        "idempotency_key",
    }
    missing_step_fields = []
    for step in next_steps:
        if isinstance(step, dict):
            fields = sorted(step_required - set(step))
            if fields:
                missing_step_fields.append({"intent": step.get("intent"), "fields": fields})
    score = 1.0
    if missing:
        score -= 0.6
    if not next_steps:
        score -= 0.2
    if missing_step_fields:
        score -= 0.2
    return {
        "name": "handoff_contract",
        "score": max(0.0, score),
        "metadata": {
            "missing": missing,
            "missing_step_fields": missing_step_fields,
            "contract_version": summary.get("contract_version"),
        },
    }


def _run_acceptance(workspace: Workspace, scenario: Scenario) -> List[Dict[str, Any]]:
    results = []
    for command in scenario.manifest.get("acceptance", []):
        if not isinstance(command, list):
            raise ValueError("Acceptance commands must be argv lists in " + scenario.id)
        results.append(_run_command(command, workspace.repo, workspace.env))
    return results


def _score_acceptance(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not results:
        return {"name": "acceptance", "score": 1.0, "metadata": {"commands": 0}}
    failed = [r for r in results if r["returncode"] != 0]
    return {
        "name": "acceptance",
        "score": 0.0 if failed else 1.0,
        "metadata": {
            "commands": len(results),
            "failed": [
                {
                    "argv": r["argv"],
                    "returncode": r["returncode"],
                    "stderr": r["stderr"][-500:],
                }
                for r in failed
            ],
        },
    }


def score_run(
    scenario: Scenario,
    summary: Dict[str, Any],
    changed: List[str],
    command_log: List[Dict[str, Any]],
    acceptance_results: List[Dict[str, Any]],
    runner_result: Dict[str, Any],
) -> Dict[str, Any]:
    expected = scenario.manifest["expected"]
    checks = []

    checks.append(
        {
            "name": "runner_completed",
            "score": 1.0 if runner_result.get("returncode") == 0 else 0.0,
            "metadata": {
                "returncode": runner_result.get("returncode"),
                "stderr": (runner_result.get("stderr") or "")[-500:],
            },
        }
    )

    checks.append(
        {
            "name": "summary_present",
            "score": 1.0 if summary and "_parse_error" not in summary else 0.0,
            "metadata": {"parse_error": summary.get("_parse_error")},
        }
    )
    checks.append(_check_handoff_contract(summary))

    allowed_outcomes = expected.get("outcomes", [])
    checks.append(
        {
            "name": "expected_outcome",
            "score": 1.0 if summary.get("outcome") in allowed_outcomes else 0.0,
            "metadata": {"expected": allowed_outcomes, "actual": summary.get("outcome")},
        }
    )

    actual_intents = [
        step.get("intent")
        for step in summary.get("next_steps", [])
        if isinstance(step, dict)
    ]
    required_intents = expected.get("required_next_step_intents", [])
    checks.append(
        {
            "name": "next_step_intents",
            "score": 1.0 if all(intent in actual_intents for intent in required_intents) else 0.0,
            "metadata": {"required": required_intents, "actual": actual_intents},
        }
    )

    text = _flatten_summary_text(summary)
    missing_terms = [term for term in expected.get("required_terms", []) if term.lower() not in text]
    checks.append(
        {
            "name": "evidence_terms",
            "score": 1.0 if not missing_terms else 0.0,
            "metadata": {"missing": missing_terms},
        }
    )

    allowed = expected.get("allowed_changed_paths", [])
    unexpected = [path for path in changed if not _matches_any(path, allowed)]
    checks.append(
        {
            "name": "change_policy",
            "score": 1.0 if not unexpected else 0.0,
            "metadata": {"changed": changed, "unexpected": unexpected, "allowed": allowed},
        }
    )

    forbidden = expected.get("forbidden_changed_paths", [])
    forbidden_changed = [path for path in changed if _matches_any(path, forbidden)]
    checks.append(
        {
            "name": "forbidden_changes",
            "score": 1.0 if not forbidden_changed else 0.0,
            "metadata": {"forbidden_changed": forbidden_changed},
        }
    )

    commands = [" ".join(entry.get("argv", [])) for entry in command_log]
    missing_bt = []
    for requirement in expected.get("required_bt", []):
        prefix = requirement.get("argv0")
        contains = [str(term).lower() for term in requirement.get("contains", [])]
        found = False
        for entry in command_log:
            argv = entry.get("argv", [])
            command = " ".join(argv).lower()
            if prefix and (not argv or argv[0] != prefix):
                continue
            if all(term in command for term in contains):
                found = True
                break
        if not found:
            missing_bt.append(requirement)
    checks.append(
        {
            "name": "bt_usage",
            "score": 1.0 if not missing_bt else 0.0,
            "metadata": {"commands": commands, "missing": missing_bt},
        }
    )

    checks.append(_score_acceptance(acceptance_results))

    score = sum(check["score"] for check in checks) / len(checks)
    return {"score": round(score, 4), "checks": checks}


def run_scenario(
    scenario_id: str,
    skill_variant: str = "current",
    runner: str = "scripted",
    workspace_root: Optional[Path] = None,
    command_template: Optional[str] = None,
    keep_workspace: bool = False,
) -> Dict[str, Any]:
    scenario = load_scenarios([scenario_id])[0]
    workspace = prepare_workspace(scenario, skill_variant, workspace_root)
    before = snapshot_files(workspace.repo)
    prompt = build_prompt(scenario, workspace, skill_variant)

    if runner == "scripted":
        runner_result = run_scripted(scenario, workspace, prompt)
    elif runner == "claude":
        runner_result = run_claude(scenario, workspace, prompt)
    elif runner == "command":
        template = command_template or os.getenv("FLYWHEEL_RUNNER_COMMAND")
        if not template:
            raise ValueError("runner='command' requires FLYWHEEL_RUNNER_COMMAND or command_template")
        runner_result = run_external_command(scenario, workspace, prompt, template)
    else:
        raise ValueError("Unsupported runner: " + runner)

    acceptance_results = _run_acceptance(workspace, scenario)
    after = snapshot_files(workspace.repo)
    changed = changed_files(before, after)
    summary = _read_summary(workspace.repo)
    command_log = _read_command_log(workspace.command_log)
    scoring = score_run(scenario, summary, changed, command_log, acceptance_results, runner_result)

    output = {
        "scenario_id": scenario.id,
        "skill_variant": skill_variant,
        "runner": runner,
        "workspace": str(workspace.root),
        "repo": str(workspace.repo),
        "prompt": prompt,
        "runner_result": runner_result,
        "summary": summary,
        "changed_files": changed,
        "bt_command_log": command_log,
        "acceptance": acceptance_results,
        "score": scoring["score"],
        "checks": scoring["checks"],
    }

    if not keep_workspace and workspace_root is None:
        shutil.rmtree(str(workspace.root), ignore_errors=True)
        output["workspace"] = None
        output["repo"] = None

    return output


def run_matrix(
    scenario_ids: Optional[Iterable[str]] = None,
    skill_variants: Optional[Iterable[str]] = None,
    runner: str = "scripted",
    keep_workspace: bool = False,
) -> List[Dict[str, Any]]:
    scenarios = load_scenarios(scenario_ids)
    variants = list(skill_variants or ["current"])
    results = []
    for scenario in scenarios:
        for variant in variants:
            results.append(
                run_scenario(
                    scenario.id,
                    skill_variant=variant,
                    runner=runner,
                    keep_workspace=keep_workspace,
                )
            )
    return results


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the offline bt-flywheel harness.")
    parser.add_argument("--scenario", action="append", help="Scenario id. Defaults to all.")
    parser.add_argument(
        "--skill-variant",
        action="append",
        default=None,
        help="Skill variant: none, current, or a path. Defaults to current.",
    )
    parser.add_argument("--runner", default="scripted", choices=["scripted", "claude", "command"])
    parser.add_argument("--keep-workspace", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print full JSON results.")
    args = parser.parse_args(argv)

    results = run_matrix(
        scenario_ids=args.scenario,
        skill_variants=args.skill_variant or ["current"],
        runner=args.runner,
        keep_workspace=args.keep_workspace,
    )
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for result in results:
            print(
                "{scenario_id}\t{skill_variant}\t{runner}\t{score}".format(
                    **result
                )
            )
    failed = [r for r in results if r["score"] < 1.0]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
