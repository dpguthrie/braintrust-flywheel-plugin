# bt-flywheel Harbor Scenario: Dataset Gap

Run the `bt-flywheel` skill against the Braintrust project available in this sandbox.

The skill is installed at `/skills/bt-flywheel/SKILL.md`, and the `bt` CLI is already on `PATH`. The CLI is configured for the local Braintrust project and records every `bt` command to `/logs/artifacts/bt-command-log.jsonl`.

Operate in autonomous mode. Do not ask for user input. Do not modify `/app/src`, `/app/evals`, or `/app/scorers`; this task grades the flywheel routing decision, not local code edits.

Expected work:

- Resolve the active Braintrust project from `/app/.bt/config.json` or `bt projects list`.
- Gather production evidence with `bt status`, `bt sql`, dataset inspection, and trace inspection as needed.
- Diagnose whether the observed issue is an agent, dataset, instrumentation, or measurement problem.
- For a dataset route, write curated dataset rows to `/logs/artifacts/curated-dataset-rows.json` and/or call `bt datasets update` with those rows.
- Run a smoke eval with `bt eval --first 20 /app/evals/eval_support.py` before any full `bt eval /app/evals/eval_support.py`.
- Write `bt-flywheel-summary.json` and `bt-flywheel-narrative.md` to `/logs/artifacts/`. You may also write copies in `/app`.

For this scenario, the production failure pattern is absent from the eval dataset. The correct route is dataset curation and verification, not an agent code change.
