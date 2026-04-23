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

## Python SDK: Dataset Writes

`bt` has no `datasets` subcommand — use the Python SDK for dataset operations:

```python
import braintrust, os
braintrust.login(api_key=os.getenv("BRAINTRUST_API_KEY"))
dataset = braintrust.init_dataset(project="<project-name>", name="<dataset-name>")

# Insert a new example
dataset.insert({
    "input": {"messages": [{"role": "user", "content": "..."}]},
    "expected": "...",
    "tags": ["production", "edge-case"]
})
```

Use `braintrust.init_dataset()` directly — `braintrust.login()` returns `None`.

To inspect existing dataset content, use `bt sql`:
```bash
bt sql "SELECT * FROM dataset('<dataset-id>') LIMIT 20"
```
