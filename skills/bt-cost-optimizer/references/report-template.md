# Report Template

Write `bt-cost-optimization-report.md` in this structure.

```markdown
# Braintrust Cost Optimization Report

## Context

- Org:
- Project:
- Project ID:
- Window:
- Samples analyzed:
- Data sources:
- Pricing assumptions:

## Executive Summary

- Primary cost drivers:
- Highest-confidence savings:
- Changes that require customer confirmation:
- Next recommended action:

## Evidence Coverage

| Surface | Evidence collected | Coverage | Gaps |
|---|---|---|---|
| Logs / GB ingest |  |  |  |
| Scorers |  |  |  |
| Topics |  |  |  |
| Gateway / provider spend |  |  |  |
| Experiments / datasets |  |  |  |
| Retention / storage |  |  |  |

## Log / Ingest Findings

- Estimated sample bytes:
- Estimated monthly processed data:
- Average row size:
- P95 row size:
- Largest trace/root-span drivers:

| Rank | Path | Sample bytes | Share | Max row bytes | Rows | Notes |
|---|---:|---:|---:|---:|---:|---|

## Largest Rows and Traces

| Rank | Row or trace ID | Root span ID | Estimated bytes | Spans | Created | Notes |
|---|---|---|---:|---:|---|---|

## Scorer Findings

| Scorer/model | Calls | Prompt tokens | Completion tokens | Evidence | Notes |
|---|---:|---:|---:|---|---|

## Topics Findings

- Topics status:
- Topic config:
- Recent trace count:
- Opportunities to replace or route scorers:

## Gateway / Provider Findings

- LLM token drivers:
- Cache opportunities:
- Provider routing opportunities:
- Audio compression opportunities:
- Evidence gaps:

## Code Findings

- File/path:
- Logging/scoring/Gateway call:
- Why it drives cost:
- Safer shape:

## Recommendations

| Priority | Surface | Change | Evidence | Expected impact | Tradeoff | Confidence |
|---|---|---|---|---|---|---|

## JSONAttachment Candidates

List large JSON fields that should be moved to `JSONAttachment`, plus the compact inline fields to retain.

## Scorer Changes

List scorers that should change sampling, filters, span scope, `skip_logging`, scorer type, or LLM judge consolidation.

## Risks and Non-Goals

- Fields that must stay inline:
- Scorers that should remain LLM-as-judge:
- Retention/audit constraints:
- Unknowns:
- Follow-up commands:
```

Also write `bt-cost-optimization-summary.json` when possible:

```json
{
  "org": "",
  "project": "",
  "project_id": "",
  "sample_days": 7,
  "surfaces": {
    "logs": {},
    "scorers": {},
    "topics": {},
    "gateway": {},
    "experiments": {},
    "datasets": {}
  },
  "recommendations": []
}
```
