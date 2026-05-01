# bt functions, bt scorers, bt tools, bt prompts Patterns

## Command Overview

`bt functions` manages all function types (LLM prompts, scorers, tools, tasks, etc.) with full CRUD + invoke.
Type-scoped aliases `bt scorers`, `bt tools`, and `bt prompts` are read-only shortcuts (list/view/delete — no push/pull/invoke).

---

## bt functions list

```bash
# List all functions in the active project
bt functions list -p <project-name>

# Filter by type: llm, scorer, task, tool, custom-view, preprocessor, facet, classifier, tag, parameters
bt functions list -p <project-name> -t scorer
bt functions list -p <project-name> --json
```

---

## bt functions view

```bash
bt functions view <function-slug> -p <project-name>
bt functions view <function-slug> -p <project-name> --json
```

---

## bt functions invoke

Test a function without running a full eval:

```bash
# Invoke with JSON input
bt functions invoke <slug> -p <project-name> --input '{"key": "value"}'

# Invoke an LLM prompt with a user message
bt functions invoke <slug> -p <project-name> --message "Summarize this"

# Pin to a specific version
bt functions invoke <slug> -p <project-name> --version <version-id>

# Force JSON output mode
bt functions invoke <slug> -p <project-name> --mode json
```

---

## bt functions push

Push local function definitions (prompts, scorers, tools) to Braintrust:

```bash
# Push from a file or directory
bt functions push -p <project-name> <path>
bt functions push -p <project-name> --file <path>

# Control behavior when slug already exists (default: error)
bt functions push -p <project-name> --if-exists replace <path>
bt functions push -p <project-name> --if-exists ignore <path>

# Skip confirmation prompt (for CI)
bt functions push -p <project-name> -y <path>
```

---

## bt functions pull

Download remote function definitions as local files:

```bash
# Pull a specific function by slug
bt functions pull <slug> -p <project-name>

# Pull to a specific output directory (default: ./braintrust)
bt functions pull <slug> -p <project-name> --output-dir ./scorers

# Pull as Python instead of TypeScript
bt functions pull <slug> -p <project-name> --language python

# Overwrite even if local file is modified
bt functions pull <slug> -p <project-name> --force
```

---

## bt functions delete

```bash
bt functions delete <slug> -p <project-name>
```

---

## bt prompts (read-only alias)

```bash
bt prompts list -p <project-name>
bt prompts view <slug> -p <project-name>
bt prompts delete <slug> -p <project-name>
```

---

## bt scorers / bt tools (read-only aliases)

```bash
bt scorers list -p <project-name>
bt scorers view <slug> -p <project-name>
bt tools list -p <project-name>
bt tools view <slug> -p <project-name>
```

---

## bt datasets: Dataset Reads/Writes

Use the `bt datasets` CLI for routine dataset operations. Prefer stable row IDs so refreshes are idempotent.

```bash
# List and inspect datasets
bt datasets list -p <project-name> --json
bt datasets view <dataset-name> -p <project-name> --json --full --limit 20

# Create a dataset and seed rows from JSON or JSONL
bt datasets create <dataset-name> -p <project-name> --file records.jsonl --id-field id

# Upsert rows into an existing dataset by stable record id
bt datasets update <dataset-name> -p <project-name> --file records.jsonl --id-field id
```

Rows can be JSON array entries or JSONL records. Keep the record ID stable across flywheel runs:

```json
{
  "id": "flywheel:<project-id>:<source-trace-id>",
  "input": {"messages": [{"role": "user", "content": "..."}]},
  "expected": "...",
  "tags": ["production", "flywheel-curated", "validation", "failing"],
  "metadata": {
    "source_trace_id": "<source-trace-id>",
    "source_project_id": "<project-id>",
    "bucket": "failing",
    "split": "validation",
    "flywheel_iteration": "<iteration-id>"
  }
}
```

For a quick single-row update, inline JSON is acceptable:

```bash
bt datasets update <dataset-name> -p <project-name> \
  --rows '[{"id":"case-1","input":{"text":"hi"},"expected":"hello"}]' \
  --id-field id
```

For broad filtered reads, `bt sql` is still useful:

```bash
bt sql "SELECT * FROM dataset('<dataset-id>') LIMIT 20"
```
