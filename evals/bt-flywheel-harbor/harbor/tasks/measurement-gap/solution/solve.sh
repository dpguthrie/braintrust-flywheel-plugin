#!/usr/bin/env bash
set -euo pipefail

mkdir -p /logs/artifacts

bt status --json
bt projects list --json
bt experiments list --json -p "Support Agent"
bt sql "SELECT * FROM project_logs('proj_support_agent') WHERE is_root = true AND created >= NOW() - INTERVAL 7 day LIMIT 1"
bt sql "SELECT id, input, output, scores.\"Task Success\" FROM project_logs('proj_support_agent') WHERE search('cannot help billing') AND created >= NOW() - INTERVAL 7 day"
bt view trace --object-ref project_logs:proj_support_agent --trace-id trace_measurement_gap_001 --json
bt functions list --json -p "Support Agent"
bt functions view task-success -p "Support Agent" --json

python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

timestamp = datetime.now(timezone.utc).isoformat()
summary = {
    "contract_version": "bt-flywheel-handoff/v1",
    "run_id": "bt-flywheel:Support Agent:measurement-gap",
    "timestamp": timestamp,
    "mode": "autonomous",
    "goal": "general health check",
    "phases_run": ["orient", "discover", "diagnose"],
    "outcome": "needs_work",
    "severity": "warning",
    "blocking": False,
    "confidence": "high",
    "summary": "Production traces show repeated billing-policy refusals that existing scores mark as passing, so the next flywheel route is measurement/scorer work before any agent change.",
    "findings": [
        "Trace search found 19 billing-policy refusals in 7 days while Task Success remained 1.0 for representative trace trace_measurement_gap_001.",
        "The existing task-success scorer does not separate bad refusal or unsupported handoff behavior from correct answers.",
        "Dataset coverage for billing policy examples exists, so this is not primarily a dataset gap."
    ],
    "changes": {
        "agent": [],
        "measurement": ["Propose a billing-policy refusal scorer or facet calibrated on positive, negative, and borderline traces before optimizing agent behavior."],
        "datasets": [],
        "instrumentation": []
    },
    "verification": {
        "status": "not_run",
        "baseline_experiment_id": "exp_baseline_measurement_gap",
        "baseline_experiment_url": "https://www.braintrust.dev/app/Braintrust%20Demos/p/Support%20Agent/experiments/exp_baseline_measurement_gap",
        "new_experiment_id": None,
        "new_experiment_url": None,
        "metric_delta": {},
        "regression_count": 0,
        "notes": ["Verification is blocked on adding calibrated measurement for the observed failure mode."]
    },
    "regressions": [],
    "links": [
        {
            "type": "trace",
            "role": "evidence",
            "label": "Billing refusal trace",
            "id": "trace_measurement_gap_001",
            "url": "https://www.braintrust.dev/app/Braintrust%20Demos/p/Support%20Agent/r/trace_measurement_gap_001",
            "metadata": {"Task Success": 1.0, "manual_label": "bad_refusal"}
        },
        {
            "type": "function",
            "role": "current_measurement",
            "label": "Existing task-success scorer",
            "id": "task-success",
            "url": None,
            "metadata": {"gap": "does not penalize billing refusal"}
        }
    ],
    "artifacts": [
        {"type": "summary_json", "path": "/logs/artifacts/bt-flywheel-summary.json", "label": "Machine-readable flywheel handoff"},
        {"type": "narrative_markdown", "path": "/logs/artifacts/bt-flywheel-narrative.md", "label": "Human-readable flywheel narrative"},
        {"type": "log", "path": "/logs/artifacts/bt-command-log.jsonl", "label": "bt command log"}
    ],
    "next_steps": [
        {
            "intent": "review_change",
            "priority": "normal",
            "blocking": False,
            "requires_human_review": True,
            "title": "Add billing refusal measurement",
            "body_markdown": "Create a scorer or facet that fails unsupported billing-policy refusals. Calibrate it on trace_measurement_gap_001 and related passing/borderline traces before changing the agent.",
            "suggested_destination": "code_review",
            "link_refs": ["Billing refusal trace", "Existing task-success scorer"],
            "artifact_refs": ["/logs/artifacts/bt-flywheel-summary.json"],
            "idempotency_key": "bt-flywheel:Support Agent:measurement-gap:review_change",
            "metadata": {"route": "measurement"}
        }
    ]
}
narrative = """## Flywheel Run

### Outcome
needs_work, warning severity, high confidence, not blocking

### Summary
Production traces show repeated billing-policy refusals that existing scores mark as passing, so the next route is measurement work before agent changes.

### Findings
- trace_measurement_gap_001 has Task Success 1.0 despite an unsupported billing refusal.
- The current task-success scorer does not capture this failure dimension.
- Billing examples are represented in the dataset, so the first gap is measurement.

### Changes
- Agent: none
- Measurement: propose a calibrated billing refusal scorer or facet
- Datasets: none
- Instrumentation: none

### Verification
Not run; verification needs the measurement gap closed first.

### Next Steps
- review_change: add billing refusal measurement before changing agent behavior.
"""
for path in [Path("/logs/artifacts/bt-flywheel-summary.json"), Path("/app/bt-flywheel-summary.json")]:
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
for path in [Path("/logs/artifacts/bt-flywheel-narrative.md"), Path("/app/bt-flywheel-narrative.md")]:
    path.write_text(narrative, encoding="utf-8")
PY
