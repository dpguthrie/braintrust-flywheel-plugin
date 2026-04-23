# bt functions and bt datasets Patterns

## Availability Note

`bt functions` may not be available in all `bt` versions. Before using it, run `bt --help` and check whether `functions` appears in the command list.

**If `bt functions` is unavailable:**
- For reading prompts: use `bt prompts list --project <name>` (always available)
- For writing scorers/prompts: use the Braintrust UI or the Python SDK directly

Similarly, `bt datasets` may not be available — check with `bt --help`.

---

## bt functions Commands

### List all functions in a project
```bash
bt functions list --project <project-name>
```

### Read a specific function (prompt, scorer, or tool)
```bash
bt functions view <function-slug> -p <project-name>
```

### Push an updated function from a local file
```bash
bt functions push -p <project-name> --file <path-to-file>
```

---

## Fallback: bt prompts (read operations only)

```bash
# List all prompts
bt prompts list -p <project-name>

# View a specific prompt's content
bt prompts view <slug> -p <project-name>
```

---

## bt datasets Commands (when available)

### List datasets in a project
```bash
bt datasets list --project <project-name>
```

### Read dataset contents
```bash
bt datasets get --project <project-name> --name <dataset-name>
```

If `bt datasets` is unavailable, use `bt sql` to inspect dataset content and the Python SDK below for writes.

---

## Python SDK: Dataset Writes

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

Note: use `braintrust.init_dataset()` directly — do **not** use the return value of `braintrust.login()`. `login()` returns `None`.
