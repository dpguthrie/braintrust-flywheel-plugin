# Demo: bt-flywheel Harbor Offline Eval

This demo shows a minimal Harbor-backed eval for `bt-flywheel` and how the same pattern maps to a developer-tooling team evaluating agent friendliness across harnesses, models, prompts, repos, and tool versions.

## What This Demo Proves

The current suite proves the core architecture:

1. `run.sh` materializes ordinary Harbor task directories for the selected bt-flywheel scenarios and variants.
2. It writes a native Harbor JobConfig and runs one `harbor run --config ...` command across the selected tasks, harnesses, and models.
3. Harbor owns sandboxed agent execution and trial concurrency.
4. Each Harbor task runs either with the real `bt-flywheel` skill injected or with the skill removed for a baseline comparison.
4. Braintrust project data is supplied by deterministic snapshots through a local `bt` CLI.
5. The local `bt` logs every command to `/logs/artifacts/bt-command-log.jsonl`.
6. The importer logs each Harbor trial as one Braintrust experiment row.
7. The importer converts Harbor result, `bt` commands, and optional ATIF trajectory steps into a normalized Braintrust trace.
8. The verifier checks the skill output contract, routing decision, process discipline, and side-effect safety.
9. Braintrust stores structured scores and metadata for comparison.

## Local Demo

From the repository root:

```bash
evals/bt-flywheel-harbor/run.sh
```

By default this:

- creates `evals/bt-flywheel-harbor/.venv` if needed
- loads a repo-root `.env` file when one exists
- installs or refreshes `evals/bt-flywheel-harbor/requirements.txt` only when needed
- installs Harbor into the eval venv from `requirements.txt`
- materializes generated Harbor task variants under `evals/bt-flywheel-harbor/.generated/`
- writes a Harbor job config
- runs `harbor run --config ...`
- imports the Harbor job results into Braintrust or writes a local import preview
- includes both `with-skill` and `no-skill` rows as generated Harbor tasks
- runs the enabled Codex and Claude Code targets from the bt-flywheel suite config
- runs up to 4 Harbor trials concurrently by default

This is intentionally Harbor-first. Braintrust does not parallelize agent
execution here; Harbor does. Braintrust receives one experiment row per Harbor
trial after the job finishes.

The default Codex target needs `OPENAI_API_KEY` in the shell or `.env`. The
default Claude Code target needs `ANTHROPIC_API_KEY` unless you use
`ANTHROPIC_AUTH_TOKEN` or `CLAUDE_CODE_OAUTH_TOKEN`. Gemini/Google targets need
`GOOGLE_API_KEY` or `GEMINI_API_KEY`. The eval passes provider credentials into
Harbor as env-var templates, for example
`--agent-env OPENAI_API_KEY=${OPENAI_API_KEY}`, so the recorded Harbor command
does not contain raw secret values.

The Claude Code target uses Harbor's built-in `claude-code` adapter. If you need
to test a custom harness adapter later, set `HARBOR_AGENT_IMPORT_PATH` for an ad
hoc run or add `agent_import_path` to a suite target. The default suite avoids
repo-local subclasses so Harbor remains the source of truth for agent support.

That is the intended abstraction boundary: this repo does not alter Harbor's
agent implementations or Braintrust's experiment model. It uses Harbor the way a
Harbor user would, then imports the completed Harbor job into Braintrust.

The bt-flywheel-specific filenames are configured in `suite_artifacts.py`.
Harbor only guarantees its own trial layout and the collected `artifacts/`
directory; this suite tells the importer that its optional summary, narrative,
and command log are named `bt-flywheel-summary.json`,
`bt-flywheel-narrative.md`, and `bt-command-log.jsonl`.

Run a single scenario:

```bash
HARBOR_SCENARIOS=healthy-exit evals/bt-flywheel-harbor/run.sh
```

Run only the skill-enabled rows:

```bash
HARBOR_SKILL_VARIANTS=with-skill evals/bt-flywheel-harbor/run.sh
```

Run only Codex:

```bash
HARBOR_TARGETS=codex-gpt-5.4 evals/bt-flywheel-harbor/run.sh
```

Run only Claude Code:

```bash
HARBOR_TARGETS=claude-code-sonnet-4-6 evals/bt-flywheel-harbor/run.sh
```

Compare the skill against the no-skill baseline for one scenario:

```bash
HARBOR_SCENARIOS=measurement-gap \
HARBOR_SKILL_VARIANTS=with-skill,no-skill \
evals/bt-flywheel-harbor/run.sh
```

Run a single ad hoc harness/model pair without editing the suite config:

```bash
HARBOR_AGENT=codex \
HARBOR_MODEL=openai/gpt-5.4 \
evals/bt-flywheel-harbor/run.sh
```

Run a single ad hoc Claude Code model:

```bash
HARBOR_AGENT=claude-code \
HARBOR_MODEL=anthropic/claude-sonnet-4-6 \
evals/bt-flywheel-harbor/run.sh
```

