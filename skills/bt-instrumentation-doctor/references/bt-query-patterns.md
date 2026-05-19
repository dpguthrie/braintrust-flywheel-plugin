# bt Query Patterns for Instrumentation Review

Use these queries to collect bounded evidence before flagging instrumentation issues. Always set a time window and an explicit `LIMIT`; `bt sql` caps at 1,000 rows per query.

Replace `<PROJECT_ID>` with the resolved ID from `bt projects list --json`.

## Volume and Shape

```bash
# Span and trace counts in the window
bt sql --json "SELECT COUNT(*) AS spans, COUNT(DISTINCT root_span_id) AS traces \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE created >= NOW() - INTERVAL 7 day"

# Spans per trace distribution
bt sql --json "SELECT root_span_id, COUNT(*) AS spans \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE created >= NOW() - INTERVAL 7 day \
  GROUP BY root_span_id \
  ORDER BY spans DESC \
  LIMIT 50"
```

## Span Names

```bash
# Name cardinality (flag explosions: many names with count=1)
bt sql --json "SELECT span_attributes.name AS name, COUNT(*) AS calls \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE created >= NOW() - INTERVAL 7 day \
  GROUP BY name \
  ORDER BY calls DESC \
  LIMIT 200"

# Anonymous / empty names
bt sql --json "SELECT COUNT(*) FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE created >= NOW() - INTERVAL 7 day \
    AND (span_attributes.name IS NULL OR span_attributes.name = '' OR span_attributes.name = 'anonymous')"
```

## Root Span Health

```bash
# Root rows where input or output looks empty
bt sql --json "SELECT id, input, output \
  FROM project_logs('<PROJECT_ID>', shape => 'summary') \
  WHERE created >= NOW() - INTERVAL 7 day \
    AND (input IS NULL OR output IS NULL \
         OR length(CAST(output AS VARCHAR)) < 5) \
  LIMIT 20"
```

## Errors

```bash
# Traces that contain any error span
bt sql --json "SELECT COUNT(*) AS traces_with_errors \
  FROM project_logs('<PROJECT_ID>', shape => 'traces') \
  WHERE created >= NOW() - INTERVAL 7 day \
    AND ANY_SPAN(error IS NOT NULL)"

# Error types
bt sql --json "SELECT error.type AS error_type, COUNT(*) AS n \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE created >= NOW() - INTERVAL 7 day \
    AND error IS NOT NULL \
  GROUP BY error_type \
  ORDER BY n DESC \
  LIMIT 50"
```

## LLM Span Completeness

```bash
# Counts: how many LLM spans have model and token metrics
bt sql --json "SELECT \
    COUNT(*) AS llm_spans, \
    COUNT(metrics.prompt_tokens) AS with_prompt_tokens, \
    COUNT(metrics.completion_tokens) AS with_completion_tokens, \
    COUNT(metadata.model) AS with_model \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE span_attributes.type = 'llm' \
    AND created >= NOW() - INTERVAL 7 day"

# Token usage by model
bt sql --json "SELECT metadata.model AS model, COUNT(*) AS calls, \
    SUM(metrics.prompt_tokens) AS prompt_tokens, \
    SUM(metrics.completion_tokens) AS completion_tokens \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE span_attributes.type = 'llm' \
    AND created >= NOW() - INTERVAL 7 day \
  GROUP BY model \
  ORDER BY prompt_tokens + completion_tokens DESC \
  LIMIT 50"
```

## Scorer Spans

```bash
# Scorer span volume by name and model
bt sql --json "SELECT span_attributes.name AS scorer, metadata.model AS model, COUNT(*) AS calls \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE span_attributes.purpose = 'scorer' \
    AND created >= NOW() - INTERVAL 7 day \
  GROUP BY scorer, model \
  ORDER BY calls DESC \
  LIMIT 50"

# Scorer LLM token cost
bt sql --json "SELECT metadata.model AS model, COUNT(*) AS calls, \
    SUM(metrics.prompt_tokens) AS prompt_tokens, \
    SUM(metrics.completion_tokens) AS completion_tokens \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE span_attributes.purpose = 'scorer' \
    AND span_attributes.type = 'llm' \
    AND created >= NOW() - INTERVAL 7 day \
  GROUP BY model \
  ORDER BY prompt_tokens + completion_tokens DESC"
```

## Thread / Session Coherence

```bash
# Sessions split across multiple roots
bt sql --json "SELECT metadata.session_id, COUNT(DISTINCT root_span_id) AS roots, COUNT(*) AS spans \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE created >= NOW() - INTERVAL 7 day \
    AND metadata.session_id IS NOT NULL \
  GROUP BY metadata.session_id \
  HAVING COUNT(DISTINCT root_span_id) > 1 \
  ORDER BY roots DESC \
  LIMIT 20"
```

If the customer uses a different correlation field (e.g., `metadata.conversation_id`, `metadata.thread_id`), substitute that name. Use `bt sql "SELECT * FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND created >= NOW() - INTERVAL 1 day LIMIT 1"` to discover the metadata fields the customer actually uses.

## Online Scorer Automations

The CLI does not expose automations directly; fetch via REST:

```bash
curl -s "${BRAINTRUST_API_URL:-https://api.braintrust.dev}/v1/project_score?project_id=<PROJECT_ID>&limit=100" \
  -H "Authorization: Bearer ${BRAINTRUST_API_KEY}" > /tmp/bt-doc-automations.json
```

Summarize:

```bash
python3 - <<'EOF'
import json
data = json.load(open('/tmp/bt-doc-automations.json'))
rules = data.get('objects', data) if isinstance(data, dict) else data
for r in rules:
    print(f"name={r.get('name')} root={r.get('apply_to_root_span')} "
          f"names={r.get('apply_to_span_names')} "
          f"sampling={r.get('sampling_rate')} filter={bool(r.get('filter'))}")
EOF
```

If `BRAINTRUST_API_KEY` is unset, note this in the plan and direct the user to **Project → Logs → Score** before making scope or sampling recommendations.

## Deepest Traces (for structural inspection)

```bash
bt sql --json "SELECT root_span_id, COUNT(*) AS spans \
  FROM project_logs('<PROJECT_ID>', shape => 'spans') \
  WHERE created >= NOW() - INTERVAL 7 day \
  GROUP BY root_span_id \
  ORDER BY spans DESC \
  LIMIT 10"
```

For each candidate root, pull the full trace:

```bash
bt view trace --json --project-id <PROJECT_ID> --trace-id <ROOT_SPAN_ID> --limit 200 \
  > /tmp/bt-doc-trace-<ROOT_SPAN_ID>.json
```

## Pagination

`bt sql` caps at 1,000 rows. To collect more:

```bash
bt sql --json "..." > /tmp/page1.json
CURSOR=$(python3 -c "import json; d=json.load(open('/tmp/page1.json')); print(d.get('cursor') or '')")
[ -n "$CURSOR" ] && bt sql --json "... OFFSET '${CURSOR}'" > /tmp/page2.json
```

Cap at 3–5 pages for structural analysis. Diminishing returns set in fast; targeted queries (root spans only, LLM spans only, scorer spans only) give better signal per row than more pages.

## Topics

```bash
bt topics status --json > /tmp/bt-doc-topics-status.json
bt topics config --json > /tmp/bt-doc-topics-config.json
```

If Topics is not configured and the customer is using LLM-as-judge classifiers, surface it as an alternative — see `scorer-setup-patterns.md`.
