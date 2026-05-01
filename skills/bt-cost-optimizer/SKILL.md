---
name: bt-cost-optimizer
description: Use when analyzing and reducing Braintrust usage costs with the bt CLI, including logs/GB ingest, scorers, Topics, Gateway LLM spend, datasets, experiments, attachments, or large trace payloads.
---

# Braintrust Cost Optimizer

Find what is driving Braintrust usage cost, separate measured evidence from heuristics, and recommend safe changes to logging, scoring, Topics, Gateway, datasets, and experiments.

## When to Use

- A Braintrust customer asks why usage cost, GB ingest, scorer volume, or LLM spend is high
- A project is approaching processed-data, scorer, Topics, storage, or provider-spend limits
- Logs, traces, scorer spans, datasets, experiments, metadata, prompts, tool outputs, or attachments may be too large
- The user wants to know whether sampling, `JSONAttachment`, scorer filtering, Topics, Gateway caching, provider routing, retention, or code changes would reduce cost

## Reference Files

Load these as needed:

- `references/braintrust-cost-model.md` - pricing/resource accounting facts and evidence limits
- `references/bt-query-patterns.md` - `bt` commands and SQL patterns for collecting samples
- `references/optimization-patterns.md` - concrete log, scorer, Topics, Gateway, and experiment recommendations
- `references/report-template.md` - expected report structure
- `scripts/analyze-cost-drivers.py` - local analyzer for exported Braintrust rows

## Core Principles

- Start with `bt` evidence. Run bounded queries and inspect a row sample before recommending changes.
- Distinguish measured findings from recommendations that require UI, billing, Gateway, or code config review.
- For logs, processed data is cumulative monthly ingest, not retained storage. Deleting old traces does not reduce the current month's processed-data usage.
- The strongest log-cost lever is reducing bytes sent to Braintrust: omit, sample, truncate, summarize, deduplicate, or log IDs/references instead of full payloads.
- Use `JSONAttachment` for large JSON that must remain available for debugging but does not need search, filtering, scorer logic, or dashboard grouping.
- Do not claim `JSONAttachment` is a guaranteed billable-byte reduction. Use it to reduce indexed trace bodies and improve span-size/UI behavior; pair it with actual byte reduction when the goal is cost.
- For scorers, reduce the number of scored spans and LLM judge calls before optimizing prompt tokens. Prefer code-based checks for deterministic criteria.
- For broad categorization, prefer Topics before high-volume LLM-as-judge scorers. Use Topics to route targeted scorers.
- Keep compact, high-value metadata inline: IDs, model, route, customer tier, prompt version, topic, document IDs, counts, hashes, and fields used by filters, scorers, evals, dashboards, or incident workflows.

## Workflow

### 1. Orient

Resolve the active Braintrust context before querying.

```bash
bt status --json
cat .bt/config.json 2>/dev/null
bt projects list --json
```

Use `.bt/config.json` first when present. If no project is configured, ask the user for the project name, then resolve the project ID with `bt projects list --json`.

Capture:

- org name
- project name
- project ID
- time window to inspect, defaulting to 7 days
- primary concern: logs/GB ingest, scorers, Topics, Gateway/provider spend, datasets/experiments, or all cost surfaces
- current plan/pricing assumptions if the user provides them; otherwise avoid hard-dollar claims

### 2. Collect Evidence

Load `references/bt-query-patterns.md`. Pull bounded evidence before making recommendations.

Minimum evidence set:

```bash
bt sql --json "SELECT * FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day LIMIT 1000" > /tmp/bt-cost-project-spans.json
bt sql --json "SELECT COUNT(*) AS spans, COUNT(DISTINCT root_span_id) AS traces FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day" > /tmp/bt-cost-volume.json
bt scorers list --json > /tmp/bt-cost-scorers.json
bt topics status --json > /tmp/bt-cost-topics-status.json
bt topics config --json > /tmp/bt-cost-topics-config.json
```

If the project is very high volume, reduce the sample limit and use targeted queries for root spans, scorer spans, LLM spans, or known trace IDs.

