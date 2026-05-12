# Braintrust Skills

A collection of agent skills for working with [Braintrust](https://braintrust.dev) through the `bt` CLI and repository-local coding-agent workflows.

## Available Skills

| Skill | Purpose |
|---|---|
| `bt-flywheel` | Continuously improve Braintrust-backed AI agents by mining traces, updating measurement/datasets/code/instrumentation, running evals, and emitting portable exit handoffs. |
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

The flywheel guides you through a 5-phase improvement loop:

1. **Orient** — Resolve project config, establish goal and baseline experiment
2. **Discover** — Mine production traces broadly for errors, scores, search clusters, topics, latency/cost, behavior, and coverage gaps
3. **Diagnose** — Route to what needs changing: measurement/scorer, dataset, agent code, instrumentation, or exit if healthy
4. **Improve** — Apply the artifact-specific route: measurement, dataset, agent, or instrumentation
5. **Verify & Decide** — Run smoke/full evals, compare to baseline, inspect regressions, route another loop or exit

On exit, the skill writes an adapter-neutral handoff into `bt-flywheel-summary.json`. It includes outcome, severity, blocking status, confidence, findings, changes, verification, structured links, local artifacts, and intent-based `next_steps`. The calling workflow maps those next steps to local review, CI, GitHub, Slack, Jira/Linear, app UI, release gates, webhooks, or no side effect.

Works in interactive dev sessions, CI pipelines, scheduled/cron contexts, post-deploy checks, incident follow-up, and other agent harnesses.

### Agent-Agnostic Contract

`bt-flywheel` is meant to be plugged into different coding agents and automation systems. The portable contract is:

1. Make `skills/bt-flywheel/` available to the agent as a skill, instruction bundle, or checked-out reference directory.
2. Give the agent repository access, `bt` CLI access, Braintrust credentials, and project context.
3. Ask the agent to follow `skills/bt-flywheel/SKILL.md`.
4. Expect `bt-flywheel-summary.json` and `bt-flywheel-narrative.md` on exit.
5. Let the surrounding harness decide whether to open a PR, issue, Slack message, Jira/Linear ticket, release gate, app notification, or do nothing based on `outcome`, `blocking`, and `next_steps`.

The skill should not depend on a specific coding agent. Agent-specific files such as `.claude/skills/`, `.cursor/`, `AGENTS.md`, or CLI prompts are integration details.

`bt-flywheel-summary.json` should validate against the schema bundled with the skill, e.g. [`skills/bt-flywheel/schemas/bt-flywheel-summary.schema.json`](skills/bt-flywheel/schemas/bt-flywheel-summary.schema.json) in this repo.

### Support Matrix

| Surface | Status | Notes |
|---|---|---|
| Core skill in `skills/bt-flywheel/` | Supported | Portable skill contract and Braintrust workflow |
| Summary schema | Supported | `bt-flywheel-summary.json` output contract |
| GitHub Actions examples | Maintained examples | Copy into caller repos; no reusable workflow contract |
| Codex / Cursor / OpenCode examples | Templates | Use as starting points; adapt to each runner's current CLI/auth model |
| Slack / Jira / Linear | Handoff only | The skill emits adapter-neutral `next_steps`; downstream harnesses map and execute them |
| Webhooks | Handoff only | Use caller-owned configuration; never put raw webhook URLs in the handoff |
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

For Claude Code (and most other agents), use `npx skills`:

```bash
npx skills add dpguthrie/braintrust-skills@bt-flywheel -g -y
npx skills add dpguthrie/braintrust-skills@bt-cost-optimizer -g -y
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

| Trigger | Typical handoff intent |
|---|---|
| Manual local dev session | `review_change`, `investigate`, or `no_action` |
| Scheduled weekly improvement job | `review_change` if changes were made, `investigate` if follow-up is needed |
| Post-deploy verification | `block_release`, `notify`, or `no_action` |
| Braintrust score degradation alert | `investigate` with trace evidence |
| New production topic cluster | `label_data`, `review_change`, or `investigate` |
| PR comment command like `/flywheel` | `review_change` or `notify` |
| Release gate | `block_release`, `rerun`, or `no_action` |
| Incident retrospective | `investigate` with trace links and eval gaps |
| Dataset refresh cadence | `review_change` plus validation eval |

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

Tests whether the LLM judge correctly rates flywheel behavior against synthetic scenarios: positive examples, exit handoff examples, and negative failure modes:

| Tag | Scenario | Expected rating |
|---|---|---|
| `healthy-exit` | Healthy production → exits early, no changes | A/B |
| `broken-scorer` | Bimodal distribution → updates scorer | A/B |
| `new-scorer-needed` | Repeated unmeasured failure → adds measurement first | A/B |
| `dataset-gap` | New query patterns → adds examples | A/B |
| `agent-bug-fixed` | Low scores on query type → targeted prompt fix | A/B |
| `no-convergence` | 3 iterations, no improvement → graceful exit | A/B |
| `handoff-review-change` | Code change with passing evals → suggests review | A/B |
| `handoff-investigate` | Human follow-up needed → suggests investigation/labeling | A/B |
| `handoff-block-release` | External release gate → suggests blocking release | A/B |
| `handoff-no-action` | Healthy system → suggests no action | A/B |
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

### `evals/bt-flywheel-harness/eval_harness.py` — Offline fixture harness

Runs small fixture repositories through a deterministic flywheel harness. The harness installs a fake `bt` CLI on `PATH`, replays scenario-specific Braintrust responses, captures `bt-flywheel-summary.json`, records changed files and `bt` usage, runs fixture acceptance checks, and scores the result against the expected handoff contract.

See [`evals/bt-flywheel-harness/README.md`](evals/bt-flywheel-harness/README.md) for the full harness guide and current limitations.
See [`evals/bt-flywheel-harness/EVALUATION_STRATEGY.md`](evals/bt-flywheel-harness/EVALUATION_STRATEGY.md) for the recommended online trace-first direction. The scripted runner is only a harness smoke test; real skill evaluation should score actual Claude/Codex runs and their traces/artifacts.

Local smoke run, no Braintrust credentials required:

```bash
python3 evals/bt-flywheel-harness/run_harness.py --runner scripted
```

Braintrust Eval run:

```bash
pip install -r evals/bt-flywheel-harness/requirements.txt

BRAINTRUST_API_KEY=... \
BRAINTRUST_EVAL_PROJECT=bt-flywheel \
braintrust eval evals/bt-flywheel-harness/eval_harness.py
```

Compare skill variants:

```bash
FLYWHEEL_HARNESS_SKILL_VARIANTS=none,current \
BRAINTRUST_API_KEY=... \
braintrust eval evals/bt-flywheel-harness/eval_harness.py
```

Run with Claude Code:

```bash
FLYWHEEL_HARNESS_RUNNER=claude \
BRAINTRUST_API_KEY=... \
braintrust eval evals/bt-flywheel-harness/eval_harness.py
```

To run another coding harness instead of the scripted smoke runner, set `FLYWHEEL_HARNESS_RUNNER=command` and provide `FLYWHEEL_RUNNER_COMMAND`. The command template may use `{repo}`, `{prompt_file}`, `{skill_path}`, and `{scenario_id}`. The fake `bt` command remains on `PATH`, so the agent gets deterministic Braintrust responses while still editing and testing a real fixture repo.

```bash
FLYWHEEL_HARNESS_RUNNER=command \
FLYWHEEL_RUNNER_COMMAND='your-agent --workdir {repo} --prompt-file {prompt_file}' \
braintrust eval evals/bt-flywheel-harness/eval_harness.py
```

Set `FLYWHEEL_HARNESS_LLM_JUDGE=1` to add an optional LLM handoff-quality judge on top of the deterministic checks.
