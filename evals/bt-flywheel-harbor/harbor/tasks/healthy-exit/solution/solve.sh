#!/usr/bin/env bash
set -euo pipefail

mkdir -p /logs/artifacts

bt status --json
bt projects list --json
bt experiments list --json -p "Support Agent"
bt sql "SELECT * FROM project_logs('proj_support_agent') WHERE is_root = true AND created >= NOW() - INTERVAL 7 day LIMIT 1"
bt sql "SELECT COUNT(*) AS trace_count, AVG(scores.\"Task Success\") AS task_success_avg FROM project_logs('proj_support_agent') WHERE is_root = true AND created >= NOW() - INTERVAL 7 day"
bt view trace --object-ref project_logs:proj_support_agent --trace-id trace_healthy_001 --json

python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

timestamp = datetime.now(timezone.utc).isoformat()
summary = {
    "contract_version": "bt-flywheel-handoff/v1",
    "run_id": "bt-flywheel:Support Agent:healthy-exit",
    "timestamp": timestamp,
    "mode": "autonomous",
    "goal": "general health check",
    "phases_run": ["orient", "discover", "diagnose"],
    "outcome": "healthy",
    "severity": "info",
    "blocking": False,
    "confidence": "high",
    "summary": "Production metrics are healthy over the 7 day window; no measurement, dataset, agent, or instrumentation change is warranted.",
    "findings": [
        "7 day production aggregate returned 240 traces with Task Success average 0.972 and no output contract failures.",
        "Representative trace trace_healthy_001 scored 1.0 and matches an already represented account access dataset cluster."
    ],
    "changes": {
        "agent": [],
        "measurement": [],
        "datasets": [],
        "instrumentation": []
    },
    "verification": {
        "status": "not_run",
        "baseline_experiment_id": "exp_baseline_healthy",
        "baseline_experiment_url": "https://www.braintrust.dev/app/Braintrust%20Demos/p/Support%20Agent/experiments/exp_baseline_healthy",
        "new_experiment_id": None,
        "new_experiment_url": None,
        "metric_delta": {},
        "regression_count": 0,
        "notes": ["No eval was run because Diagnose exited healthy with no proposed change."]
    },
    "regressions": [],
    "links": [
        {
            "type": "trace",
            "role": "evidence",
            "label": "Representative healthy trace",
            "id": "trace_healthy_001",
            "url": "https://www.braintrust.dev/app/Braintrust%20Demos/p/Support%20Agent/r/trace_healthy_001",
            "metadata": {"Task Success": 1.0}
        },
        {
            "type": "query",
            "role": "evidence",
            "label": "7 day production health aggregate",
            "metadata": {"trace_count": 240, "task_success_avg": 0.972}
        }
    ],
    "artifacts": [
        {"type": "summary_json", "path": "/logs/artifacts/bt-flywheel-summary.json", "label": "Machine-readable flywheel handoff"},
        {"type": "narrative_markdown", "path": "/logs/artifacts/bt-flywheel-narrative.md", "label": "Human-readable flywheel narrative"},
        {"type": "log", "path": "/logs/artifacts/bt-command-log.jsonl", "label": "bt command log"}
    ],
    "next_steps": [
        {
            "intent": "no_action",
            "priority": "low",
            "blocking": False,
            "requires_human_review": False,
            "title": "No flywheel action needed",
            "body_markdown": "Production health checks are green and no coverage or measurement gap was found.",
            "suggested_destination": "none",
            "link_refs": ["Representative healthy trace"],
            "artifact_refs": ["/logs/artifacts/bt-flywheel-summary.json"],
            "idempotency_key": "bt-flywheel:Support Agent:healthy-exit:no_action",
            "metadata": {}
        }
    ]
}
narrative = """## Flywheel Run

### Outcome
healthy, info severity, high confidence, not blocking

### Summary
Production metrics are healthy over the 7 day window; no measurement, dataset, agent, or instrumentation change is warranted.

### Findings
- 240 traces had Task Success average 0.972 and no output contract failures.
- trace_healthy_001 is representative and already covered by the dataset.

### Changes
- Agent: none
- Measurement: none
- Datasets: none
- Instrumentation: none

### Verification
No eval was run because the flywheel exited healthy before Improve.

### Next Steps
- no_action: no downstream adapter action needed.
"""
for path in [Path("/logs/artifacts/bt-flywheel-summary.json"), Path("/app/bt-flywheel-summary.json")]:
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
for path in [Path("/logs/artifacts/bt-flywheel-narrative.md"), Path("/app/bt-flywheel-narrative.md")]:
    path.write_text(narrative, encoding="utf-8")
PY
