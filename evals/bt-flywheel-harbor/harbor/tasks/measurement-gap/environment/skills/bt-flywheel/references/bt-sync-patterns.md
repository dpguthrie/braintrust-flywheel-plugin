# bt sync Patterns

Synchronize project logs, experiments, or datasets between Braintrust and local NDJSON files.
Useful for bulk analysis, offline processing, or migrating data between projects.

Supported object refs:
- `project_logs:<project-id|project-name>`
- `experiment:<experiment-id|experiment-name>` (requires `-p` for names)
- `dataset:<dataset-id|dataset-name>` (requires `-p` for names)

---

## Pull (Download to Local JSONL)

```bash
# Pull last 3 days of project logs (default window: 3d)
bt sync pull project_logs:<project-id> --window 3d

# Pull to a custom root directory (default: ./bt-sync)
bt sync pull project_logs:<project-id> --window 7d --root ./data

# Pull with a SQL filter to narrow the data
bt sync pull project_logs:<project-id> --filter "is_root = true AND error IS NOT NULL"

# Pull a specific number of traces
bt sync pull project_logs:<project-id> --traces 500

# Pull an experiment
bt sync pull experiment:<experiment-id> -p <project-name>

# Pull a dataset
bt sync pull dataset:<dataset-name> -p <project-name>

# Fresh pull (ignore previous sync state and start over)
bt sync pull project_logs:<project-id> --fresh
```

---

## Push (Upload Local JSONL Back to Braintrust)

```bash
bt sync push project_logs:<project-id> --in bt-sync/project_logs
```

---

## Status (Show Local Sync State)

```bash
bt sync status project_logs:<project-id>
```
