# bt Query Patterns

Use these patterns to collect bounded evidence. Always include a time range, explicit limit, or specific trace/span ID.

## Resolve Context

```bash
bt status --json
bt projects list --json
cat .bt/config.json 2>/dev/null
```

## Production Log Volume

Count spans and traces in a time window:

```bash
bt sql --json "SELECT COUNT(*) AS spans, COUNT(DISTINCT root_span_id) AS traces FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day" > /tmp/bt-cost-volume.json
```

Sample spans for row-size analysis:

```bash
bt sql --json "SELECT * FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day LIMIT 1000" > /tmp/bt-cost-project-spans.json
```

Sample root spans only:

```bash
bt sql --json "SELECT * FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE is_root = true AND created >= NOW() - INTERVAL 7 day LIMIT 500" > /tmp/bt-cost-root-spans.json
```

Inspect recent spans through the view command:

```bash
bt view logs --json --project-id <PROJECT_ID> --list-mode spans --window 7d --limit 200 > /tmp/bt-cost-view-spans.json
```

Fetch a full trace when a large row has a `root_span_id`:

```bash
bt view trace --json --project-id <PROJECT_ID> --trace-id <ROOT_SPAN_ID> --limit 200 > /tmp/bt-cost-trace.json
```

## Span Depth and Duplication Clues

Find the most common span names:

```bash
bt sql --json "SELECT span_attributes.name AS span_name, COUNT(*) AS spans FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day GROUP BY span_name ORDER BY spans DESC LIMIT 50" > /tmp/bt-cost-span-names.json
```

Find traces with many spans:

```bash
bt sql --json "SELECT root_span_id, COUNT(*) AS spans FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day GROUP BY root_span_id ORDER BY spans DESC LIMIT 50" > /tmp/bt-cost-deep-traces.json
```

## Scorer Automations

Fetch the project's active online scorer automation rules to see which scorers are running, at what sampling rate, with what filters, and on what span scope. This is required before making any sampling-rate recommendation — never suggest changing a rate you haven't measured.

```bash
curl -s "https://api.braintrust.dev/v1/project_score?project_id=<PROJECT_ID>&limit=100" \
  -H "Authorization: Bearer ${BRAINTRUST_API_KEY}" \
  > /tmp/bt-cost-automations.json
```

If `BRAINTRUST_API_KEY` is not set (e.g., the user authenticates via OAuth through the browser), note that automation rules must be reviewed in the Braintrust UI under **Project → Logs → Score** and ask the user to share the relevant config.

Key fields to extract from each automation rule:

- `name` — rule name
- `scorer_id` / scorer reference — which scorer it runs
- `sampling_rate` — current percentage (0–1); if already ≤ 0.1, sampling is not a lever
- `apply_to_root_span` — whether it targets root spans only
- `apply_to_span_names` — specific span names targeted
- `filter` — existing SQL filter clause, if any

Summarize the result before writing recommendations:

```bash
python3 - <<'EOF'
import json
with open('/tmp/bt-cost-automations.json') as f:
    data = json.load(f)
rules = data.get('objects', data) if isinstance(data, dict) else data
for r in rules:
    print(f"name={r.get('name')} sampling={r.get('sampling_rate')} root={r.get('apply_to_root_span')} filter={bool(r.get('filter'))}")
EOF
```

## Scorers

List scorers:

```bash
bt scorers list --json > /tmp/bt-cost-scorers.json
```

Count scorer spans:

```bash
bt sql --json "SELECT span_attributes.name AS scorer_name, COUNT(*) AS calls FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE span_attributes.purpose = 'scorer' AND created >= NOW() - INTERVAL 7 day GROUP BY scorer_name ORDER BY calls DESC LIMIT 50" > /tmp/bt-cost-scorer-calls.json
```

Estimate scorer LLM token usage by model:

```bash
bt sql --json "SELECT metadata.model AS model, COUNT(*) AS calls, SUM(metrics.prompt_tokens) AS prompt_tokens, SUM(metrics.completion_tokens) AS completion_tokens FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE span_attributes.purpose = 'scorer' AND span_attributes.type = 'llm' AND created >= NOW() - INTERVAL 7 day GROUP BY model ORDER BY prompt_tokens + completion_tokens DESC LIMIT 50" > /tmp/bt-cost-scorer-token-usage.json
```

If scorer spans use a different shape, sample them directly:

```bash
bt sql --json "SELECT * FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE span_attributes.purpose = 'scorer' AND created >= NOW() - INTERVAL 7 day LIMIT 500" > /tmp/bt-cost-scorer-spans.json
```

## General LLM Provider Spend

Token usage by model:

```bash
bt sql --json "SELECT metadata.model AS model, COUNT(*) AS calls, SUM(metrics.prompt_tokens) AS prompt_tokens, SUM(metrics.completion_tokens) AS completion_tokens FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE span_attributes.type = 'llm' AND created >= NOW() - INTERVAL 7 day GROUP BY model ORDER BY prompt_tokens + completion_tokens DESC LIMIT 50" > /tmp/bt-cost-llm-token-usage.json
```

If model is stored in another metadata path, sample LLM spans and inspect the row shape:

```bash
bt sql --json "SELECT * FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE span_attributes.type = 'llm' AND created >= NOW() - INTERVAL 7 day LIMIT 100" > /tmp/bt-cost-llm-spans.json
```

Apply model pricing externally; Braintrust logs can expose token counts, but published provider rates and customer-specific discounts are outside project log rows.

## Topics

Topics status and config are available from the CLI:

```bash
bt topics status --json > /tmp/bt-cost-topics-status.json
bt topics status --full --json > /tmp/bt-cost-topics-status-full.json
bt topics config --json > /tmp/bt-cost-topics-config.json
```

Count recent traces available for Topics:

```bash
bt sql --json "SELECT COUNT(DISTINCT root_span_id) AS traces FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day" > /tmp/bt-cost-topic-trace-count.json
```

When topic/facet spans are logged, inspect them:

```bash
bt sql --json "SELECT * FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE span_attributes.type = 'facet' AND created >= NOW() - INTERVAL 7 day LIMIT 100" > /tmp/bt-cost-topic-facet-spans.json
```

## Experiments and Datasets

When experiment or dataset IDs are known:

```bash
bt sql --json "SELECT * FROM experiment('<EXPERIMENT_ID>') LIMIT 500" > /tmp/bt-cost-experiment.json
bt sql --json "SELECT * FROM dataset('<DATASET_ID>') LIMIT 500" > /tmp/bt-cost-dataset.json
```

Run the analyzer on exported experiment or dataset rows to identify oversized fields.

## Local Analysis

Run the analyzer on any exported JSON or JSONL files:

```bash
python3 skills/bt-cost-optimizer/scripts/analyze-cost-drivers.py \
  /tmp/bt-cost-project-spans.json \
  /tmp/bt-cost-scorer-spans.json \
  --sample-days 7 \
  --output bt-cost-optimization-report.md \
  --json-output bt-cost-optimization-summary.json
```

The analyzer is approximate. It ranks likely drivers from sampled row JSON and cannot recover detached attachment body sizes from rows that only contain attachment references.
