# bt-flywheel

An agent skill for continuously improving AI agents built on [Braintrust](https://braintrust.dev).

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

On exit, the skill writes evidence-backed Act recommendations into `bt-flywheel-summary.json`. Common action types include `pull_request`, `pr_comment`, `issue`, `slack`, `jira`, `linear`, `deployment_gate`, `rollback`, `labeling_task`, `rerun_later`, `webhook`, and `none`. The calling workflow decides which side effects to execute.

Works in interactive dev sessions, CI pipelines, scheduled/cron contexts, post-deploy checks, incident follow-up, and other agent harnesses.

## Agent-Agnostic Contract

`bt-flywheel` is meant to be plugged into different coding agents and automation systems. The portable contract is:

1. Make `skills/bt-flywheel/` available to the agent as a skill, instruction bundle, or checked-out reference directory.
2. Give the agent repository access, `bt` CLI access, Braintrust credentials, and project context.
3. Ask the agent to follow `skills/bt-flywheel/SKILL.md`.
4. Expect `bt-flywheel-summary.json` and `bt-flywheel-narrative.md` on exit.
5. Let the surrounding harness decide whether to open a PR, issue, Slack message, Jira/Linear ticket, or do nothing based on `recommended_actions`.

The skill should not depend on a specific coding agent. Agent-specific files such as `.claude/skills/`, `.cursor/`, `AGENTS.md`, or CLI prompts are integration details.

`bt-flywheel-summary.json` should validate against [`schemas/bt-flywheel-summary.schema.json`](schemas/bt-flywheel-summary.schema.json).

## Support Matrix

| Surface | Status | Notes |
|---|---|---|
| Core skill in `skills/bt-flywheel/` | Supported | Portable skill contract and Braintrust workflow |
| Summary schema | Supported | `bt-flywheel-summary.json` output contract |
| Claude Code GitHub Action | Maintained example | Concrete runner harness, not the product boundary |
| Codex / Cursor / OpenCode examples | Templates | Use as starting points; adapt to each runner's current CLI/auth model |
| Slack / Jira / Linear | Recommendation only | The skill emits `recommended_actions`; downstream harnesses execute them |
| Webhooks | Recommendation only | Use `type: "webhook"` plus `webhook_url_env`; downstream harnesses own secrets and delivery |
| Online flywheel scorers | Best-effort portable | Assumes trace spans expose shell/edit/write events with names similar to `Bash`, `Terminal`, `Edit`, or `Write` |

## Install

For any agent or harness, make the skill directory available in your repo or agent skill path:

```bash
mkdir -p .agent-skills
curl -fsSL https://github.com/dpguthrie/flywheel-plugin/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=2 -C .agent-skills flywheel-plugin-main/skills/bt-flywheel
```

For Claude Code plugin installs:

```
/plugin marketplace add dpguthrie/bt-flywheel
/plugin install bt-flywheel@bt-flywheel
```

## Usage

Once installed, invoke the skill directly if your agent supports skills:

```
/bt-flywheel
```

Or ask any coding agent to run the flywheel from the skill path:

> "Use `skills/bt-flywheel/SKILL.md` or `.agent-skills/bt-flywheel/SKILL.md` to improve my Braintrust-backed agent."

## Requirements

- [`bt` CLI](https://github.com/braintrustdata/bt) installed and authenticated
- A Braintrust project with production traffic
- (Optional) `.bt/config.json` configured via `bt setup` for zero-config project resolution

---

## GitHub Actions

This repo includes one reusable GitHub Actions workflow for Claude Code because it needs a concrete runner. Treat it as a maintained example harness, not the only way to use the skill.

Copy `examples/flywheel-caller.yml` to `.github/workflows/flywheel.yml` in your repo and fill in the inputs:

```yaml
jobs:
  flywheel:
    uses: dpguthrie/flywheel-plugin/.github/workflows/bt-flywheel-claude.yml@main
    with:
      project_name: my-braintrust-project
      system_context: |
        Describe your agent here...
      code_paths: src/ evals/ scorers.py
      act_mode: auto
    secrets: inherit
```

Required secrets in your repo: `ANTHROPIC_API_KEY` (to run Claude Code), `BRAINTRUST_API_KEY`.

If your agent calls a third-party LLM directly (OpenAI, Gemini, etc.), pass its key via `extra_env` — the flywheel itself doesn't need it.

Set `code_paths` explicitly. If it is omitted, the workflow does not stage files or open a PR; this avoids accidentally committing generated summaries, logs, downloaded skills, or unrelated files. `act_mode: auto` honors GitHub-executable `recommended_actions` (`pull_request` and `issue`); use `pr`, `issue`, `summary`, or `none` to force a policy. Other action types are surfaced in the summary/artifacts for a downstream harness.

See [`examples/flywheel-caller.yml`](examples/flywheel-caller.yml) for the full annotated Claude Code example. For other coding agents, use the portable templates in [`examples/integrations.md`](examples/integrations.md): the common parts are installing Braintrust, making `skills/bt-flywheel` available, invoking the agent, and consuming the two output artifacts.

---

## Other Triggers

The same skill can be invoked from many harnesses:

| Trigger | Typical Act recommendation |
|---|---|
| Manual local dev session | Summary or PR after review |
| Scheduled weekly improvement job | PR if code changed, issue if follow-up needed |
| Post-deploy verification | Issue or Slack on regression, none if healthy |
| Braintrust score degradation alert | Issue/ticket with trace evidence |
| New production topic cluster | Dataset curation issue or PR |
| PR comment command like `/flywheel` | PR update or review comment |
| Release gate | Block/retry on regression, none if healthy |
| Incident retrospective | Jira/Linear ticket with trace links and eval gaps |
| Dataset refresh cadence | Dataset update plus validation eval |

---

## Flywheel Quality Scorers

The `scorers/` directory contains six Braintrust online scorers that evaluate the quality of the flywheel's own execution — i.e., whether the coding agent runner is following the flywheel methodology correctly.

These are not scorers for your downstream task agent. They score the flywheel coding-agent session itself, catching things like:

| Scorer | What it catches |
|---|---|
| Evidence Before Change | Agent editing code without first running `bt sql` or `bt view` |
| Smoke Test Discipline | Running a full eval without a smoke run first |
| Run Efficiency | Duplicate Bash commands or unnecessary credential-seeking calls |
| Narrative Specificity | Run summaries that are vague ("improved performance") instead of specific (exact deltas, trace links) |
| Diagnostic Coherence | Code changes that aren't motivated by the actual findings |
| Claimed vs Actual | Summary claiming changes that don't match the actual Edit/Write spans |

### Deploying the scorers

Install dependencies and push once to register them in the Braintrust project where your coding-agent traces are logged:

```bash
pip install -r scorers/requirements.txt

BRAINTRUST_API_KEY=... \
BRAINTRUST_CC_PROJECT=my-agent-coding-agent \
FLYWHEEL_CODE_PATHS="src/|evals/|scorers\.py" \
bt functions push --language python \
  --requirements scorers/requirements.txt \
  --if-exists replace \
  scorers/flywheel_scorers.py
```

Re-run any time you want to push updated scorer logic.

`FLYWHEEL_CODE_PATHS` scopes edit-tracking scorers to your source files. Leave it empty to match all Edit/Write spans.

Trace assumption: the online scorers inspect span names for shell/edit/write events. They expect names similar to `Bash:`, `Terminal:`, `Edit:`, or `Write:`. If your coding agent logs different span names, adapt `scorers/_scoring.py` before relying on those scores.

The LLM-judge scorers (`Narrative Specificity`, `Diagnostic Coherence`) use `gpt-4o-mini` by default. Override with `FLYWHEEL_JUDGE_MODEL=<model>`.

---

## Offline Evals

The `evals/` directory contains two Braintrust offline evals for measuring the quality of the flywheel skill itself.

### Why offline evals?

The online scorers (above) catch anti-patterns in individual live runs. The offline evals complement them by:

- Testing the scorer functions against fixture data (regression safety net for scorer changes)
- Validating that the LLM judge rubric correctly distinguishes good flywheel behavior from known failure modes
- Providing a benchmark dataset of positive and negative examples you can extend as new failure modes are discovered

### `evals/eval_scorers.py` — Scorer unit tests

Tests the four deterministic scorer functions (`Evidence Before Change`, `Smoke Test Discipline`, `Run Efficiency`, `Claimed vs Actual`) against 22 fixture span sequences. Each case asserts the computed score falls within an expected range.

```bash
pip install -r evals/requirements.txt

BRAINTRUST_API_KEY=... \
BRAINTRUST_EVAL_PROJECT=bt-flywheel \
braintrust eval evals/eval_scorers.py
```

### `evals/eval_behavior.py` — Behavior quality evaluation

Tests whether the LLM judge correctly rates flywheel behavior against synthetic scenarios: positive examples, Act recommendation examples, and negative failure modes:

| Tag | Scenario | Expected rating |
|---|---|---|
| `healthy-exit` | Healthy production → exits early, no changes | A/B |
| `broken-scorer` | Bimodal distribution → updates scorer | A/B |
| `dataset-gap` | New query patterns → adds examples | A/B |
| `agent-bug-fixed` | Low scores on query type → targeted prompt fix | A/B |
| `no-convergence` | 3 iterations, no improvement → graceful exit | A/B |
| `act-pr` | Code change with passing evals → recommends PR | A/B |
| `act-issue` | Human follow-up needed → recommends issue | A/B |
| `act-webhook` | External release gate → recommends blocking webhook | A/B |
| `act-none` | Healthy system → recommends no action | A/B |
| `unnecessary-changes` | Healthy system → made changes anyway | C/D |
| `wrong-diagnosis` | Bimodal scorer → tried to fix agent code | C/D |
| `vague-summary` | Real issues found → summary has no specifics | C/D |
| `ignored-regressions` | Metric improved but 5 regressions → marked done | C/D |
| `incomplete-diagnosis` | Two issues found → only addressed one | C/D |

```bash
BRAINTRUST_API_KEY=... \
BRAINTRUST_EVAL_PROJECT=bt-flywheel \
FLYWHEEL_JUDGE_MODEL=gpt-4o \
braintrust eval evals/eval_behavior.py
```