Upload to Braintrust:

```bash
UPLOAD=1 evals/bt-flywheel-harbor/run.sh
```

Control Harbor trial concurrency:

```bash
HARBOR_MAX_CONCURRENCY=2 evals/bt-flywheel-harbor/run.sh
```

## Suite Config And Harbor JobConfig

The bt-flywheel selection config lives at [`suite.toml`](suite.toml). It is
not a `braintrust-harbor` abstraction and it is not required by Harbor. It is a
small suite-local input that tells `run.sh` which Harbor tasks to generate
before writing a native Harbor JobConfig.

Current dimensions:

| Dimension | Current use | Generalized developer-tooling use |
|---|---|---|
| `scenarios` | `healthy-exit`, `measurement-gap`, `dataset-gap` | User prompts or task names such as `create-project`, `debug-deploy`, `migrate-config` |
| `skill_variants` | `with-skill`, `no-skill` | Tooling guidance present vs absent, or old prompt contract vs new prompt contract |
| `targets` | Harbor agent/model pairs such as `codex` + `openai/gpt-5.4` | Harness/model pairs such as Codex, Claude Code, Cursor, or custom harnesses |
| `conditions` | `braintrust-project-snapshot` condition | Tool versions, install methods, feature flags, or environment variants |
| `trace_mode` | `normalized` | Keep trace-level scorers stable across harness-specific tracing differences |

One `run.sh` invocation writes one Harbor JobConfig. When `UPLOAD=1`, that
Harbor job is imported as one Braintrust experiment, with one Braintrust row per
Harbor trial. `HARBOR_MAX_CONCURRENCY` maps to Harbor's
`n_concurrent_trials`; it does not control Braintrust worker count.

For `bt-flywheel`, the selection config is intentionally small:

```toml
[[targets]]
name = "codex-gpt-5.4"
agent = "codex"
models = ["openai/gpt-5.4"]
enabled = true

[[targets]]
name = "claude-code-sonnet-4-6"
agent = "claude-code"
models = ["anthropic/claude-sonnet-4-6"]
enabled = true
```

Custom Harbor agents still plug in through Harbor's normal import path:

```toml
[[targets]]
name = "my-agent-main"
agent = "my-agent"
agent_import_path = "my_eval_suite.harbor_agents:MyAgent"
models = ["openai/gpt-5.4"]
enabled = true
```

The `no-skill` rows are materialized as temporary Harbor task directories. They keep the same project snapshot and verifier, but remove `/skills/bt-flywheel` from the sandbox and rewrite the task prompt so the agent is not told to use the skill. Compare experiment results by `metadata.skill_variant` to estimate whether the skill adds value over the prompt-only baseline.

Braintrust row `input` is intentionally shaped like the user-facing agent session,
for example a `/bt-flywheel ...` prompt plus project context. Scenario, harness,
model, skill variant, Harbor paths, and other runner details live in metadata so
experiments group cleanly without making the input look like internal runner
configuration.

Each materialized task writes that row contract to `.agent-tooling-eval.json`.
The shared importer reads that neutral file; runner details stay in metadata so
the Braintrust row input mirrors a user-facing agent session.

## CI Demo

The workflow at [`.github/workflows/bt-flywheel-harbor-eval.yml`](../../.github/workflows/bt-flywheel-harbor-eval.yml) runs the same script on a schedule or manually.

It installs Python and `uv`, then calls:

```bash
evals/bt-flywheel-harbor/run.sh
```

Manual dispatch supports:

- scenario filtering
- target filtering
- skill variant filtering
- concurrency control
- upload on/off

The scheduled run uploads by default when `BRAINTRUST_API_KEY` is configured in repository secrets.
Agent harnesses also need their provider credentials. For the default Codex target,
set `OPENAI_API_KEY` in repository secrets.

## Braintrust Trace Shape

The primary scoring surface is a normalized trace imported from Harbor artifacts. Native Braintrust developer-tool integrations can still be useful, but they should be treated as sidecar traces or links unless they can be mapped back into this contract. That keeps score behavior comparable across Codex, Claude Code, Cursor, OpenCode, and future harnesses.

The Braintrust eval trace should show spans like:

```text
eval
  task
    harbor.trial
    bt.status
    bt.sql
    bt.trace_view
    agent.context
    agent.message
    agent.tool.<tool_name>
  <scorer name>
  <scorer name>
```

Each imported span includes `metadata.trace_schema = "harbor-normalized-trace/v1"` and a `metadata.normalized_kind`, such as `harness_run`, `command_log_entry`, `agent_context`, `agent_message`, or `agent_tool_call`. Trace-level scorers use that normalized surface rather than harness-native span names.

The `bt.*` spans are imported from the local CLI command log. The `agent.*` spans are imported from Harbor's ATIF trajectory artifact when the selected harness produces one. Agent turns with tool calls are represented as an `agent.message` LLM span plus one or more `agent.tool.<tool_name>` spans, so token metrics stay on the LLM span and tool observations stay on tool spans.

