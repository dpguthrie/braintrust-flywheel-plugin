"""Minimal Docker-friendly Braintrust Eval for bt-flywheel.

This is intentionally separate from the Harbor suite. It runs under `bt eval`
and each row launches one agent subprocess inside a prepared container.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from braintrust import Eval

try:
    from braintrust.span_identifier_v4 import SpanComponentsV4
except Exception:  # pragma: no cover - older SDK fallback.
    SpanComponentsV4 = None  # type: ignore[assignment]


DOCKER_DIR = Path(__file__).resolve().parent
REPO_ROOT = DOCKER_DIR.parents[1]
HARBOR_DIR = DOCKER_DIR.parent / "bt-flywheel-harbor"
CASES_PATH = DOCKER_DIR / "cases.json"
TASKS_DIR = HARBOR_DIR / "harbor" / "tasks"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


@dataclass(frozen=True)
class TraceContext:
    parent_span_id: str | None
    root_span_id: str | None
    experiment_id: str | None
    exported_parent: str | None


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def env_csv(name: str) -> set[str]:
    value = os.getenv(name, "")
    return {part.strip() for part in value.split(",") if part.strip()}


def load_cases() -> list[dict[str, Any]]:
    selected_scenarios = env_csv("BT_FLYWHEEL_DOCKER_SCENARIOS")
    selected_variants = env_csv("BT_FLYWHEEL_DOCKER_SKILL_VARIANTS")
    command_override = os.getenv("BT_FLYWHEEL_DOCKER_COMMAND_JSON")
    rows: list[dict[str, Any]] = []

    for case in read_json(CASES_PATH)["cases"]:
        metadata = case["metadata"]
        if selected_scenarios and metadata["scenario"] not in selected_scenarios:
            continue
        if selected_variants and metadata["skill_variant"] not in selected_variants:
            continue

        input_value = dict(case["input"])
        if command_override:
            input_value["command"] = json.loads(command_override)

        fixture = read_json(TASKS_DIR / metadata["scenario"] / "environment" / "fixtures" / "scenario.json")
        rows.append(
            {
                "input": input_value,
                "expected": case.get("expected", fixture["expected"]),
                "metadata": {
                    "suite": "bt-flywheel-docker",
                    "execution": "docker-bt-eval-subprocess",
                    **metadata,
                },
            }
        )

    if not rows:
        raise ValueError("No bt-flywheel Docker cases selected")
    return rows


def prepare_workspace(scenario: str, skill_available: bool) -> tuple[Path, Path]:
    run_dir = Path(tempfile.mkdtemp(prefix=f"bt-flywheel-docker-{scenario}-"))
    workspace = run_dir / "workspace"
    shutil.copytree(TASKS_DIR / scenario / "environment", workspace)
    (workspace / "artifacts").mkdir(exist_ok=True)
    (workspace / ".bt").mkdir(exist_ok=True)
    (workspace / ".bt" / "config.json").write_text(
        json.dumps({"project": "Support Agent", "project_id": "proj_support_agent"}, indent=2) + "\n",
        encoding="utf-8",
    )

    source_skill = workspace / "skills" / "bt-flywheel"
    claude_skill = workspace / ".claude" / "skills" / "bt-flywheel"
    if skill_available and source_skill.exists():
        claude_skill.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_skill, claude_skill)
    else:
        shutil.rmtree(workspace / "skills", ignore_errors=True)
        shutil.rmtree(workspace / ".claude", ignore_errors=True)

    return run_dir, workspace


def expand_command(command: list[str], *, prompt: str, model: str, workspace: Path) -> list[str]:
    replacements = {
        "{prompt}": prompt,
        "{model}": model,
        "{workspace}": str(workspace),
        "{repo_root}": str(REPO_ROOT),
        "{suite_dir}": str(DOCKER_DIR),
    }
    expanded: list[str] = []
    for item in command:
        for key, value in replacements.items():
            item = item.replace(key, value)
        expanded.append(item)
    return expanded


def parse_trace_context(span: Any) -> TraceContext:
    exported = None
    try:
        exported = span.export()
    except Exception:
        exported = None

    if exported and SpanComponentsV4 is not None:
        try:
            components = SpanComponentsV4.from_str(exported)
            object_type = getattr(components.object_type, "name", "")
            return TraceContext(
                parent_span_id=components.span_id,
                root_span_id=components.root_span_id,
                experiment_id=components.object_id if object_type == "EXPERIMENT" else None,
                exported_parent=exported,
            )
        except Exception:
            pass

    return TraceContext(
        parent_span_id=getattr(span, "id", None),
        root_span_id=None,
        experiment_id=None,
        exported_parent=exported,
    )


def trace_claude_enabled() -> bool:
    configured = os.getenv("BT_FLYWHEEL_DOCKER_TRACE_CLAUDE")
    if configured is not None:
        return configured == "1" or configured.lower() == "true"
    return os.getenv("UPLOAD") == "1"


def subprocess_env(input_value: dict[str, Any], workspace: Path, trace_context: TraceContext) -> dict[str, str]:
    env = {key: str(value) for key, value in os.environ.items()}
    env.update({key: str(value) for key, value in input_value.get("env_vars", {}).items()})
    env["PATH"] = f"{workspace / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    env["BT_PROJECT_SNAPSHOT_FILE"] = str(workspace / "fixtures" / "scenario.json")
    env["BT_COMMAND_LOG"] = str(workspace / "artifacts" / "bt-command-log.jsonl")
    env["BT_WRITE_DIR"] = str(workspace / "artifacts")
    env["FLYWHEEL_AUTONOMOUS"] = "true"
    env.setdefault("BRAINTRUST_DEFAULT_PROJECT", "Support Agent")

    if trace_claude_enabled():
        env["TRACE_TO_BRAINTRUST"] = "true"
        env.setdefault("BRAINTRUST_CC_PROJECT", os.getenv("BRAINTRUST_EVAL_PROJECT", "bt-flywheel"))
        if trace_context.parent_span_id:
            env["CC_PARENT_SPAN_ID"] = trace_context.parent_span_id
        if trace_context.root_span_id:
            env["CC_ROOT_SPAN_ID"] = trace_context.root_span_id
        if trace_context.experiment_id:
            env["CC_EXPERIMENT_ID"] = trace_context.experiment_id

    return env


def first_existing(*paths: Path) -> Path | None:
    return next((path for path in paths if path.exists()), None)


def collect_artifacts(workspace: Path) -> dict[str, Any]:
    summary_path = first_existing(workspace / "artifacts" / "bt-flywheel-summary.json", workspace / "bt-flywheel-summary.json")
    narrative_path = first_existing(workspace / "artifacts" / "bt-flywheel-narrative.md", workspace / "bt-flywheel-narrative.md")
    command_log_path = workspace / "artifacts" / "bt-command-log.jsonl"
    return {
        "summary_json": read_json(summary_path) if summary_path else None,
        "narrative_text": narrative_path.read_text(encoding="utf-8") if narrative_path else "",
        "command_log": read_jsonl(command_log_path),
        "artifact_paths": {
            "summary": str(summary_path.relative_to(workspace)) if summary_path else None,
            "narrative": str(narrative_path.relative_to(workspace)) if narrative_path else None,
            "command_log": str(command_log_path.relative_to(workspace)) if command_log_path.exists() else None,
        },
    }


def truncate(text: str, limit: int = 12000) -> str:
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def log_bt_command_spans(hooks: Any, command_log: list[dict[str, Any]]) -> None:
    for index, row in enumerate(command_log):
        command_class = str(row.get("command_class") or "unknown")
        with hooks.span.start_span(name=f"bt.{command_class}", type="tool") as span:
            span.log(
                input={"argv": row.get("argv"), "cwd": row.get("cwd")},
                output={"mutating": row.get("mutating")},
                metadata={"index": index, "scenario": row.get("scenario")},
            )


async def run_agent(input_value: dict[str, Any], hooks: Any) -> dict[str, Any]:
    metadata = hooks.metadata or {}
    scenario = metadata["scenario"]
    skill_available = bool(metadata["skill_available"])
    timeout_sec = float(os.getenv("BT_FLYWHEEL_DOCKER_TIMEOUT_SEC", "300"))
    keep_workspace = os.getenv("BT_FLYWHEEL_DOCKER_KEEP_WORKSPACE") == "1"
    run_dir, workspace = prepare_workspace(scenario, skill_available)
    command = expand_command(
        input_value["command"],
        prompt=input_value["prompt"],
        model=input_value.get("model", os.getenv("BT_FLYWHEEL_DOCKER_MODEL", DEFAULT_CLAUDE_MODEL)),
        workspace=workspace,
    )

    start = time.perf_counter()
    timed_out = False
    returncode = 1
    stdout_text = ""
    stderr_text = ""
    trace_context = TraceContext(None, None, None, None)

    with hooks.span.start_span(name="agent.subprocess", type="tool") as span:
        trace_context = parse_trace_context(span)
        span.log(
            input={"command": command, "cwd": str(workspace), "trace_claude": trace_claude_enabled()},
            metadata={
                "parent_span_id": trace_context.parent_span_id,
                "root_span_id": trace_context.root_span_id,
                "experiment_id": trace_context.experiment_id,
            },
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workspace,
            env=subprocess_env(input_value, workspace, trace_context),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_sec)
            returncode = int(process.returncode or 0)
        except TimeoutError:
            timed_out = True
            process.kill()
            stdout, stderr = await process.communicate()
            returncode = 124

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        span.log(output={"returncode": returncode, "timed_out": timed_out})

    if returncode != 0 or timed_out:
        print(
            f"[bt-flywheel docker] agent command failed: returncode={returncode} timed_out={timed_out}",
            file=sys.stderr,
            flush=True,
        )
        diagnostic = stderr_text.strip() or stdout_text.strip()
        if diagnostic:
            print(truncate(diagnostic, 4000), file=sys.stderr, flush=True)

    artifacts = collect_artifacts(workspace)
    log_bt_command_spans(hooks, artifacts["command_log"])
    output = {
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_sec": round(time.perf_counter() - start, 3),
        "command": command,
        "stdout": truncate(stdout_text),
        "stderr": truncate(stderr_text),
        "workspace": str(run_dir) if keep_workspace else None,
        "trace_context": {
            "trace_claude": trace_claude_enabled(),
            "parent_span_id": trace_context.parent_span_id,
            "root_span_id": trace_context.root_span_id,
            "experiment_id": trace_context.experiment_id,
            "exported_parent": trace_context.exported_parent,
        },
        **artifacts,
    }

    if not keep_workspace:
        shutil.rmtree(run_dir, ignore_errors=True)
    return output


def score(name: str, value: bool | float, **metadata: Any) -> dict[str, Any]:
    return {"name": name, "score": float(value), "metadata": metadata}


def command_succeeded(input: Any, output: dict[str, Any], expected: Any) -> dict[str, Any]:
    del input, expected
    return score("Command succeeded", output["returncode"] == 0 and not output["timed_out"], returncode=output["returncode"])


def produced_handoff(input: Any, output: dict[str, Any], expected: Any) -> dict[str, Any]:
    del input, expected
    paths = output["artifact_paths"]
    missing = [name for name, path in paths.items() if path is None]
    return score("Produced handoff", not missing, missing=missing)


def valid_handoff(input: Any, output: dict[str, Any], expected: Any) -> dict[str, Any]:
    del input, expected
    summary = output.get("summary_json") or {}
    ok = summary.get("contract_version") == "bt-flywheel-handoff/v1" and bool(summary.get("next_steps"))
    return score("Valid handoff", ok)


def expected_route(input: Any, output: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    del input
    summary = output.get("summary_json") or {}
    changes = summary.get("changes") or {}
    next_steps = summary.get("next_steps") or []
    first_step = next_steps[0] if next_steps else None
    first_intent = first_step.get("intent") if isinstance(first_step, dict) else None

    route = expected["route"]
    if route == "healthy":
        ok = summary.get("outcome") == "healthy" and first_intent == "no_action"
    elif route == "measurement":
        ok = bool(changes.get("measurement")) and not changes.get("agent") and not changes.get("datasets")
    elif route == "dataset":
        ok = bool(changes.get("datasets")) and not changes.get("agent")
    else:
        ok = False

    return score("Expected route", ok, expected_route=route, outcome=summary.get("outcome"), first_intent=first_intent)


def trace_context_wired(input: Any, output: dict[str, Any], expected: Any) -> dict[str, Any]:
    del input, expected
    context = output.get("trace_context") or {}
    enabled = bool(context.get("trace_claude"))
    required = ["parent_span_id", "root_span_id", "experiment_id"] if enabled else ["parent_span_id"]
    missing = [key for key in required if not context.get(key)]
    return score("Trace context wired", not missing, trace_claude=enabled, missing=missing)


Eval(
    os.getenv("BRAINTRUST_EVAL_PROJECT", "bt-flywheel"),
    data=load_cases,
    task=run_agent,
    scores=[command_succeeded, produced_handoff, valid_handoff, expected_route, trace_context_wired],
    experiment_name=os.getenv("BRAINTRUST_EXPERIMENT_NAME") or f"bt-flywheel-docker-{uuid4().hex[:8]}",
    metadata={
        "suite": "bt-flywheel-docker",
        "execution": "docker-bt-eval-subprocess",
        "created_at": datetime.now(timezone.utc).isoformat(),
    },
    max_concurrency=int(os.getenv("BT_FLYWHEEL_DOCKER_MAX_CONCURRENCY", "1")),
)
