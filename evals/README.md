# Offline Evals

This directory contains offline evals for validating Braintrust skills.

For the reusable Harbor-first bridge used by the Harbor suite, see the
`braintrust-harbor` package.

Concrete suites, such as `evals/bt-flywheel-harbor/`, own their task generation,
fixtures, fake/live service adapters, verifiers, and domain-specific scorers.

## bt-flywheel Docker Suite

`evals/bt-flywheel-docker/eval_subprocess.py` is the minimal Braintrust-native version of the same skill-vs-no-skill question. It runs inside Docker through `bt eval` and treats each row as a Claude Code subprocess invocation:

```json
{
  "command": ["claude", "--print", "--dangerously-skip-permissions", "--output-format", "json", "--model", "{model}", "--no-session-persistence", "{prompt}"],
  "prompt": "/bt-flywheel help me improve my agent...",
  "env_vars": {
    "BT_FLYWHEEL_FIXTURE_SCENARIO": "healthy-exit"
  }
}
```

Run locally without upload:

```bash
evals/bt-flywheel-docker/run_docker.sh
```

Upload a run:

```bash
UPLOAD=1 evals/bt-flywheel-docker/run_docker.sh
```

Inside the container, the command is still:

```bash
bt eval --runner python3 evals/bt-flywheel-docker/eval_subprocess.py
```

The Docker image installs `bt`, Claude Code, and Braintrust's `trace-claude-code` plugin. When upload/tracing is enabled, the eval passes `CC_PARENT_SPAN_ID`, `CC_ROOT_SPAN_ID`, and `CC_EXPERIMENT_ID` into the subprocess environment so Claude plugin traces attach under the Braintrust eval row.

Braintrust owns task concurrency through `Eval(max_concurrency=...)`. The Docker suite does not provide Harbor's built-in coding-agent adapters; it is useful as a small, direct containerized subprocess baseline.

The default Docker-suite Claude Code model is `claude-sonnet-4-6`. Set
`BT_FLYWHEEL_DOCKER_MODEL` to a different Claude Code model name or alias when
needed.

## bt-flywheel Harbor Suite

`evals/bt-flywheel-harbor/run_harbor_batch.py` runs a small Harbor-backed task suite for the `bt-flywheel` skill. One Harbor job is one Braintrust experiment: Harbor launches the coding-agent trials with its own `n_concurrent_trials`, and the importer logs each Harbor trial back to Braintrust as one experiment row with normalized traces, verifier rewards, scores, metadata, and artifacts.

Default scenarios:

| Scenario | Expected route |
|---|---|
| `healthy-exit` | Exit with `outcome=healthy` and `next_steps[0].intent=no_action` |
| `measurement-gap` | Route to measurement/scorer work before agent changes |
| `dataset-gap` | Add/propose curated dataset rows and run smoke before full eval |

Run one Harbor task directly:

```bash
uv tool install harbor

harbor run -p evals/bt-flywheel-harbor/harbor/tasks/healthy-exit -a codex -m "${HARBOR_MODEL:-openai/gpt-5.4}"
```

Run the Braintrust eval locally without upload:

```bash
evals/bt-flywheel-harbor/run.sh
```

`run.sh` loads a repo-root `.env` file by default when one exists. The default
Codex target requires `OPENAI_API_KEY`, and the default Claude Code target
requires `ANTHROPIC_API_KEY` unless you use `ANTHROPIC_AUTH_TOKEN` or
`CLAUDE_CODE_OAUTH_TOKEN`. The runner passes provider credentials to Harbor as
`--agent-env KEY=${KEY}` templates so command logs do not include raw secret
values.

The Claude Code target uses Harbor's built-in `claude-code` adapter. Keep
custom agent adapters explicit by setting `HARBOR_AGENT_IMPORT_PATH` or
`agent_import_path` in the bt-flywheel suite config only when you are testing an adapter Harbor
does not already provide.

The eval runner does not modify Harbor or Braintrust internals. It uses Harbor
for agents, sandboxes, concurrency, and verifier rewards, then imports the
resulting job artifacts into Braintrust as experiment rows, traces, scores, and
metadata.

The bt-flywheel artifact names are configured in
`evals/bt-flywheel-harbor/suite_artifacts.py`. Harbor does not know about
`bt-flywheel-summary.json`, `bt-flywheel-narrative.md`, or
`bt-command-log.jsonl`; those are suite conventions layered on top of Harbor's
standard `artifacts/` and `verifier/reward.json` outputs.

The script creates `evals/bt-flywheel-harbor/.venv` once and installs both Python
library dependencies and the Harbor CLI from `requirements.txt`, preferring
`uv pip install` when `uv` is available. Later runs skip dependency installation
unless `requirements.txt` changes. Set `FORCE_PYTHON_INSTALL=1` to refresh
dependencies explicitly.

Braintrust row inputs are the user-facing session prompts. Scenario names,
harness/model pairs, skill variants, Harbor task paths, and runner details are
stored in row metadata for filtering and grouping. The materialized Harbor task
stores that row contract in `.agent-tooling-eval.json`.

`run.sh` materializes local Harbor task directories for the selected
bt-flywheel scenarios/variants, writes a native Harbor JobConfig, runs one
`harbor run --config ...` command, and then imports the resulting Harbor job
directory into Braintrust. `HARBOR_MAX_CONCURRENCY` maps to Harbor's
`n_concurrent_trials`, so Harbor owns parallel agent execution.

When `UPLOAD=0`, the importer writes `braintrust-import-preview.json` into the
Harbor job directory instead of sending rows to Braintrust. When `UPLOAD=1`, it
creates one Braintrust experiment named after the Harbor job unless
`BRAINTRUST_EXPERIMENT_NAME` is set.

