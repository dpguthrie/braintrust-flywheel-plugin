#!/usr/bin/env python3
"""Verifier for bt-flywheel Harbor tasks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCENARIO_PATH = Path("/fixtures/scenario.json")
SCHEMA_PATH = Path("/skills/bt-flywheel/schemas/bt-flywheel-summary.schema.json")
ARTIFACTS_DIR = Path("/logs/artifacts")
VERIFIER_DIR = Path("/logs/verifier")


UNCHANGED_FILES = {
    Path("/app/src/agent.py"): '''"""Stable placeholder agent file for side-effect checks."""


SYSTEM_PROMPT = "Answer support questions using the approved support knowledge base."


def route(input_text: str) -> str:
    return "support_answer"
''',
    Path("/app/evals/eval_support.py"): '''"""Placeholder eval path referenced by the local bt CLI."""


CASES = [
    {"input": "How do I reset my password?", "expected": "Use the password reset flow."},
]
''',
    Path("/app/scorers/support_scorers.py"): '''"""Placeholder scorer file for side-effect checks."""


def task_success(output: str, expected: str) -> float:
    return 1.0 if expected.lower() in output.lower() else 0.0
''',
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                rows.append({"parse_error": str(exc), "line_number": line_number, "line": stripped})
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def find_file(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def type_matches(value: Any, expected: Any) -> bool:
    expected_types = expected if isinstance(expected, list) else [expected]
    actual = json_type_name(value)
    if actual == "integer" and "number" in expected_types:
        return True
    return actual in expected_types


def validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: expected one of {schema['enum']!r}, got {value!r}")
    if "type" in schema and not type_matches(value, schema["type"]):
        errors.append(f"{path}: expected type {schema['type']!r}, got {json_type_name(value)!r}")
        return errors
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required key {key!r}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    errors.extend(validate_json_schema(value[key], child_schema, f"{path}.{key}"))
    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} items, got {len(value)}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate_json_schema(item, item_schema, f"{path}[{index}]"))
    return errors


def effectively_empty(value: Any) -> bool:
    if value in (None, "", [], {}):
        return True
    if isinstance(value, list):
        return all(str(item).strip().lower() in {"", "none", "n/a", "no changes"} for item in value)
    return False


def summary_text(summary: dict[str, Any]) -> str:
    parts = [
        summary.get("summary", ""),
        " ".join(str(item) for item in summary.get("findings", [])),
        json.dumps(summary.get("changes", {}), sort_keys=True),
        json.dumps(summary.get("next_steps", []), sort_keys=True),
    ]
    return " ".join(parts).lower()


def criterion(name: str, passed: bool, message: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "score": 1.0 if passed else 0.0,
        "message": message,
        "metadata": metadata or {},
    }


def check_artifact_presence(summary_path: Path | None, narrative_path: Path | None, command_log_path: Path | None) -> dict[str, Any]:
    missing = []
    if summary_path is None:
        missing.append("bt-flywheel-summary.json")
    if narrative_path is None:
        missing.append("bt-flywheel-narrative.md")
    if command_log_path is None:
        missing.append("bt-command-log.jsonl")
    return criterion("artifact_presence", not missing, "required artifacts are present" if not missing else "missing artifacts", {"missing": missing})


def check_schema(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return criterion("schema_validity", False, "summary is not a JSON object")
    schema = read_json(SCHEMA_PATH)
    errors = validate_json_schema(summary, schema)
    return criterion("schema_validity", not errors, "summary validates against the bundled schema" if not errors else "schema validation failed", {"errors": errors[:20]})


def check_route(summary: dict[str, Any], scenario: dict[str, Any], command_log: list[dict[str, Any]]) -> dict[str, Any]:
    expected = scenario["expected"]
    route = expected["route"]
    allowed_outcomes = set(expected.get("allowed_outcomes", []))
    outcome = summary.get("outcome")
    changes = summary.get("changes", {})
    next_steps = summary.get("next_steps", [])
    first_intent = next_steps[0].get("intent") if next_steps and isinstance(next_steps[0], dict) else None
    text = summary_text(summary)
    outcome_ok = outcome in allowed_outcomes
    curated_rows = (ARTIFACTS_DIR / "curated-dataset-rows.json").exists()
    dataset_write = any(row.get("command_class") == "dataset_write" for row in command_log)

    if route == "healthy":
        passed = (
            outcome == "healthy"
            and first_intent == "no_action"
            and effectively_empty(changes.get("agent"))
            and effectively_empty(changes.get("measurement"))
            and effectively_empty(changes.get("datasets"))
            and effectively_empty(changes.get("instrumentation"))
        )
        message = "healthy route exited with no action" if passed else "healthy route should exit without changes"
    elif route == "measurement":
        measurement_signal = bool(changes.get("measurement")) or any(term in text for term in ["measurement", "scorer", "facet", "classifier"])
        passed = (
            outcome_ok
            and measurement_signal
            and effectively_empty(changes.get("agent"))
            and effectively_empty(changes.get("datasets"))
        )
        message = "measurement gap routed to scorer/measurement work" if passed else "measurement gap was not routed to measurement before agent/dataset changes"
    elif route == "dataset":
        dataset_signal = bool(changes.get("datasets")) or curated_rows or dataset_write or "dataset" in text
        passed = outcome_ok and dataset_signal and effectively_empty(changes.get("agent"))
        message = "dataset gap routed to dataset curation" if passed else "dataset gap was not routed to dataset curation"
    else:
        passed = False
        message = f"unknown expected route: {route}"

    return criterion(
        "route_correctness",
        passed,
        message,
        {
            "expected_route": route,
            "outcome": outcome,
            "first_intent": first_intent,
            "curated_rows": curated_rows,
            "dataset_write": dataset_write,
        },
    )


def check_process(command_log: list[dict[str, Any]], scenario: dict[str, Any]) -> dict[str, Any]:
    evidence_classes = {"status", "project_read", "experiment_read", "sql", "trace_view", "dataset_read", "function_read"}
    evidence_indexes = [index for index, row in enumerate(command_log) if row.get("command_class") in evidence_classes]
    mutating_indexes = [index for index, row in enumerate(command_log) if row.get("mutating")]
    evidence_before_change = bool(evidence_indexes) and (not mutating_indexes or min(evidence_indexes) < min(mutating_indexes))

    smoke_indexes = [index for index, row in enumerate(command_log) if row.get("command_class") == "eval_smoke"]
    full_indexes = [index for index, row in enumerate(command_log) if row.get("command_class") == "eval_full"]
    smoke_before_full = not full_indexes or (bool(smoke_indexes) and min(smoke_indexes) < min(full_indexes))
    dataset_eval_required = scenario["expected"]["route"] == "dataset"
    dataset_eval_ok = not dataset_eval_required or (bool(smoke_indexes) and bool(full_indexes) and smoke_before_full)

    passed = bool(command_log) and evidence_before_change and smoke_before_full and dataset_eval_ok
    return criterion(
        "process_discipline",
        passed,
        "evidence was gathered before changes and eval order was safe" if passed else "process discipline checks failed",
        {
            "command_count": len(command_log),
            "evidence_before_change": evidence_before_change,
            "smoke_before_full": smoke_before_full,
            "dataset_eval_required": dataset_eval_required,
            "dataset_eval_ok": dataset_eval_ok,
        },
    )


def check_side_effects(command_log: list[dict[str, Any]], scenario: dict[str, Any]) -> dict[str, Any]:
    allowed_mutations = set(scenario["expected"].get("allowed_mutations", []))
    forbidden_mutations = [
        row.get("command_class")
        for row in command_log
        if row.get("mutating") and row.get("command_class") not in allowed_mutations
    ]
    changed_files = []
    for path, expected in UNCHANGED_FILES.items():
        actual = path.read_text(encoding="utf-8") if path.exists() else None
        if actual != expected:
            changed_files.append(str(path))
    passed = not forbidden_mutations and not changed_files
    return criterion(
        "side_effect_safety",
        passed,
        "no forbidden Braintrust writes or local code edits detected" if passed else "forbidden side effects detected",
        {
            "allowed_mutations": sorted(allowed_mutations),
            "forbidden_mutations": forbidden_mutations,
            "changed_files": changed_files,
        },
    )


def main() -> int:
    VERIFIER_DIR.mkdir(parents=True, exist_ok=True)
    scenario = read_json(SCENARIO_PATH)
    summary_path = find_file(ARTIFACTS_DIR / "bt-flywheel-summary.json", Path("/app/bt-flywheel-summary.json"))
    narrative_path = find_file(ARTIFACTS_DIR / "bt-flywheel-narrative.md", Path("/app/bt-flywheel-narrative.md"))
    command_log_path = find_file(ARTIFACTS_DIR / "bt-command-log.jsonl")
    command_log = read_jsonl(command_log_path) if command_log_path else []
    summary = read_json(summary_path) if summary_path else None

    criteria = {
        "artifact_presence": check_artifact_presence(summary_path, narrative_path, command_log_path),
        "schema_validity": check_schema(summary),
    }
    summary_obj = summary if isinstance(summary, dict) else {}
    criteria["route_correctness"] = check_route(summary_obj, scenario, command_log)
    criteria["process_discipline"] = check_process(command_log, scenario)
    criteria["side_effect_safety"] = check_side_effects(command_log, scenario)

    reward = {
        key: value["score"]
        for key, value in criteria.items()
    }
    reward["overall"] = round(sum(reward.values()) / len(criteria), 6)
    details = {
        "scenario": scenario["scenario"],
        "summary_path": str(summary_path) if summary_path else None,
        "narrative_path": str(narrative_path) if narrative_path else None,
        "command_log_path": str(command_log_path) if command_log_path else None,
        "criteria": criteria,
        "reward": reward,
    }
    (VERIFIER_DIR / "reward.json").write_text(json.dumps(reward, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (VERIFIER_DIR / "reward-details.json").write_text(json.dumps(details, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if reward["overall"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
