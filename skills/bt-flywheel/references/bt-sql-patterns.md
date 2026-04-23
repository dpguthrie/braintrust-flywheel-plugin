# bt sql Patterns

SQL query templates for the Braintrust flywheel. Replace `<PROJECT_ID>` with your project UUID and `<SCORE_COL>` with discovered score column names (double-quoted if they contain spaces, e.g., `scores."Response Quality"`).

## Rules

- Always use `project_logs('<PROJECT_ID>')` for production logs — never bare table names
- Every `project_logs()` query must include a time range filter on `created` (or `_xact_id`, `_pagination_key`, or a specific span ID)
- Use `NOW() - INTERVAL N day` — not `INTERVAL 'N days'`
- Facets and classifications require `shape => 'traces'`; scores use the default shape
- Nested fields use dot notation: `scores."My Score"`, `facets.Sentiment`
- Fields with spaces must be double-quoted: `scores."My Score"`
- No subqueries, JOINs, UNIONs, or window functions
- Use `ILIKE` for case-insensitive matching, `MATCH` for full-word search
- Use MATCH to search a specific field for exact word matches, or search() to search across all text fields at once.  search() is equivalent to writing input MATCH query OR output MATCH query OR ... for each text field
---

## Schema Discovery

```bash
# Try 1 day first; if empty, try 7 day, then 30 day
bt sql "SELECT * FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND created >= NOW() - INTERVAL 1 day LIMIT 1"
```

---

## Discovery Queries (Discover Phase)

### Errors
```bash
bt sql "SELECT id, error FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND error IS NOT NULL AND created >= NOW() - INTERVAL 7 day LIMIT 20"
```

### Low scores
```bash
bt sql "SELECT id, scores.\"<SCORE_COL>\" FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND scores.\"<SCORE_COL>\" <= 0.5 AND created >= NOW() - INTERVAL 7 day LIMIT 20"
```

### High latency
```bash
bt sql "SELECT id, metrics.duration_ms FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND metrics.duration_ms > 10000 AND created >= NOW() - INTERVAL 7 day ORDER BY metrics.duration_ms DESC LIMIT 20"
```

### Score distribution (detect scorer anomalies — stuck at 0/1)
```bash
bt sql "SELECT scores.\"<SCORE_COL>\", COUNT(*) AS count FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND created >= NOW() - INTERVAL 7 day GROUP BY scores.\"<SCORE_COL>\" ORDER BY scores.\"<SCORE_COL>\""
```

### Facet distribution (requires traces shape)
```bash
bt sql "SELECT facets.\"<FACET_COL>\", COUNT(*) AS count FROM project_logs('<PROJECT_ID>', shape => 'traces') WHERE created >= NOW() - INTERVAL 7 day GROUP BY facets.\"<FACET_COL>\" ORDER BY count DESC"
```

---

## Experiment Queries (Analyze Phase)

### Sample rows
```bash
bt sql "SELECT id, scores.\"<SCORE_COL>\", output FROM experiment('<experiment-id>') LIMIT 20"
```

### Score statistics
```bash
bt sql "SELECT AVG(scores.\"<SCORE_COL>\") AS avg_score, MIN(scores.\"<SCORE_COL>\") AS min_score, MAX(scores.\"<SCORE_COL>\") AS max_score FROM experiment('<experiment-id>')"
```

### Regressions (below threshold)
```bash
bt sql "SELECT id, scores.\"<SCORE_COL>\" FROM experiment('<experiment-id>') WHERE scores.\"<SCORE_COL>\" < 0.5"
```

### Scorer distribution (check for stuck at 0/1)
```bash
bt sql "SELECT scores.\"<SCORE_COL>\", COUNT(*) AS count FROM experiment('<experiment-id>') GROUP BY scores.\"<SCORE_COL>\" ORDER BY scores.\"<SCORE_COL>\""
```