Scoring covers both task correctness and harness quality:

| Category | Scores |
|---|---|
| Task result | `Harbor verifier reward`, `Schema validity`, `Route correctness` |
| Workflow discipline | `Process discipline`, `Trace process discipline`, `Evidence alignment` |
| Trace quality | `Normalized trace contract`, `Agent trace presence` |
| Harness quality | `Harness reliability`, `Tool efficiency`, `Runtime and cost efficiency` |
| Variant comparison | `Skill selection` for `with-skill` vs `no-skill` rows |
| Safety | `Side-effect safety`, `Blast radius safety` |

Run a subset:

```bash
HARBOR_SCENARIOS=healthy-exit,dataset-gap evals/bt-flywheel-harbor/run.sh
```

Run only the skill-enabled rows:

```bash
HARBOR_SKILL_VARIANTS=with-skill evals/bt-flywheel-harbor/run.sh
```

Run only one harness target:

```bash
HARBOR_TARGETS=codex-gpt-5.4 evals/bt-flywheel-harbor/run.sh
HARBOR_TARGETS=claude-code-sonnet-4-6 evals/bt-flywheel-harbor/run.sh
```

Run only the skill baseline comparison for one scenario:

```bash
HARBOR_SCENARIOS=measurement-gap HARBOR_SKILL_VARIANTS=with-skill,no-skill evals/bt-flywheel-harbor/run.sh
```

Upload a stable run:

```bash
UPLOAD=1 evals/bt-flywheel-harbor/run.sh
```

Useful environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `HARBOR_AGENT` | `codex` | Harbor agent name, for example `codex` or `claude-code` |
| `HARBOR_MODEL` | `openai/gpt-5.4` | Harbor model identifier, for example `openai/gpt-5.4` or `anthropic/claude-sonnet-4-6` |
| `HARBOR_SCENARIOS` | all default scenarios | Comma-separated scenario filter |
| `HARBOR_TARGETS` | enabled targets in the bt-flywheel suite config | Comma-separated target-name filter |
| `HARBOR_SKILL_VARIANTS` | enabled bt-flywheel task variants | Comma-separated skill variant filter: `with-skill`, `no-skill` |
| `HARBOR_MAX_CONCURRENCY` | `4` | Harbor trial concurrency for the single job |
| `HARBOR_BIN` | `harbor` | Harbor executable |
| `HARBOR_JOBS_DIR` | `jobs` | Directory where Harbor writes job output |
| `HARBOR_EXTRA_ARGS` | empty | Extra flags passed to `harbor run` |
| `HARBOR_AGENT_ENV_KEYS` | inferred from agent/model | Comma-separated provider env vars to pass to Harbor as templates |
| `HARBOR_TRACE_MODE` | `normalized` | Import Harbor artifacts into a stable Braintrust span contract; set `off` to disable |
| `HARBOR_AGENT_IMPORT_PATH` | unset | Custom Harbor agent import path for ad hoc `HARBOR_AGENT` runs |
| `HARBOR_SCORE_GOOD_SECONDS` / `HARBOR_SCORE_MAX_SECONDS` | `600` / `1800` | Runtime budget for the cost-efficiency scorer |
| `HARBOR_SCORE_GOOD_BT_COMMANDS` / `HARBOR_SCORE_MAX_BT_COMMANDS` | `15` / `50` | `bt` command budget for tool and cost-efficiency scorers |
| `HARBOR_SCORE_GOOD_TOOL_CALLS` / `HARBOR_SCORE_MAX_TOOL_CALLS` | `35` / `90` | Agent tool-call budget when trajectory data is available |
| `UPLOAD` | `0` | Set to `1` to upload the Braintrust experiment |
| `BRAINTRUST_EVAL_PROJECT` | `bt-flywheel` | Braintrust project for eval upload |
| `OPENAI_API_KEY` | unset | Required by Harbor's default Codex target |
| `ANTHROPIC_API_KEY` | unset | Required by Harbor's default Claude Code target, unless using `ANTHROPIC_AUTH_TOKEN` or `CLAUDE_CODE_OAUTH_TOKEN` |
| `GOOGLE_API_KEY` / `GEMINI_API_KEY` | unset | Required when enabling Gemini/Google model targets |

To use a custom Harbor agent adapter, keep it in your suite or package and point
the bt-flywheel suite config at it:

```toml
[[targets]]
name = "my-agent-main"
agent = "my-agent"
agent_import_path = "my_eval_suite.harbor_agents:MyAgent"
models = ["openai/gpt-5.4"]
enabled = true
```

For an ad hoc run, use:

```bash
HARBOR_AGENT=my-agent \
HARBOR_AGENT_IMPORT_PATH=my_eval_suite.harbor_agents:MyAgent \
HARBOR_MODEL=openai/gpt-5.4 \
evals/bt-flywheel-harbor/run.sh
```

To add a scenario:

1. Copy one task under `evals/bt-flywheel-harbor/harbor/tasks/<new-scenario>/`.
2. Update `environment/fixtures/scenario.json` with deterministic Braintrust project data and expected route metadata.
3. Keep `environment/skills/bt-flywheel/` synchronized with the current skill bundle.
4. Add or adjust the oracle `solution/solve.sh`.
5. Extend the verifier only when the new route requires a new general criterion.
6. Add the scenario name to `evals/bt-flywheel-harbor/suite.toml` when it should run by default.

See [`bt-flywheel-harbor/DEMO.md`](bt-flywheel-harbor/DEMO.md) for the local/CI demo and how this maps to a broader developer-tooling benchmark.