When experiments or datasets are suspected, sample those too with `experiment('<EXPERIMENT_ID>')` or `dataset('<DATASET_ID>')` if the IDs are known.

### 3. Analyze Row-Level Drivers

Run the analyzer on one or more exported files.

```bash
python3 skills/bt-cost-optimizer/scripts/analyze-cost-drivers.py \
  /tmp/bt-cost-project-spans.json \
  --sample-days 7 \
  --output bt-cost-optimization-report.md \
  --json-output bt-cost-optimization-summary.json
```

If no sample window is known, omit `--sample-days`; the report will still rank fields, rows, traces, scorer spans, and token totals but will not extrapolate monthly usage.

### 4. Inspect Code and Config

Find where cost drivers are produced. Prefer targeted code search over broad assumptions.

```bash
rg -n "init_logger|initLogger|logger\\.log|span\\.log|start_span|startSpan|braintrust|JSONAttachment|Attachment\\(" .
rg -n "messages|transcript|documents|chunks|retrieved|context|prompt|completion|tool_calls|response|request|metadata|embedding" .
rg -n "sampling_rate|apply_to_root_span|apply_to_span_names|btql_filter|skip_logging|LLM-as-a-Judge|autoevals|scorer" .
rg -n "x-bt-use-cache|x-bt-cache-ttl|x-bt-endpoint-name|x-bt-compress-audio|BraintrustGateway|braintrust_proxy|base_url" .
```

Look for:

- Full conversations logged repeatedly on parent and child spans
- Retrieved document arrays, embeddings, HTML, PDFs, raw API responses, tool outputs, or base64 media logged inline
- Metadata objects containing large nested blobs instead of small filterable fields
- Duplicate logging of both raw provider requests and normalized traces
- Scorers applied to every span instead of root or named spans
- LLM-as-judge scorers used for deterministic checks
- Scorer automations without `btql_filter`, with high `sampling_rate`, or with scorer logging enabled when scorer traces are not needed
- Missing Gateway cache headers on deterministic LLM calls
- Experiments or datasets storing full production artifacts when only inputs, expected outputs, summaries, or failure examples are needed

### 5. Recommend Changes

Load `references/optimization-patterns.md` and write `bt-cost-optimization-report.md`. Every recommendation must include:

- evidence source: `bt sql`, `bt view`, `bt topics`, `bt scorers`, code search, billing/UI config, or assumption
- observed path, field, scorer, topic config, or code location
- estimated bytes, rows, scorer calls, token totals, or qualitative cost driver
- why the data/action is or is not needed inline
- suggested change
- expected tradeoff
- confidence level

Use these decision rules:

- If data is needed for search/filter/scorers/dashboards, keep a compact form inline.
- If data is needed only for debugging or audit, move it to `JSONAttachment` or an external reference and keep summary metadata inline.
- If data is rarely needed, sample it or log only on errors, low scores, incidents, or critical workflows.
- If data is duplicated across spans, keep it on one span and reference it elsewhere by ID/hash.
- If data is not needed after aggregation, log counts, hashes, and summaries instead of the raw payload.
- If a scorer is deterministic, replace LLM-as-judge with code or Autoevals where possible.
- If a scorer answers "what type of request is this?" rather than "how good is the answer?", consider Topics first.
- If deterministic LLM calls are repeated, recommend Gateway caching and measure model/token volume from logs where available.

### 6. Act

Do not edit customer instrumentation by default. The default output is an evidence-backed report plus optional patch recommendations.

Only make code changes when the user asks. When changing code:

- Keep behavior-preserving instrumentation changes small
- Add or update tests if the logging/scoring shape is covered
- Preserve fields used by evals, scorers, filters, dashboards, and incident workflows
- Show before/after logging or scoring shapes in the report

## Required Output

Write:

- `bt-cost-optimization-report.md` - human-readable findings and recommendations
- `bt-cost-optimization-summary.json` - machine-readable summary when using the analyzer or automation

If evidence is insufficient, say exactly what is missing and provide the next `bt` command or config location to collect it.