When Harbor provides usage data, the eval logs Braintrust metric fields such as `prompt_tokens`, `completion_tokens`, `tokens`, and `estimated_cost`. Claude Code currently emits per-step usage, so those metrics can appear on individual `agent.message` spans. Codex currently emits aggregate `final_metrics`, so the aggregate token/cost values are logged on `harbor.trial` and in `output.usage_metrics`.

## Scoring Model

The scoring set is intentionally split between task correctness and harness quality:

| Score | What it checks | Why it matters |
|---|---|---|
| `Harbor verifier reward` | Fixture verifier's aggregate reward | Keeps the Harbor task itself authoritative |
| `Harness reliability` | Harbor completion, loaded trial artifacts, reward presence, no infra error | Separates agent behavior failures from broken eval runs |
| `Normalized trace contract` | `harbor.*`, `bt.*`, and `agent.*` spans use the shared schema | Keeps cross-harness traces comparable |
| `Agent trace presence` | Agent/tool execution spans were imported when available | Makes missing harness trajectories visible |
| `Schema validity` | `bt-flywheel-summary.json` follows the contract | Ensures downstream automation can consume the handoff |
| `Route correctness` | Healthy, measurement-gap, and dataset-gap outcomes follow the expected route | Measures the skill's core decision quality |
| `Process discipline` / `Trace process discipline` | Evidence before changes and smoke before full eval | Rewards safe agent workflow, not just final text |
| `Evidence alignment` | Findings and verification are backed by trace/eval/dataset inspection | Penalizes unsupported recommendations |
| `Skill selection` | `with-skill` rows actually have skill evidence, and `no-skill` rows do not leak it | Supports skill-vs-baseline comparison |
| `Tool efficiency` | Bounded command count, low duplication, no unknown command loops | Captures tool-discovery minimality |
| `Runtime and cost efficiency` | Runtime, command count, and optional token/cost metrics | Treats cost as a scorer |
| `Side-effect safety` / `Blast radius safety` | No forbidden mutations, local code edits, or risky shell actions | Catches destructive tool use and excessive blast radius |

This maps to the PDF guidance that modern harness evals need to score the full workflow: starting world state, sandboxed execution, trace capture, tool selection, code-execution safety, cost, and the final artifact. This repo does not yet add memory or multi-session continuity scorers because the current `bt-flywheel` scenarios are single-session tasks.

## Mapping To A Developer-Tooling Benchmark

For a developer-tooling team, the eval row usually needs these dimensions:

```text
task prompt x optional repo x harness x model x guidance/tooling variant x tool version
```

The suite-local generation config could look like:

```toml
[[tasks]]
name = "create-project"
prompt = "Create a new Worker project that returns JSON from /health."
repo = ""

[[tasks]]
name = "debug-existing-project"
prompt = "Fix the failing deploy command in this repo."
repo = "https://github.com/org/example-app"

[[tool_versions]]
name = "latest"
install = "npm install -g wrangler@latest"

[[tool_versions]]
name = "baseline"
install = "npm install -g wrangler@4.16.0"

[[guidance_variants]]
name = "with-agent-docs"
install = "cp docs/agents.md AGENTS.md"

[[guidance_variants]]
name = "no-agent-docs"
install = ""

[[targets]]
name = "codex-gpt-5.4"
agent = "codex"
models = ["openai/gpt-5.4"]

[[targets]]
name = "claude-code-sonnet-4-6"
agent = "claude-code"
models = ["anthropic/claude-sonnet-4-6"]
```

The suite would materialize those combinations into ordinary Harbor tasks, then
run them with a normal Harbor JobConfig. Each task would:

- clones or creates the target repo inside the sandbox
- installs the selected tool version
- asks the selected harness/model to perform the user task
- verifies concrete outcomes, such as files created, commands succeeding, deploy dry-run success, errors diagnosed, or docs followed
- records artifacts and command logs

Braintrust metadata should include:

```json
{
  "task": "debug-existing-project",
  "harness": "codex",
  "model": "openai/gpt-5.4",
  "guidance_variant": "with-agent-docs",
  "tool": "wrangler",
  "tool_version": "latest"
}
```

That is what lets the team compare agent friendliness by model, harness, prompt/task, repo shape, guidance/tooling variant, and tool version over time.

## What This Repo Does Not Yet Include

This `bt-flywheel` suite does not yet implement:

- arbitrary user prompts as data rows
- optional git repo cloning per trial
- tool-version install dimensions
- Cursor, OpenCode, or custom harness targets
- multi-session continuity and harness memory regression tasks
- longitudinal regression dashboards beyond Braintrust experiment metadata

Those are the next layer for a general developer-tooling benchmark. The current suite is deliberately narrower: it proves the sandbox, harness/model row expansion, deterministic verifier, and Braintrust logging flow on a real skill.
