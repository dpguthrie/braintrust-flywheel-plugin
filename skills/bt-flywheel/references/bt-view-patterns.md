# bt view Patterns

## Rules

- Use `--object-ref project_logs:<project-id>` (with the project UUID, not name)
- `bt view` runs non-interactively when stdin is not a TTY — automatic in CI/cron
- Use `--json` for machine-readable output suitable for piping or parsing
- Prefer `--object-ref` over `-p <project-name>` — `--object-ref` gives precise control over the data source and avoids name ambiguity

---

## Browse Recent Logs (summary mode — default)

```bash
bt view logs --object-ref project_logs:<project-id> --window 2d --json --limit 50
```

## Browse Logs in Spans Mode

```bash
bt view logs --object-ref project_logs:<project-id> --window 2d --list-mode spans --json
```

## Filter Logs by Free-Text Search

```bash
bt view logs --object-ref project_logs:<project-id> --window 2d --search "error" --json
```

## Filter Logs by BTQL Expression

```bash
# Show only root spans with errors
bt view logs --object-ref project_logs:<project-id> --filter "is_root = true AND error IS NOT NULL" --json

# Combine search and filter
bt view logs --object-ref project_logs:<project-id> --search "timeout" --filter "is_root = true" --json
```

## Filter Logs by Absolute Timestamp

```bash
# Use --since instead of --window for absolute lower bounds
bt view logs --object-ref project_logs:<project-id> --since "2025-01-01T00:00:00Z" --json
```

## Drill Into a Specific Trace

```bash
bt view trace --object-ref project_logs:<project-id> --trace-id <root-span-id> --json
```

## View a Specific Span

```bash
bt view span --object-ref project_logs:<project-id> --id <span-id> --json
```

## View Trace or Span by Braintrust UI URL

```bash
bt view trace --url <braintrust-trace-url>
bt view span --url <braintrust-span-url>
```

## View Experiment Logs

```bash
bt view logs --object-ref experiment:<experiment-id> --json
bt view trace --object-ref experiment:<experiment-id> --trace-id <root-span-id> --json
```
