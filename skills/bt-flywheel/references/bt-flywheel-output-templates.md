# Flywheel Output Templates

## Contents

- `bt-flywheel-summary.json`
- Handoff field guidance
- `bt-flywheel-narrative.md`

## bt-flywheel-summary.json

Written when the flywheel exits. In autonomous mode, write it to the working directory root. In interactive mode, present the same fields in the final response and write the file when useful.

Validate this file against `<bt-flywheel-skill-path>/schemas/bt-flywheel-summary.schema.json` when the schema is available.

The summary is a portable handoff contract. It describes what happened, how confident the flywheel is, where the evidence lives, what artifacts were produced, and what adapter-neutral next steps a caller may route into local UI, CI, GitHub, chat, issue tracking, release gates, or an embedded app.

```json
{
  "contract_version": "bt-flywheel-handoff/v1",
  "run_id": "bt-flywheel:<project-name>:<iso8601-or-run-id>",
  "timestamp": "<ISO8601>",
  "mode": "<interactive | autonomous>",
  "goal": "<goal or 'general health check'>",
  "phases_run": ["orient", "discover", "diagnose", "improve", "verify_decide"],
  "outcome": "<healthy | improved | needs_work | blocked | no_convergence>",
  "severity": "<info | warning | critical>",
  "blocking": false,
  "confidence": "<low | medium | high>",
  "summary": "<one-paragraph outcome summary>",
  "findings": ["<finding 1 with evidence>", "<finding 2 with evidence>"],
  "changes": {
    "agent": ["<description>"],
    "measurement": ["<scorer/facet/classifier description>"],
    "datasets": ["<description>"],
    "instrumentation": ["<description>"]
  },
  "verification": {
    "status": "<not_run | smoke_passed | full_passed | failed | inconclusive>",
    "baseline_experiment_id": "<experiment-id or null>",
    "baseline_experiment_url": "https://www.braintrust.dev/app/<org>/p/<project>/experiments/<baseline-id>",
    "new_experiment_id": "<experiment-id or null>",
    "new_experiment_url": "https://www.braintrust.dev/app/<org>/p/<project>/experiments/<experiment-id>",
    "metric_delta": { "<SCORE_COL>": 0.05 },
    "regression_count": 0,
    "notes": ["<verification caveat or detail>"]
  },
  "regressions": [
    {
      "trace_id": "<trace-id>",
      "score": 0.0,
      "url": "https://www.braintrust.dev/app/<org>/p/<project>/r/<trace-id>",
      "label": "<short regression description>"
    }
  ],
  "links": [
    {
      "type": "experiment",
      "role": "candidate",
      "label": "New experiment",
      "id": "<experiment-id>",
      "url": "https://www.braintrust.dev/app/<org>/p/<project>/experiments/<experiment-id>",
      "metadata": { "score_delta": 0.05 }
    },
    {
      "type": "trace",
      "role": "evidence",
      "label": "Representative failure trace",
      "id": "<trace-id>",
      "url": "https://www.braintrust.dev/app/<org>/p/<project>/r/<trace-id>",
      "metadata": { "score": 0.0 }
    },
    {
      "type": "query",
      "role": "evidence",
      "label": "Production search query",
      "metadata": {
        "sql": "SELECT ...",
        "row_count": 38
      }
    }
  ],
  "artifacts": [
    {
      "type": "summary_json",
      "path": "bt-flywheel-summary.json",
      "label": "Machine-readable flywheel handoff"
    },
    {
      "type": "narrative_markdown",
      "path": "bt-flywheel-narrative.md",
      "label": "Human-readable flywheel narrative"
    }
  ],
  "next_steps": [
    {
      "intent": "<no_action | review_change | investigate | label_data | rerun | notify | block_release | rollback>",
      "priority": "<low | normal | high>",
      "blocking": false,
      "requires_human_review": true,
      "title": "<short human-readable title>",
      "body_markdown": "<adapter-neutral next-step body with evidence, findings, changes, and caveats>",
      "suggested_destination": "<local_summary | code_review | issue_tracker | chat | release_gate | scheduler | app_ui | external_system | none>",
      "link_refs": ["<optional link ids or labels>"],
      "artifact_refs": ["<optional artifact paths>"],
      "idempotency_key": "bt-flywheel:<project-name>:<run-date>:<intent>:<stable-fingerprint>",
      "metadata": {}
    }
  ]
}
```

## Handoff Field Guidance

- `outcome`: route the run without inspecting prose. Use `healthy` for no work needed, `improved` for verified improvement, `needs_work` for actionable follow-up, `blocked` for missing labels/data/auth or unsafe automation, and `no_convergence` after bounded iterations fail to improve.
- `severity` and `blocking`: express release/operational risk without naming a destination. A caller can map them to CI status, deployment gate, notification, or UI state.
- `confidence`: lower it for low traffic, flaky evals, inconclusive trace data, or unresolved human-label questions.
- `verification`: distinguish "changed" from "proved." `not_run` is valid for healthy exits or blocked runs.
- `links`: store Braintrust experiments, traces, query evidence, datasets, functions, docs, and external references as structured objects so apps and CI can render them differently.
- `artifacts`: store local files produced by the flywheel. Embedded apps may upload them; local developers and CI can read paths directly.
- `next_steps`: describe intent, priority, and review needs. `suggested_destination` is advisory only; the caller owns mapping to GitHub, Slack, Jira, Linear, app UI, webhooks, or no side effect.

Use `intent: "no_action"` with `suggested_destination: "none"` when no follow-up is needed. Use `intent: "block_release"` or `rollback` only when evidence shows a blocking regression or severe degradation. Do not include secrets or raw webhook URLs; put those in caller configuration, not the handoff.

## bt-flywheel-narrative.md

Written after `bt-flywheel-summary.json`. It is a human-readable companion for local review, CI job summaries, PR descriptions, app UI, or tickets. Write while you still have full context; do not summarize only from the JSON.

```markdown
## Flywheel Run

### Outcome
<outcome, severity, confidence, blocking status>

### Summary
<one concise paragraph>

### Findings
- <finding with query result, trace link, or score value>

### Changes
- Agent: <none or changes>
- Measurement: <none or changes>
- Datasets: <none or changes>
- Instrumentation: <none or changes>

### Verification
| | Baseline | New |
|---|---|---|
| Experiment | [<baseline-id>](<baseline_url>) | [<new-id>](<new_url>) |
| <SCORE_COL> avg | X | Y |
| Regressions | - | [<trace-id>](<url>), ... |

### Links And Artifacts
- <important links and local artifacts>

### Next Steps
- <intent, priority, suggested destination, review requirement, and idempotency key>
```

If no changes were made, explain whether production is healthy or why the run is blocked/needs work. If follow-up is needed, include the exact evidence and labels/decisions the caller should collect.
