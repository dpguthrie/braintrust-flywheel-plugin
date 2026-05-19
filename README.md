# Braintrust Skills

A collection of agent skills for working with [Braintrust](https://braintrust.dev) through the `bt` CLI and repository-local coding-agent workflows.

## Available Skills

| Skill | Purpose |
|---|---|
| `bt-flywheel` | Continuously improve Braintrust-backed AI agents by mining traces, updating measurement/datasets/code/instrumentation, running evals, and emitting portable exit handoffs. |
| `bt-cost-optimizer` | Analyze Braintrust logs, scorers, Topics, Gateway/provider spend, datasets, and experiments to recommend safe cost optimizations. |
| `bt-instrumentation-doctor` | Review a project's traces and the surrounding codebase, then emit a prioritized plan for fixing trace structure, scorer scope, Thread view setup, payload shape, and tracing cost. |

Install each skill by copying or installing the full directory under `skills/<skill-name>/`; references, scripts, and agent metadata are part of the skill.

## Repository Layout

```text
skills/<skill-name>/        Installable skill bundles. SKILL.md is the canonical per-skill entrypoint.
examples/<skill-name>/      Copyable runner and integration examples.
evals/<skill-name>/         Offline evals for validating a skill's behavior.
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
| Harbor offline evals | Experimental | Deterministic Braintrust project snapshots validate skill routing and handoff quality in sandboxed coding-agent runs |
| Braintrust subprocess evals | Experimental | Minimal `Eval(...)` suite compares with-skill vs no-skill subprocess runs without Harbor |

## bt-cost-optimizer

`bt-cost-optimizer` helps a coding agent answer: "What Braintrust usage is driving cost, what can the `bt` CLI prove from data, and how should we safely change logging, scoring, Topics, Gateway usage, datasets, or experiments?"

The skill:

- Uses `bt status`, `bt projects`, `bt sql`, and `bt view` to collect bounded evidence from Braintrust.
- Uses `bt scorers` and `bt topics` to inspect scorer inventory and Topics status/config where available.
- Runs a local analyzer over exported rows to rank high-byte fields, largest traces, scorer spans, LLM token usage, and `JSONAttachment` candidates.
- Inspects local code for Braintrust logging, scorer, and Gateway patterns and maps sample findings back to instrumentation.
- Produces `bt-cost-optimization-report.md` and optionally `bt-cost-optimization-summary.json`.

The skill distinguishes measured findings from advisory recommendations. `bt` can measure sampled rows, scorer spans, token totals, and Topics config/status; exact bill totals, negotiated pricing, retention policy, and Gateway cache/routing config may require billing/UI or code/config context.

## bt-instrumentation-doctor

`bt-instrumentation-doctor` answers: "Is my Braintrust tracing healthy, and what concrete changes should I make in my codebase to improve it?"

The skill:

- Resolves project context via `bt status` / `.bt/config.json` and pulls bounded span and trace samples with `bt sql` and `bt view trace`.
- Fetches online scorer automations via the REST `/v1/project_score` endpoint and surfaces scope/sampling/filter issues.
- Cross-references the customer's codebase (Python, TypeScript/JavaScript, Go) to tie each finding to a specific file and line.
- Runs a local analyzer over exported spans/traces to flag empty root I/O, anonymous span names, missing model/token metrics, scorer-span dominance, duplicate parent/child payloads, oversized fields, deep traces, and conversations fragmented across roots.
- Emits `bt-tracing-plan.md` (prioritized, finding-by-finding) and `bt-tracing-summary.json` (machine-readable) so downstream automation can route the plan into review, issues, or a follow-up `bt-flywheel` run.

Scope boundary with the other skills:

- For deeper byte/scorer accounting on a single account, route to `bt-cost-optimizer`.
- For the full Discover → Diagnose → Improve → Verify loop after the plan is shipped, route to `bt-flywheel`.

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

python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo dpguthrie/braintrust-skills \
  --path skills/bt-instrumentation-doctor
```

For project-local CI or another agent harness, copy the full skill directory into the runner's skill path:

```bash
mkdir -p .agent-skills
curl -fsSL https://github.com/dpguthrie/braintrust-skills/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=2 -C .agent-skills braintrust-skills-main/skills/bt-flywheel

curl -fsSL https://github.com/dpguthrie/braintrust-skills/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=2 -C .agent-skills braintrust-skills-main/skills/bt-cost-optimizer

curl -fsSL https://github.com/dpguthrie/braintrust-skills/archive/refs/heads/main.tar.gz \
  | tar -xz --strip-components=2 -C .agent-skills braintrust-skills-main/skills/bt-instrumentation-doctor
```

For Claude Code (and most other agents), use `npx skills`:

```bash
npx skills add dpguthrie/braintrust-skills@bt-flywheel -g -y
npx skills add dpguthrie/braintrust-skills@bt-cost-optimizer -g -y
npx skills add dpguthrie/braintrust-skills@bt-instrumentation-doctor -g -y
```

## Usage

Once installed, invoke the skill directly if your agent supports skills:

```
/bt-flywheel
/bt-cost-optimizer
/bt-instrumentation-doctor
```

Or ask any coding agent to run the skill from the skill path:

> "Use `skills/bt-flywheel/SKILL.md` or `.agent-skills/bt-flywheel/SKILL.md` to improve my Braintrust-backed agent."

For ingest optimization:

> "Use `skills/bt-cost-optimizer/SKILL.md` or `.agent-skills/bt-cost-optimizer/SKILL.md` to analyze my Braintrust usage costs and recommend safe optimizations."

## Common Requirements

- [`bt` CLI](https://github.com/braintrustdata/bt) installed and authenticated
- A Braintrust project with logs, experiments, or datasets to inspect
- (Optional) `.bt/config.json` configured via `bt setup` for zero-config project resolution
- (For offline skill evals) Docker available; `evals/bt-flywheel-harbor/run.sh` installs Harbor into its eval venv, and `evals/bt-flywheel-docker/run_docker.sh` builds the minimal Docker subprocess image

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

## Offline Evals

There are two primary bt-flywheel eval paths:

| Suite | Use when |
|---|---|
| `evals/bt-flywheel-harbor/` | You want Harbor to own sandboxed coding-agent execution, native agent adapters, job artifacts, and trial concurrency, then import the job into Braintrust. |
| `evals/bt-flywheel-docker/` | You want a minimal Docker image that runs `bt eval ...` directly while keeping the task as a subprocess. |

Run the simple Docker subprocess suite:

```bash
UPLOAD=1 evals/bt-flywheel-docker/run_docker.sh
```

Inside the container, the command is still:

```bash
bt eval --runner python3 evals/bt-flywheel-docker/eval_subprocess.py
```

The Docker subprocess suite defaults to Claude Code:

```json
["claude", "--print", "--dangerously-skip-permissions", "--output-format", "json", "--model", "{model}", "--no-session-persistence", "{prompt}"]
```

For Claude Code tracing, the Docker image installs Braintrust's Claude Code tracing plugin and the eval passes `CC_PARENT_SPAN_ID`, `CC_ROOT_SPAN_ID`, and `CC_EXPERIMENT_ID` into the subprocess environment.

The `evals/bt-flywheel-harbor/` directory contains a Harbor-backed Braintrust offline eval for measuring the flywheel skill itself. One Harbor job is treated as one Braintrust experiment: Harbor runs the sandboxed coding-agent trials with its own concurrency, and the importer logs each Harbor trial back to Braintrust as an experiment row with normalized traces, scores, metadata, and artifacts.

Reusable Harbor/Braintrust glue comes from the `braintrust-harbor` PyPI package. The bt-flywheel suite owns its task materialization, fake Braintrust fixtures, verifiers, and skill-specific scorers under `evals/bt-flywheel-harbor/`.

Default scenarios:

| Scenario | Expected behavior |
|---|---|
| `healthy-exit` | Production metrics are healthy, so the flywheel exits with `outcome=healthy` and `next_steps[0].intent=no_action`. |
| `measurement-gap` | Traces show a repeated failure mode not captured by scores, so the flywheel routes to measurement/scorer work before agent changes. |
| `dataset-gap` | Production contains a pattern absent from eval data, so the flywheel curates dataset rows and runs smoke before full eval. |

Braintrust scores cover the verifier reward, schema validity, route correctness, process discipline, normalized trace quality, evidence alignment, skill selection, tool efficiency, runtime/cost, and blast-radius safety. Use `metadata.skill_variant`, `metadata.agent`, `metadata.model`, and `metadata.target` to compare with-skill vs no-skill baselines across harnesses.

Run a single Harbor task directly:

```bash
uv tool install harbor

harbor run -p evals/bt-flywheel-harbor/harbor/tasks/healthy-exit -a codex -m "${HARBOR_MODEL:-openai/gpt-5.4}"
```

Run the Braintrust eval locally without upload:

```bash
evals/bt-flywheel-harbor/run.sh
```

Upload results when stable:

```bash
UPLOAD=1 evals/bt-flywheel-harbor/run.sh
```

Useful knobs:

| Variable | Purpose |
|---|---|
| `HARBOR_SCENARIOS=healthy-exit,dataset-gap` | Run a subset of scenarios |
| `HARBOR_TARGETS=codex-gpt-5.4` | Run selected targets from the bt-flywheel suite config |
| `HARBOR_TARGETS=claude-code-sonnet-4-6` | Run only the Claude Code target |
| `HARBOR_MAX_CONCURRENCY=4` | Control Harbor trial concurrency |
| `HARBOR_AGENT=codex` | Select the Harbor agent, for example `codex` or `claude-code` |
| `HARBOR_MODEL=openai/gpt-5.4` | Select the model passed to Harbor, for example `openai/gpt-5.4` or `anthropic/claude-sonnet-4-6` |
| `HARBOR_EXTRA_ARGS="..."` | Pass additional flags to `harbor run` |
| `UPLOAD=1` | Upload the run to Braintrust instead of local-only mode |
| `BRAINTRUST_EVAL_PROJECT=bt-flywheel` | Select the Braintrust eval project |

See [`evals/README.md`](evals/README.md) for the task layout and [`evals/bt-flywheel-harbor/DEMO.md`](evals/bt-flywheel-harbor/DEMO.md) for the local/CI demo and developer-tooling mapping.
