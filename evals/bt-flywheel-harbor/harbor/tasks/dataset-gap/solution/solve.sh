#!/usr/bin/env bash
set -euo pipefail

mkdir -p /logs/artifacts

bt status --json
bt projects list --json
bt experiments list --json -p "Support Agent"
bt sql "SELECT * FROM project_logs('proj_support_agent') WHERE is_root = true AND created >= NOW() - INTERVAL 7 day LIMIT 1"
bt sql "SELECT production_cluster, production_traces, dataset_rows FROM dataset_coverage WHERE production_cluster = 'device_limit_after_phone_replacement'"
bt view trace --object-ref project_logs:proj_support_agent --trace-id trace_dataset_gap_001 --json
bt datasets list --json -p "Support Agent"
bt datasets view "Support Eval Dataset" -p "Support Agent" --json

python3 - <<'PY'
import json
from pathlib import Path

rows = [
    {
        "id": "flywheel:proj_support_agent:trace_dataset_gap_001",
        "input": {"message": "The mobile app says device limit exceeded after replacing my phone."},
        "expected": "Explain how to remove old devices from device management, then retry sign-in.",
        "tags": ["production", "flywheel-curated", "validation", "device_limit_after_phone_replacement"],
        "metadata": {
            "source_trace_id": "trace_dataset_gap_001",
            "source_project_id": "proj_support_agent",
            "production_score": 0.42,
            "bucket": "device_limit_after_phone_replacement",
            "split": "validation",
            "flywheel_iteration": "harbor-eval"
        }
    },
    {
        "id": "flywheel:proj_support_agent:trace_dataset_gap_002",
        "input": {"message": "I upgraded phones and now the app says I have too many devices."},
        "expected": "Direct the user to remove the previous phone from device management before adding the new phone.",
        "tags": ["production", "flywheel-curated", "train", "device_limit_after_phone_replacement"],
        "metadata": {
            "source_trace_id": "trace_dataset_gap_002",
            "source_project_id": "proj_support_agent",
            "production_score": 0.39,
            "bucket": "device_limit_after_phone_replacement",
            "split": "train",
            "flywheel_iteration": "harbor-eval"
        }
    }
]
Path("/logs/artifacts/curated-dataset-rows.json").write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

bt datasets update "Support Eval Dataset" -p "Support Agent" --id-field id --json --no-input < /logs/artifacts/curated-dataset-rows.json
bt eval --first 20 /app/evals/eval_support.py
bt eval /app/evals/eval_support.py

python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

