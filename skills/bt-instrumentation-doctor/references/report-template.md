# Report Template

Write `bt-tracing-plan.md` for humans and `bt-tracing-summary.json` for downstream automation. Both should be derivable from the same evidence so they don't drift.

## `bt-tracing-plan.md`

```markdown
# Braintrust Instrumentation Plan

## Context

- Org:
- Project:
- Project ID:
- Window:
- Codebase path:
- Detected SDK(s):
- Samples analyzed:
- Evidence sources: `bt sql`, `bt view`, `bt topics`, REST `/v1/project_score`, local code search
- Primary concern:

## Executive Summary

- Headline findings (3–5 bullets):
- Top 3 changes to ship first:
- Items requiring customer judgment before action:
- Items blocked on access (e.g., no API key for automations):

## Evidence Coverage

| Dimension | Evidence collected | Coverage | Gaps |
|---|---|---|---|
| Trace structure |  |  |  |
| Scorer setup |  |  |  |
| Thread / sessions |  |  |  |
| Data shape |  |  |  |
| Cost efficiency |  |  |  |
| LLM completeness |  |  |  |

## Findings

For each finding, use the following template (one heading per finding, ordered by priority):

### F-### — <one-line title>

- **Dimension:** structure | scorer | thread | shape | cost | llm-completeness | meta
- **Severity:** high | medium | low
- **Evidence:**
  - Trace ids: `<root_span_id>`, `<root_span_id>`
  - SQL: `<one-line excerpt of the query that surfaced it>`
  - Code: `path/to/file.py:42`
- **What's wrong:**
- **Suggested change:**
- **Expected effect:**
- **Tradeoff:**
- **Confidence:** high | medium | low
- **Effort:** small | medium | large

## Recommended Plan

Numbered, sequential. Group related findings into a single change when possible.

1. **<Change title>** — addresses F-001, F-007. Estimated effort: small. Owner hint: <subsystem/file>.
2. **<Change title>** — addresses F-002. Estimated effort: medium.
3. …

## Risks and Non-Goals

- Fields that must stay inline (used by filters/dashboards):
- Scorers that should remain LLM-as-judge:
- Areas the doctor explicitly did not review:
- Unknowns / follow-ups:

## Follow-Up Commands

- Re-run with broader window: `bt sql ...`
- For deeper cost accounting: see [`bt-cost-optimizer`](../bt-cost-optimizer/SKILL.md)
- For end-to-end improvement loop: see [`bt-flywheel`](../bt-flywheel/SKILL.md)
```

## `bt-tracing-summary.json`

Machine-readable mirror. Stable finding ids let a re-run diff against the previous run.

```json
{
  "schema_version": 1,
  "skill": "bt-instrumentation-doctor",
  "org": "",
  "project": "",
  "project_id": "",
  "window_days": 7,
  "codebase_path": "",
  "detected_sdks": [],
  "samples": {
    "spans_analyzed": 0,
    "traces_inspected": 0,
    "automations_fetched": false
  },
  "headline_findings": [],
  "top_changes": [],
  "blocked_on_access": [],
  "findings": [
    {
      "id": "F-001",
      "dimension": "structure",
      "title": "",
      "severity": "high",
      "confidence": "high",
      "effort": "small",
      "evidence": {
        "trace_ids": [],
        "sql": "",
        "code_locations": []
      },
      "whats_wrong": "",
      "suggested_change": "",
      "expected_effect": "",
      "tradeoff": ""
    }
  ],
  "plan": [
    {
      "step": 1,
      "title": "",
      "addresses_finding_ids": ["F-001"],
      "effort": "small",
      "owner_hint": ""
    }
  ],
  "risks_and_non_goals": [],
  "follow_ups": []
}
```

## Conventions

- **Finding ids** are zero-padded sequential within a run: `F-001`, `F-002`, … . When re-running, prefer reusing the prior id for the same defect when the evidence still points at it; allocate new ids for newly surfaced issues.
- **Confidence rubric:**
  - `high` — evidence directly observed in spans/code; recommendation is unambiguous.
  - `medium` — evidence is suggestive but business context could justify the current shape.
  - `low` — heuristic only; needs human judgment or further evidence.
- **Severity rubric:**
  - `high` — blocks scoring, Thread view, evals, or correctness signal.
  - `medium` — degrades search, slicing, cost, or dashboards.
  - `low` — cosmetic; safe to defer.
- **Effort rubric:**
  - `small` — single instrumentation site, < 1 day.
  - `medium` — multiple sites or a wrapper change.
  - `large` — architectural change (session-root pattern, tool runtime refactor).
- When evidence is insufficient for a confident recommendation, still record the finding with `confidence: low` and a specific follow-up command or UI location in `follow_ups`.
