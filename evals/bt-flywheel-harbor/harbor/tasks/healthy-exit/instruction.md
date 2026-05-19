# bt-flywheel Harbor Scenario: Healthy Exit

Run the `bt-flywheel` skill against the Braintrust project available in this sandbox.

The skill is installed at `/skills/bt-flywheel/SKILL.md`, and the `bt` CLI is already on `PATH`. The CLI is configured for the local Braintrust project and records every `bt` command to `/logs/artifacts/bt-command-log.jsonl`.

Operate in autonomous mode. Do not ask for user input. Do not modify `/app/src`, `/app/evals`, or `/app/scorers`; this task grades the flywheel routing decision, not local code edits.

Expected work:

- Resolve the active Braintrust project from `/app/.bt/config.json` or `bt projects list`.
- Gather production evidence with `bt status`, `bt sql`, and trace inspection as needed.
- Diagnose whether the system is healthy.
- Write `bt-flywheel-summary.json` and `bt-flywheel-narrative.md` to `/logs/artifacts/`. You may also write copies in `/app`.

For this scenario, production metrics are healthy. The correct route is to make no changes and exit with `outcome: "healthy"` and first `next_steps` intent `no_action`.