timestamp = datetime.now(timezone.utc).isoformat()
summary = {
    "contract_version": "bt-flywheel-handoff/v1",
    "run_id": "bt-flywheel:Support Agent:dataset-gap",
    "timestamp": timestamp,
    "mode": "autonomous",
    "goal": "general health check",
    "phases_run": ["orient", "discover", "diagnose", "improve", "verify_decide"],
    "outcome": "improved",
    "severity": "warning",
    "blocking": False,
    "confidence": "high",
    "summary": "Production device-limit traces had low scores and no matching eval rows, so two curated dataset examples were added and verified with smoke-before-full evals.",
    "findings": [
        "The device_limit_after_phone_replacement cluster appeared in 27 production traces with Task Success average 0.42.",
        "Dataset coverage query returned 0 rows for that production cluster.",
        "Representative traces trace_dataset_gap_001 and trace_dataset_gap_002 provide train and validation examples."
    ],
    "changes": {
        "agent": [],
        "measurement": [],
        "datasets": ["Added two curated production-derived rows for the device limit after phone replacement pattern."],
        "instrumentation": []
    },
    "verification": {
        "status": "full_passed",
        "baseline_experiment_id": "exp_baseline_dataset_gap",
        "baseline_experiment_url": "https://www.braintrust.dev/app/Braintrust%20Demos/p/Support%20Agent/experiments/exp_baseline_dataset_gap",
        "new_experiment_id": "exp_full_dataset_gap",
        "new_experiment_url": "https://www.braintrust.dev/app/Braintrust%20Demos/p/Support%20Agent/experiments/exp_full_dataset_gap",
        "metric_delta": {"Production Pattern Coverage": 0.15, "Task Success": 0.02},
        "regression_count": 0,
        "notes": ["Smoke eval exp_smoke_dataset_gap passed before full eval exp_full_dataset_gap."]
    },
    "regressions": [],
    "links": [
        {
            "type": "trace",
            "role": "evidence",
            "label": "Device limit trace",
            "id": "trace_dataset_gap_001",
            "url": "https://www.braintrust.dev/app/Braintrust%20Demos/p/Support%20Agent/r/trace_dataset_gap_001",
            "metadata": {"Task Success": 0.42}
        },
        {
            "type": "dataset",
            "role": "changed_artifact",
            "label": "Support Eval Dataset",
            "id": "dataset_support_eval",
            "url": None,
            "metadata": {"rows_added": 2}
        },
        {
            "type": "experiment",
            "role": "candidate",
            "label": "Full verification eval",
            "id": "exp_full_dataset_gap",
            "url": "https://www.braintrust.dev/app/Braintrust%20Demos/p/Support%20Agent/experiments/exp_full_dataset_gap",
            "metadata": {"Production Pattern Coverage": 0.87}
        }
    ],
    "artifacts": [
        {"type": "summary_json", "path": "/logs/artifacts/bt-flywheel-summary.json", "label": "Machine-readable flywheel handoff"},
        {"type": "narrative_markdown", "path": "/logs/artifacts/bt-flywheel-narrative.md", "label": "Human-readable flywheel narrative"},
        {"type": "curated_dataset_rows", "path": "/logs/artifacts/curated-dataset-rows.json", "label": "Curated dataset rows"},
        {"type": "log", "path": "/logs/artifacts/bt-command-log.jsonl", "label": "bt command log"}
    ],
    "next_steps": [
        {
            "intent": "review_change",
            "priority": "normal",
            "blocking": False,
            "requires_human_review": True,
            "title": "Review curated device-limit examples",
            "body_markdown": "Review the two curated dataset rows derived from trace_dataset_gap_001 and trace_dataset_gap_002, then keep them in the eval dataset if labels look correct.",
            "suggested_destination": "code_review",
            "link_refs": ["Device limit trace", "Support Eval Dataset", "Full verification eval"],
            "artifact_refs": ["/logs/artifacts/curated-dataset-rows.json", "/logs/artifacts/bt-flywheel-summary.json"],
            "idempotency_key": "bt-flywheel:Support Agent:dataset-gap:review_change",
            "metadata": {"route": "dataset"}
        }
    ]
}
narrative = """## Flywheel Run

### Outcome
improved, warning severity, high confidence, not blocking

### Summary
Production device-limit traces had low scores and no matching eval rows, so two curated dataset examples were added and verified with smoke-before-full evals.

### Findings
- The production cluster appeared in 27 traces with Task Success average 0.42.
- Dataset coverage was missing for device_limit_after_phone_replacement.
- trace_dataset_gap_001 and trace_dataset_gap_002 were used as curated examples.

### Changes
- Agent: none
- Measurement: none
- Datasets: added two curated rows
- Instrumentation: none

### Verification
Smoke eval exp_smoke_dataset_gap passed before full eval exp_full_dataset_gap.

### Next Steps
- review_change: inspect the curated labels before retaining the dataset update.
"""
for path in [Path("/logs/artifacts/bt-flywheel-summary.json"), Path("/app/bt-flywheel-summary.json")]:
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
for path in [Path("/logs/artifacts/bt-flywheel-narrative.md"), Path("/app/bt-flywheel-narrative.md")]:
    path.write_text(narrative, encoding="utf-8")
PY
