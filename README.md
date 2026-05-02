# Braintrust Skills

A collection of agent skills for working with [Braintrust](https://braintrust.dev) through the `bt` CLI and repository-local coding-agent workflows.

## Available Skills

| Skill | Purpose |
|---|---|
| `bt-flywheel` | Continuously improve Braintrust-backed AI agents by mining traces, updating datasets/scorers/code, running evals, and emitting Act recommendations. |
| `bt-cost-optimizer` | Analyze Braintrust logs, scorers, Topics, Gateway/provider spend, datasets, and experiments to recommend safe cost optimizations. |

Install each skill by copying or installing the full directory under `skills/<skill-name>/`; references, scripts, and agent metadata are part of the skill.

## Repository Layout

```text
skills/<skill-name>/        Installable skill bundles. SKILL.md is the canonical per-skill entrypoint.
examples/<skill-name>/      Copyable runner and integration examples.
evals/<skill-name>/         Offline evals for validating a skill's behavior.
scorers/<skill-name>/       Braintrust online scorers or support code for a skill.
```

Do not add `README.md` files inside individual skill directories by default. Keep agent-facing instructions in `SKILL.md`, detailed context in `references/`, deterministic helpers in `scripts/`, and install/navigation docs in this README or [`skills/README.md`](skills/README.md).

## bt-flywheel

### What it does

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

### Agent-Agnostic Contract

`bt-flywheel` is meant to be plugged into different coding agents and automation systems. The portable contract is:

1. Make `skills/bt-flywheel/` available to the agent as a skill, instruction bundle, or checked-out reference directory.
2. Give the agent repository access, `bt` CLI access, Braintrust credentials, and project context.
3. Ask the agent to follow `skills/bt-flywheel/SKILL.md`.
4. Expect `bt-flywheel-summary.json` and `bt-flywheel-narrative.md` on exit.
5. Let the surrounding harness decide whether to open a PR, issue, Slack message, Jira/Linear ticket, or do nothing based on `recommended_actions`.

The skill should not depend on a specific coding agent. Agent-specific files such as `.claude/skills/`, `.cursor/`, `AGENTS.md`, or CLI prompts are integration details.

`bt-flywheel-summary.json` should validate against the schema bundled with the skill, e.g. [`skills/bt-flywheel/schemas/bt-flywheel-summary.schema.json`](skills/bt-flywheel/schemas/bt-flywheel-summary.schema.json) in this repo.

### Support Matrix

| Surface | Status | Notes |
|---|---|---|
| Core skill in `skills/bt-flywheel/` | Supported | Portable skill contract and Braintrust workflow |
| Summary schema | Supported | `bt-flywheel-summary.json` output contract |
| GitHub Actions examples | Maintained examples | Copy into caller repos; no reusable workflow contract |
| Codex / Cursor / OpenCode examples | Templates | Use as starting points; adapt to each runner's current CLI/auth model |
| Slack / Jira / Linear | Recommendation only | The skill emits `recommended_actions`; downstream harnesses execute them |
| Webhooks | Recommendation only | Use `type: "webhook"` plus `webhook_url_env`; downstream harnesses own secrets and delivery |
| Online flywheel scorers | Best-effort portable | Assumes trace spans expose shell/edit/write events with names similar to `Bash`, `Terminal`, `Edit`, or `Write` |

## bt-cost-optimizer

`bt-cost-optimizer` helps a coding agent answer: "What Braintrust usage is driving cost, what can the `bt` CLI prove from data, and how should we safely change logging, scoring, Topics, Gateway usage, datasets, or experiments?"

The skill:

- Uses `bt status`, `bt projects`, `bt sql`, and `bt view` to collect bounded evidence from Braintrust.
- Uses `bt scorers` and `bt topics` to inspect scorer inventory and Topics status/config where available.
- Runs a local analyzer over exported rows to rank high-byte fields, largest traces, scorer spans, LLM token usage, and `JSONAttachment` candidates.
- Inspects local code for Braintrust logging, scorer, and Gateway patterns and maps sample findings back to instrumentation.
- Produces `bt-cost-optimization-report.md` and optionally `bt-cost-optimization-summary.json`.

The skill distinguishes measured findings from advisory recommendations. `bt` can measure sampled rows, scorer spans, token totals, and Topics config/status; exact bill totals, negotiated pricing, retention policy, and Gateway cache/routing config may require billing/UI or code/config context.

## Install Skills

Install the whole skill directory, not only `SKILL.md`; the `references/`, `scripts/`, and `agents/` files are part of each skill.

For Codex, use the standard skill installer and choose the skill path:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo dpguthrie/braintrust-skills \
  --path skills/bt-flywheel

python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo dpguthrie/braintrust-skills \
  --path skills/bt-cost-optimizer
```

For project-local CI or another agent harness, copy the full skill directory into the runner's skill path:

```bash
mkdir -p .agent-skills
curl -fsSL https://github.com/dpguthrie/braintrust-skills/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=2 -C .agent-skills braintrust-skills-main/skills/bt-flywheel

curl -fsSL https://github.com/dpguthrie/braintrust-skills/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=2 -C .agent-skills braintrust-skills-main/skills/bt-cost-optimizer
```

For Claude Code, install both skills at once via the plugin:

```bash
claude plugins install github:dpguthrie/braintrust-skills
```

## Usage

Once installed, invoke the skill directly if your agent supports skills:

```
/bt-flywheel
/bt-cost-optimizer
```

Or ask any coding agent to run the skill from the skill path:

> "Use `skills/bt-flywheel/SKILL.md` or `.agent-skills/bt-flywheel/SKILL.md` to improve my Braintrust-backed agent."

For ingest optimization:

> "Use `skills/bt-cost-optimizer/SKILL.md` or `.agent-skills/bt-cost-optimizer/SKILL.md` to analyze my Braintrust usage costs and recommend safe optimizations."

## Common Requirements

- [`bt` CLI](https://github.com/braintrustdata/bt) installed and authenticated
- A Braintrust project with logs, experiments, or datasets to inspect
- (Optional) `.bt/config.json` configured via `bt setup` for zero-config project resolution

---

## bt-flywheel GitHub Actions

This repo includes example GitHub Actions workflows you can copy into your own repository. They install the skill and define the runner logic locally; they do not call a reusable workflow from this repo.

Copy `examples/bt-flywheel/flywheel-caller.yml` to `.github/workflows/flywheel.yml` in your repo and customize the project-specific values, install command, prompt context, and staged paths.

Required secrets in your repo: `ANTHROPIC_API_KEY` (to run Claude Code), `BRAINTRUST_API_KEY`.

If your agent calls a third-party LLM directly (OpenAI, Gemini, etc.), include its key in the workflow environment or `.env` the workflow writes for eval invocations.

Set staged paths explicitly in the workflow's change-detection step. Avoid `git add .` so generated summaries, logs, downloaded skills, and unrelated changes do not get committed accidentally.

See [`examples/bt-flywheel/flywheel-caller.yml`](examples/bt-flywheel/flywheel-caller.yml) for the full annotated Claude Code example. For other coding agents, use the portable templates in [`examples/bt-flywheel/integrations.md`](examples/bt-flywheel/integrations.md): the common parts are installing Braintrust, making `skills/bt-flywheel` available, invoking the agent, and consuming the two output artifacts.

---

## bt-flywheel Other Triggers

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

The `scorers/bt-flywheel/` directory contains six Braintrust online scorers that evaluate the quality of the flywheel's own execution — i.e., whether the coding agent runner is following the flywheel methodology correctly.

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
pip install -r scorers/bt-flywheel/requirements.txt

BRAINTRUST_API_KEY=... \
BRAINTRUST_CC_PROJECT=my-agent-coding-agent \
FLYWHEEL_CODE_PATHS="src/|evals/|scorers\.py" \
bt functions push --language python \
  --requirements scorers/bt-flywheel/requirements.txt \
  --if-exists replace \
  scorers/bt-flywheel/flywheel_scorers.py
```

Re-run any time you want to push updated scorer logic.

`FLYWHEEL_CODE_PATHS` scopes edit-tracking scorers to your source files. Leave it empty to match all Edit/Write spans.

Trace assumption: the online scorers inspect span names for shell/edit/write events. They expect names similar to `Bash:`, `Terminal:`, `Edit:`, or `Write:`. If your coding agent logs different span names, adapt `scorers/bt-flywheel/_scoring.py` before relying on those scores.

The LLM-judge scorers (`Narrative Specificity`, `Diagnostic Coherence`) use `gpt-4o-mini` by default. Override with `FLYWHEEL_JUDGE_MODEL=<model>`.

---

## Offline Evals

The `evals/bt-flywheel/` directory contains two Braintrust offline evals for measuring the quality of the flywheel skill itself.

### Why offline evals?

The online scorers (above) catch anti-patterns in individual live runs. The offline evals complement them by:

- Testing the scorer functions against fixture data (regression safety net for scorer changes)
- Validating that the LLM judge rubric correctly distinguishes good flywheel behavior from known failure modes
- Providing a benchmark dataset of positive and negative examples you can extend as new failure modes are discovered

### `evals/bt-flywheel/eval_scorers.py` — Scorer unit tests

Tests the four deterministic scorer functions (`Evidence Before Change`, `Smoke Test Discipline`, `Run Efficiency`, `Claimed vs Actual`) against 22 fixture span sequences. Each case asserts the computed score falls within an expected range.

```bash
pip install -r evals/bt-flywheel/requirements.txt

BRAINTRUST_API_KEY=... \
BRAINTRUST_EVAL_PROJECT=bt-flywheel \
braintrust eval evals/bt-flywheel/eval_scorers.py
```

### `evals/bt-flywheel/eval_behavior.py` — Behavior quality evaluation

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
braintrust eval evals/bt-flywheel/eval_behavior.py
```
