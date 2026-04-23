# bt-flywheel

A Claude Code skill for continuously improving AI agents built on [Braintrust](https://braintrust.dev).

## What it does

The flywheel guides you through an 8-phase improvement loop:

1. **Orient** — Resolve project config, establish goal and baseline experiment
2. **Discover** — Mine production traces for errors, low scores, latency outliers, and coverage gaps
3. **Diagnose** — Route to what needs changing: scorer, dataset, agent code, or exit if healthy
4. **Curate** — Add production examples to datasets, update scorers
5. **Iterate** — Edit agent code based on findings
6. **Eval** — Run evals with smoke test first
7. **Analyze** — Compare new vs baseline experiment
8. **Loop** — Route back to the right phase, or exit when improved

Works in interactive dev sessions, CI pipelines, and scheduled/cron contexts.

## Install

```
/plugin install dpguthrie/bt-flywheel
```

## Usage

Once installed, invoke the skill:

```
/bt-flywheel
```

Or ask your agent to run the flywheel:

> "Let's improve my agent using the bt-flywheel skill"

## Requirements

- [`bt` CLI](https://github.com/braintrustdata/bt) installed and authenticated
- A Braintrust project with production traffic
- (Optional) `.bt/config.json` configured via `bt setup` for zero-config project resolution
