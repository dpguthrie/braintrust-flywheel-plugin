# bt sql Patterns

SQL query patterns for the Braintrust flywheel. Replace `<PROJECT_ID>`, `<SCORE_COL>`, `<FACET_COL>`, `<LATENCY_FIELD>`, and metadata paths with discovered fields.

## Contents

- Rules
- Discovery Strategy
- Schema Discovery
- Broad Discovery Queries
- Search Queries
- Coverage Queries
- Experiment Queries

## Rules

- Prefer standard SQL syntax for new queries.
- Always bound `project_logs()` with `created`, `_xact_id`, `_pagination_key`, `root_span_id`, or `id`.
- Use `NOW() - INTERVAL N day`, not `INTERVAL 'N days'`.
- Pick the right shape:
  - default/`spans`: individual matching spans.
  - `shape => 'traces'`: all spans from traces that match span conditions.
  - `shape => 'summary'`: one trace-level row with aggregate metrics and root previews.
- Inspect schema first; metric names can differ by shape/project. Common fields include `scores`, `facets`, `classifications`, `metadata`, `error`, `span_attributes`, and `metrics`.
- Quote nested fields with spaces: `scores."Response Quality"`.
- Use `search('<term>')` to search across text fields. Use `<field> MATCH '<term>'` for exact word search in one field. Use `ILIKE '%term%'` for bounded substring searches.
- In SQL mode, `JOIN`, `UNION`/`INTERSECT`/`EXCEPT`, window functions, and `INCLUDES` are unsupported. Subqueries are supported in `FROM`. Use BTQL syntax when exact array membership via `INCLUDES` is required.

## Discovery Strategy

Start with broad aggregates, then write follow-up queries from what the data reveals. Useful query seeds:

- known or suspected error strings
- user complaint language
- tool/function names
- refusal or safety words
- output contract terms
- domain nouns from failed tasks
- topic/facet/classification labels
- recent prompt/model/deploy identifiers

Prefer comparing cohorts over reading only worst cases: low vs high score, recent vs older, high cost vs normal, topic A vs topic B, production vs eval.

## Schema Discovery

```bash
# Try 1 day first; if empty, try 7 day, then 30 day.
bt sql "SELECT * FROM project_logs('<PROJECT_ID>', shape => 'summary') WHERE created >= NOW() - INTERVAL 1 day LIMIT 1"

# Inventory dynamic score names without knowing them up front.
bt sql "SELECT score, COUNT(value) AS n, AVG(value) AS avg_value, MIN(value) AS min_value, MAX(value) AS max_value
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        UNPIVOT (value FOR score IN (scores))
        WHERE created >= NOW() - INTERVAL 7 day
        GROUP BY score
        ORDER BY avg_value ASC"
```

## Broad Discovery Queries

### Traffic volume

```bash
bt sql "SELECT day(created) AS date, COUNT(1) AS trace_count
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 14 day
        GROUP BY day(created)
        ORDER BY date DESC"
```

### Errors by type and cohort

```bash
bt sql "SELECT error.type AS error_type, metadata.model AS model, COUNT(1) AS trace_count
        FROM project_logs('<PROJECT_ID>', shape => 'traces')
        WHERE created >= NOW() - INTERVAL 7 day
          AND ANY_SPAN(error IS NOT NULL)
        GROUP BY error.type, metadata.model
        ORDER BY trace_count DESC
        LIMIT 25"
```

### Low scores

```bash
bt sql "SELECT id, created, input, output, scores.\"<SCORE_COL>\" AS score
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 7 day
          AND scores.\"<SCORE_COL>\" <= 0.5
        ORDER BY created DESC
        LIMIT 50"
```

### Score distribution

```bash
bt sql "SELECT scores.\"<SCORE_COL>\" AS score, COUNT(1) AS count
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 7 day
        GROUP BY scores.\"<SCORE_COL>\"
        ORDER BY score"
```

### Segment score and latency

