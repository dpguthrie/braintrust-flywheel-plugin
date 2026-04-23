# bt view Patterns

## Rules

- Use `--object-ref project_logs:<project-id>` (with the project UUID, not name)
- `bt view` runs non-interactively when stdin is not a TTY — automatic in CI/cron
- Use `--json` for machine-readable output suitable for piping or parsing
- Prefer `--object-ref` over `-p <project-name>` — `--object-ref` gives precise control over the data source and avoids name ambiguity

---

## Browse Recent Logs

```bash
bt view logs --object-ref project_logs:<project-id> --window 2d --json --limit 50
```

## Filter Logs by Search Term

```bash
bt view logs --object-ref project_logs:<project-id> --window 2d --search "error" --json
```

## Drill Into a Specific Trace

```bash
bt view trace --object-ref project_logs:<project-id> --trace-id <root-span-id> --json
```

## View a Specific Span

```bash
bt view span --object-ref project_logs:<project-id> --id <span-id> --json
```

## View Trace by Braintrust UI URL

```bash
bt view trace --url <braintrust-trace-url>
```
