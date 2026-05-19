"""Harbor-first runner for the bt-flywheel skill eval.

One Harbor job is treated as one Braintrust experiment. Harbor owns sandboxed
agent execution and concurrency; this script imports each Harbor trial back as
one Braintrust experiment row.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import datetime as dt
from pathlib import Path
from typing import Any
from uuid import uuid4


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from braintrust_harbor import (  # noqa: E402
    HarborBatchConfig,
    import_harbor_job_to_braintrust,
)
from braintrust_harbor.artifacts import latest_child_dir  # noqa: E402
from braintrust_harbor.harbor_batch import HarborBatchResult, write_harbor_job_config  # noqa: E402
from scorers import (  # noqa: E402
    agent_trace_presence_score,
    blast_radius_safety_score,
    evidence_alignment_score,
    harbor_reward_score,
    harness_reliability_score,
    normalized_trace_contract_score,
    process_discipline_score,
    route_correctness_score,
    runtime_cost_efficiency_score,
    schema_validity_score,
    side_effect_safety_score,
    skill_selection_score,
    tool_efficiency_score,
    trace_process_discipline_score,
)
from suite_artifacts import BT_FLYWHEEL_SUITE_ARTIFACTS  # noqa: E402


TASKS_DIR = SCRIPT_DIR / "harbor" / "tasks"
DEFAULT_SUITE_CONFIG_PATH = SCRIPT_DIR / "suite.toml"
DEFAULT_SCENARIOS = ("healthy-exit", "measurement-gap", "dataset-gap")
EVAL_RUN_ID = os.getenv("BT_FLYWHEEL_HARBOR_RUN_ID", uuid4().hex[:8])
GENERATED_ROOT = Path(
    os.getenv(
        "BT_FLYWHEEL_GENERATED_TASKS_DIR",
        str(Path(__file__).resolve().parent / ".generated" / EVAL_RUN_ID),
    )
).resolve()


SCORERS = [
    harbor_reward_score,
    harness_reliability_score,
    normalized_trace_contract_score,
    agent_trace_presence_score,
    schema_validity_score,
    route_correctness_score,
    process_discipline_score,
    trace_process_discipline_score,
    evidence_alignment_score,
    skill_selection_score,
    tool_efficiency_score,
    runtime_cost_efficiency_score,
    side_effect_safety_score,
    blast_radius_safety_score,
]


def _log(message: str) -> None:
    print(f"[bt-flywheel harbor] {message}", flush=True)


def _subprocess_env(cwd: Path) -> dict[str, str]:
    env = os.environ.copy()
    repo_path = str(cwd)
    existing = env.get("PYTHONPATH")
    parts = existing.split(os.pathsep) if existing else []
    if repo_path not in parts:
        env["PYTHONPATH"] = os.pathsep.join([repo_path, *parts]) if parts else repo_path
    return env


def _stream_pipe(pipe: Any, sink: list[str]) -> None:
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            sink.append(line)
            print(line, end="", flush=True)
    finally:
        pipe.close()


def _run_harbor_batch_streaming(config: HarborBatchConfig) -> HarborBatchResult:
    job_name = config.job_name or f"agent-tooling-{uuid4().hex[:12]}"
    command = [
        config.harbor_bin,
        "run",
        "--config",
        config.config_path,
        "--job-name",
        job_name,
        *config.extra_args,
    ]
    cwd = Path.cwd()
    jobs_dir = (cwd / config.jobs_dir).resolve()
    expected_job_dir = jobs_dir / job_name
    start = time.time()
    result = HarborBatchResult(
        job_name=job_name,
        job_dir=None,
        config_path=config.config_path,
        command=command,
        returncode=None,
        started_at=dt.datetime.fromtimestamp(start, tz=dt.UTC).isoformat(),
    )

    if shutil.which(config.harbor_bin) is None:
        result.returncode = 127
        result.error = f"Harbor binary not found: {config.harbor_bin}"
    else:
        _log("starting Harbor job")
        _log("command: " + shlex.join(command))
        output_lines: list[str] = []
        process = subprocess.Popen(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=_subprocess_env(cwd),
            bufsize=1,
        )
        assert process.stdout is not None
        reader = threading.Thread(target=_stream_pipe, args=(process.stdout, output_lines), daemon=True)
        reader.start()
        try:
            result.returncode = process.wait(timeout=config.timeout_sec)
        except subprocess.TimeoutExpired:
            process.kill()
            result.returncode = 124
            result.error = f"Harbor timed out after {config.timeout_sec}s"
        reader.join(timeout=5)
        result.stdout = "".join(output_lines)[-20000:]

    job_dir = expected_job_dir if expected_job_dir.exists() else latest_child_dir(jobs_dir, since=start - 1.0)
    if job_dir is not None:
        result.job_dir = str(job_dir)
    finish = time.time()
    result.finished_at = dt.datetime.fromtimestamp(finish, tz=dt.UTC).isoformat()
    result.duration_sec = round(finish - start, 3)
    return result


def _load_suite_config() -> dict[str, Any]:
    path = Path(os.getenv("BT_FLYWHEEL_SUITE_CONFIG", os.getenv("BT_FLYWHEEL_MATRIX_CONFIG", str(DEFAULT_SUITE_CONFIG_PATH)))).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Suite config not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _env_list(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    value = os.getenv(name)
    if not value:
        return default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _as_tuple(value: Any, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return default


def _enabled_items(items: list[dict[str, Any]], env_filter: str) -> list[dict[str, Any]]:
    selected = set(_env_list(env_filter))
    enabled = [item for item in items if item.get("enabled", True)]
    if selected:
        enabled = [item for item in enabled if item.get("name") in selected]
    return enabled


def _slug(value: str) -> str:
    normalized = value.lower().replace("/", "-").replace("_", "-")
    return "".join(char if char.isalnum() or char == "-" else "-" for char in normalized).strip("-")


def _default_model_for_agent(agent: str) -> str:
    agent_name = agent.lower()
    if agent_name == "claude-code":
        return "anthropic/claude-sonnet-4-6"
    if agent_name in {"gemini", "gemini-cli"}:
        return "google/gemini-2.5-pro"
    return "openai/gpt-5.4"


def _default_agent_for_model(model: str) -> str:
    model_name = model.lower()
    if model_name.startswith(("anthropic/", "claude")):
        return "claude-code"
    if model_name.startswith(("google/", "gemini/")):
        return "gemini"
    return "codex"


def _target_items(suite_config: dict[str, Any]) -> list[dict[str, Any]]:
    env_agent = os.getenv("HARBOR_AGENT")
    env_model = os.getenv("HARBOR_MODEL")
    env_models = _env_list("HARBOR_MODELS")
    if env_agent or env_model or env_models:
        agent = env_agent or _default_agent_for_model(env_model or (env_models[0] if env_models else "openai/gpt-5.4"))
        models = env_models or ((env_model,) if env_model else (_default_model_for_agent(agent),))
        return [
            {
                "name": os.getenv("HARBOR_TARGET_NAME", "env-target"),
                "agent": agent,
                "agent_import_path": os.getenv("HARBOR_AGENT_IMPORT_PATH"),
                "models": list(models),
                "enabled": True,
            }
        ]
    return _enabled_items(suite_config.get("targets", []), "HARBOR_TARGETS")


def _condition_items(suite_config: dict[str, Any]) -> list[dict[str, Any]]:
    if os.getenv("HARBOR_CONDITION"):
        return [{"name": os.getenv("HARBOR_CONDITION"), "enabled": True, "extra_args": []}]
    return _enabled_items(suite_config.get("conditions") or [{"name": "default", "enabled": True}], "HARBOR_CONDITIONS")


def _skill_variant_items(suite_config: dict[str, Any]) -> list[dict[str, Any]]:
    return _enabled_items(suite_config.get("skill_variants") or [{"name": "with-skill", "enabled": True}], "HARBOR_SKILL_VARIANTS")


def _scenario_expected(source_task_path: Path) -> dict[str, Any]:
    with (source_task_path / "environment" / "fixtures" / "scenario.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)["expected"]


def _scenario_prompt(expected_route: str) -> str:
    focus = {
        "healthy": "check whether the production agent is healthy and avoid making unnecessary changes",
        "measurement": "look for behavior that users would call bad even if current scores miss it",
        "dataset": "look for production patterns that are missing from the eval dataset",
    }.get(expected_route, "look for the highest-impact way to improve the agent")
    return (
        "/bt-flywheel help me improve my Braintrust-backed support agent. "
        f"Please {focus}. "
        "Use the available Braintrust project context, inspect traces/evals/datasets as needed, "
        "and leave me a portable handoff with the recommended route, evidence, verification, "
        "and next steps."
    )


def _rewrite_no_skill_instruction(instruction_path: Path) -> None:
    text = instruction_path.read_text(encoding="utf-8")
    text = text.replace(
        "Run the `bt-flywheel` skill against the Braintrust project available in this sandbox.",
        "Investigate the Braintrust project available in this sandbox and produce the same flywheel-style handoff artifacts.",
    )
    text = text.replace(
        "The skill is installed at `/skills/bt-flywheel/SKILL.md`, and the `bt` CLI is already on `PATH`. The CLI is configured for the local Braintrust project and records every `bt` command to `/logs/artifacts/bt-command-log.jsonl`.",
        "No specialized skill is installed for this trial. The `bt` CLI is already on `PATH`; it is configured for the local Braintrust project and records every `bt` command to `/logs/artifacts/bt-command-log.jsonl`.",
    )
    instruction_path.write_text(text, encoding="utf-8")


def _rewrite_no_skill_dockerfile(dockerfile_path: Path) -> None:
    text = dockerfile_path.read_text(encoding="utf-8")
    text = text.replace("COPY skills/ /skills/\n", "RUN mkdir -p /skills\n")
    dockerfile_path.write_text(text, encoding="utf-8")


def _rewrite_no_skill_verifier(verifier_path: Path) -> None:
    text = verifier_path.read_text(encoding="utf-8")
    text = text.replace(
        'SCHEMA_PATH = Path("/skills/bt-flywheel/schemas/bt-flywheel-summary.schema.json")',
        'SCHEMA_PATHS = [\n    Path("/skills/bt-flywheel/schemas/bt-flywheel-summary.schema.json"),\n    Path("/fixtures/bt-flywheel-summary.schema.json"),\n]',
    )
    text = text.replace(
        "    schema = read_json(SCHEMA_PATH)\n    errors = validate_json_schema(summary, schema)",
        '    schema_path = next((path for path in SCHEMA_PATHS if path.exists()), None)\n    if schema_path is None:\n        return criterion("schema_validity", False, "summary schema is unavailable")\n    schema = read_json(schema_path)\n    errors = validate_json_schema(summary, schema)',
    )
    verifier_path.write_text(text, encoding="utf-8")


def _sync_skill_bundle(task_path: Path) -> None:
    source = REPO_ROOT / "skills" / "bt-flywheel"
    target = task_path / "environment" / "skills" / "bt-flywheel"
    if not source.exists():
        return
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _materialize_task_variant(
    *,
    scenario: str,
    skill_variant: str,
    condition: str,
    output_dir: Path,
) -> Path:
    source_task_path = TASKS_DIR / scenario
    task_name = f"{scenario}__{skill_variant}__{condition}" if condition != "default" else f"{scenario}__{skill_variant}"
    generated_task_path = output_dir / task_name
    if generated_task_path.exists():
        shutil.rmtree(generated_task_path)
    shutil.copytree(source_task_path, generated_task_path)
    _sync_skill_bundle(generated_task_path)

    expected = _scenario_expected(source_task_path)
    if skill_variant == "no-skill":
        schema_source = generated_task_path / "environment" / "skills" / "bt-flywheel" / "schemas" / "bt-flywheel-summary.schema.json"
        schema_target = generated_task_path / "environment" / "fixtures" / "bt-flywheel-summary.schema.json"
        if schema_source.exists():
            shutil.copy2(schema_source, schema_target)
        shutil.rmtree(generated_task_path / "environment" / "skills", ignore_errors=True)
        _rewrite_no_skill_instruction(generated_task_path / "instruction.md")
        _rewrite_no_skill_dockerfile(generated_task_path / "environment" / "Dockerfile")
        _rewrite_no_skill_verifier(generated_task_path / "tests" / "verify_flywheel.py")

    sidecar = {
        "task_name": task_name,
        "scenario": scenario,
        "skill_variant": skill_variant,
        "skill_available": skill_variant != "no-skill",
        "condition": condition,
        "expected_route": expected["route"],
        "input": {
            "prompt": _scenario_prompt(str(expected["route"])),
            "project": "Support Agent",
            "skill_invocation": "/bt-flywheel" if skill_variant != "no-skill" else None,
        },
        "expected": expected,
        "metadata": {
            "scenario": scenario,
            "skill": "bt-flywheel",
            "skill_variant": skill_variant,
            "skill_available": skill_variant != "no-skill",
            "condition": condition,
            "expected_route": expected["route"],
        },
    }
    sidecar_text = json.dumps(sidecar, indent=2, sort_keys=True) + "\n"
    (generated_task_path / ".agent-tooling-eval.json").write_text(sidecar_text, encoding="utf-8")
    return generated_task_path


def _agent_env_templates(agent: str, model: str) -> dict[str, str]:
    configured = _env_list("HARBOR_AGENT_ENV_KEYS")
    keys = list(configured)
    agent_name = agent.lower()
    model_name = model.lower()
    if not keys:
        if agent_name == "claude-code" or model_name.startswith("anthropic/"):
            if os.getenv("ANTHROPIC_AUTH_TOKEN"):
                keys.append("ANTHROPIC_AUTH_TOKEN")
            elif os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
                keys.append("CLAUDE_CODE_OAUTH_TOKEN")
            else:
                keys.append("ANTHROPIC_API_KEY")
            if os.getenv("ANTHROPIC_BASE_URL"):
                keys.append("ANTHROPIC_BASE_URL")
        elif agent_name == "codex" or model_name.startswith("openai/"):
            if os.getenv("OPENAI_API_KEY") or not (os.getenv("CODEX_AUTH_JSON_PATH") or os.getenv("CODEX_FORCE_AUTH_JSON")):
                keys.append("OPENAI_API_KEY")
            if os.getenv("OPENAI_BASE_URL"):
                keys.append("OPENAI_BASE_URL")
            if os.getenv("CODEX_AUTH_JSON_PATH"):
                keys.append("CODEX_AUTH_JSON_PATH")
            if os.getenv("CODEX_FORCE_AUTH_JSON"):
                keys.append("CODEX_FORCE_AUTH_JSON")
        if agent_name == "gemini" or model_name.startswith(("google/", "gemini/")):
            keys.append("GEMINI_API_KEY" if os.getenv("GEMINI_API_KEY") else "GOOGLE_API_KEY")
    return {key: f"${{{key}}}" for key in keys if key}


def _agent_missing_env(agent: str, model: str) -> list[str]:
    agent_name = agent.lower()
    model_name = model.lower()
    alternatives: list[tuple[str, ...]] = []
    if agent_name == "claude-code" or model_name.startswith("anthropic/"):
        alternatives.append(("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"))
    elif agent_name == "codex" or model_name.startswith("openai/"):
        if not (os.getenv("CODEX_AUTH_JSON_PATH") or os.getenv("CODEX_FORCE_AUTH_JSON")):
            alternatives.append(("OPENAI_API_KEY",))
    elif agent_name == "gemini" or model_name.startswith(("google/", "gemini/")):
        alternatives.append(("GOOGLE_API_KEY", "GEMINI_API_KEY"))
    return [" or ".join(keys) for keys in alternatives if not any(os.getenv(key) for key in keys)]


def _harbor_agents(targets: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    agents: list[dict[str, Any]] = []
    missing: list[str] = []
    seen: set[tuple[str, str | None, str]] = set()
    for target in targets:
        target_name = str(target.get("name") or target.get("agent") or "target")
        agent = str(target.get("agent", "codex"))
        agent_import_path = target.get("agent_import_path")
        for model in _as_tuple(target.get("models"), (_default_model_for_agent(agent),)):
            key = (agent, str(agent_import_path) if agent_import_path else None, model)
            if key in seen:
                continue
            seen.add(key)
            missing.extend(f"{target_name} ({model}): {item}" for item in _agent_missing_env(agent, model))
            agents.append(
                {
                    "name": agent,
                    "import_path": str(agent_import_path) if agent_import_path else None,
                    "model_name": model,
                    "env": _agent_env_templates(agent, model),
                    "kwargs": target.get("kwargs", {}),
                }
            )
    return agents, missing


def _suite_config_path_for_metadata() -> str:
    return os.getenv("BT_FLYWHEEL_SUITE_CONFIG", os.getenv("BT_FLYWHEEL_MATRIX_CONFIG", str(DEFAULT_SUITE_CONFIG_PATH)))


def _materialize_dataset(suite_config: dict[str, Any]) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    defaults = suite_config.get("defaults", {})
    scenarios = _env_list("HARBOR_SCENARIOS", _as_tuple(defaults.get("scenarios"), DEFAULT_SCENARIOS))
    conditions = _condition_items(suite_config)
    skill_variants = _skill_variant_items(suite_config)
    targets = _target_items(suite_config)

    tasks_dir = GENERATED_ROOT / "tasks"
    if tasks_dir.exists():
        shutil.rmtree(tasks_dir)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        for condition in conditions:
            condition_name = str(condition.get("name", "default"))
            for skill_variant in skill_variants:
                _materialize_task_variant(
                    scenario=scenario,
                    skill_variant=str(skill_variant.get("name", "with-skill")),
                    condition=condition_name,
                    output_dir=tasks_dir,
                )

    agents, missing = _harbor_agents(targets)
    if missing:
        raise RuntimeError("Missing provider credential environment variable(s): " + "; ".join(missing))

    suite_metadata = {
        "suite": "bt-flywheel-harbor",
        "run_id": EVAL_RUN_ID,
        "suite_config": _suite_config_path_for_metadata(),
        "scenarios": list(scenarios),
        "conditions": [str(item.get("name", "default")) for item in conditions],
        "skill_variants": [str(item.get("name", "with-skill")) for item in skill_variants],
        "targets": [str(item.get("name") or item.get("agent") or "target") for item in targets],
        "execution": "harbor-batch",
    }
    return tasks_dir, agents, suite_metadata


def _write_batch_config(suite_config: dict[str, Any], tasks_dir: Path, agents: list[dict[str, Any]]) -> Path:
    defaults = suite_config.get("defaults", {})
    job_name = os.getenv("BRAINTRUST_EXPERIMENT_NAME") or "-".join(
        part for part in ("bt-flywheel", _slug(EVAL_RUN_ID), "harbor-batch") if part
    )
    config = {
        "job_name": job_name,
        "jobs_dir": os.getenv("HARBOR_JOBS_DIR", str(defaults.get("jobs_dir", "jobs"))),
        "n_concurrent_trials": int(os.getenv("HARBOR_MAX_CONCURRENCY", str(defaults.get("max_concurrency", 4)))),
        "n_attempts": int(os.getenv("HARBOR_N_ATTEMPTS", "1")),
        "quiet": os.getenv("HARBOR_QUIET", "0") == "1",
        "retry": {"max_retries": int(os.getenv("HARBOR_MAX_RETRIES", "0"))},
        "environment": {"type": os.getenv("HARBOR_ENV", "docker")},
        "datasets": [{"path": str(tasks_dir)}],
        "agents": agents,
    }
    config_path = GENERATED_ROOT / "harbor-job-config.json"
    write_harbor_job_config(config_path, config)
    return config_path


def main() -> int:
    suite_config = _load_suite_config()
    defaults = suite_config.get("defaults", {})
    tasks_dir, agents, suite_metadata = _materialize_dataset(suite_config)
    config_path = _write_batch_config(suite_config, tasks_dir, agents)
    config_json = json.loads(config_path.read_text(encoding="utf-8"))
    job_name = config_json["job_name"]
    task_count = len([path for path in tasks_dir.iterdir() if path.is_dir()])
    _log(f"generated tasks: {tasks_dir}")
    _log(f"job config: {config_path}")
    _log(
        "planned trials: "
        f"{task_count} task(s), "
        f"{len(agents)} agent/model target(s), "
        f"about {task_count * len(agents)} Harbor trial(s), "
        f"concurrency={config_json.get('n_concurrent_trials')}"
    )
    batch_result = _run_harbor_batch_streaming(
        HarborBatchConfig(
            job_name=job_name,
            config_path=str(config_path),
            jobs_dir=os.getenv("HARBOR_JOBS_DIR", str(defaults.get("jobs_dir", "jobs"))),
            harbor_bin=os.getenv("HARBOR_BIN", str(defaults.get("harbor_bin", "harbor"))),
            timeout_sec=int(os.getenv("HARBOR_BATCH_TIMEOUT_SEC", str(defaults.get("timeout_sec", 7200)))),
            extra_args=tuple(shlex.split(os.getenv("HARBOR_EXTRA_ARGS", ""))),
        )
    )
    if batch_result.job_dir is None:
        print(json.dumps({"harbor": batch_result.as_dict(), "braintrust": None}, indent=2, sort_keys=True))
        return int(batch_result.returncode or 1)

    upload = os.getenv("UPLOAD", "0") == "1"
    import_result = import_harbor_job_to_braintrust(
        job_dir=batch_result.job_dir,
        project=os.getenv("BRAINTRUST_EVAL_PROJECT", str(defaults.get("braintrust_project", "bt-flywheel"))),
        experiment_name=os.getenv("BRAINTRUST_EXPERIMENT_NAME", job_name),
        scorers=SCORERS,
        upload=upload,
        metadata={**suite_metadata, "harbor_job": batch_result.as_dict()},
        suite_artifacts=BT_FLYWHEEL_SUITE_ARTIFACTS,
    )
    print(
        json.dumps(
            {
                "harbor": batch_result.as_dict(),
                "braintrust": {
                    "project": import_result.project,
                    "experiment_name": import_result.experiment_name,
                    "experiment_id": import_result.experiment_id,
                    "uploaded": import_result.uploaded,
                    "row_count": import_result.row_count,
                    "preview_path": import_result.preview_path,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return int(batch_result.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