Use fields discovered in schema inspection. Replace `<LATENCY_FIELD>` with a real numeric field such as `metrics.duration`, `metrics.duration_ms`, or a project-specific latency path.

```bash
bt sql "SELECT metadata.model AS model,
               COUNT(1) AS trace_count,
               AVG(scores.\"<SCORE_COL>\") AS avg_score,
               percentile(<LATENCY_FIELD>, 0.95) AS p95_latency
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 7 day
        GROUP BY metadata.model
        HAVING COUNT(1) >= 10
        ORDER BY avg_score ASC"
```

### High latency or cost outliers

```bash
bt sql "SELECT id, created, input, <LATENCY_FIELD> AS latency, metrics.total_tokens, estimated_cost() AS cost
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 7 day
        ORDER BY latency DESC
        LIMIT 25"
```

## Search Queries

Use `search()` when the relevant text could appear in input, output, expected, metadata, or span attributes. Combine search with score, metadata, and time bounds so results stay diagnostic.

### Search across all text fields

```bash
bt sql "SELECT id, created, input, output, scores.\"<SCORE_COL>\" AS score
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 7 day
          AND search('<TERM>')
        ORDER BY created DESC
        LIMIT 50"
```

### Search one field with exact word matching

```bash
bt sql "SELECT id, created, input, output
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 7 day
          AND input MATCH '<TERM>'
        ORDER BY created DESC
        LIMIT 50"
```

### Find searched traces that also contain tool or error spans

```bash
bt sql "SELECT *
        FROM project_logs('<PROJECT_ID>', shape => 'traces')
        WHERE created >= NOW() - INTERVAL 7 day
          AND search('<TERM>')
          AND ANY_SPAN(span_attributes.type = 'tool' OR error IS NOT NULL)
        LIMIT 100"
```

## Coverage Queries

### Facet distribution

```bash
bt sql "SELECT facets.\"<FACET_COL>\" AS facet, COUNT(1) AS count
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 7 day
        GROUP BY facets.\"<FACET_COL>\"
        ORDER BY count DESC
        LIMIT 50"
```

### Classification labels

```bash
bt sql "SELECT classifications.\"<CLASSIFIER>\"[0].label AS label, COUNT(1) AS count
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 7 day
        GROUP BY classifications.\"<CLASSIFIER>\"[0].label
        ORDER BY count DESC
        LIMIT 50"
```

### Topic/facet score gaps

```bash
bt sql "SELECT facets.\"<FACET_COL>\" AS facet,
               COUNT(1) AS trace_count,
               AVG(scores.\"<SCORE_COL>\") AS avg_score
        FROM project_logs('<PROJECT_ID>', shape => 'summary')
        WHERE created >= NOW() - INTERVAL 7 day
        GROUP BY facets.\"<FACET_COL>\"
        HAVING COUNT(1) >= 10
        ORDER BY avg_score ASC"
```

## Experiment Queries

### Sample rows

```bash
bt sql "SELECT id, scores.\"<SCORE_COL>\", input, output FROM experiment('<experiment-id>') LIMIT 20"
```

### Score statistics

```bash
bt sql "SELECT AVG(scores.\"<SCORE_COL>\") AS avg_score,
               MIN(scores.\"<SCORE_COL>\") AS min_score,
               MAX(scores.\"<SCORE_COL>\") AS max_score
        FROM experiment('<experiment-id>')"
```

### Regressions

```bash
bt sql "SELECT id, scores.\"<SCORE_COL>\" AS score, input, output
        FROM experiment('<experiment-id>')
        WHERE scores.\"<SCORE_COL>\" < 0.5
        ORDER BY score ASC"
```

### Scorer distribution

```bash
bt sql "SELECT scores.\"<SCORE_COL>\" AS score, COUNT(1) AS count
        FROM experiment('<experiment-id>')
        GROUP BY scores.\"<SCORE_COL>\"
        ORDER BY score"
```
