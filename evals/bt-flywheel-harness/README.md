# bt-flywheel Offline Harness

This harness evaluates whether `bt-flywheel` helps a coding agent diagnose and improve small Braintrust-style fixture repos.

Braintrust Eval is the primary evaluation surface. The local `unittest` file only checks harness plumbing such as fake `bt` routing and runner command construction.

For the broader evaluation thesis, current gaps, and recommended online-first direction, see [EVALUATION_STRATEGY.md](EVALUATION_STRATEGY.md).

It is intentionally offline by default:

- fixture repos provide the code under test
- scenario JSON files define expected behavior and fake Braintrust responses
- a fake `bt` CLI is placed on `PATH`
- the runner writes `bt-flywheel-summary.json` and `bt-flywheel-narrative.md`
- deterministic checks score the handoff, changed files, fake `bt` usage, and fixture acceptance tests

## Quick Start

Run the deterministic smoke runner:

```bash
python3 evals/bt-flywheel-harness/run_harness.py --runner scripted
```

Compare variants:

```bash
python3 evals/bt-flywheel-harness/run_harness.py \
  --runner scripted \
  --skill-variant none \
  --skill-variant current
```

Keep the generated temp workspaces for inspection:

```bash
python3 evals/bt-flywheel-harness/run_harness.py \
  --runner scripted \
  --keep-workspace \
  --json
```

## Claude Runner

Use Claude Code as the real agent runner:

```bash
python3 evals/bt-flywheel-harness/run_harness.py \
  --runner claude \
  --scenario agent_bug \
  --skill-variant current \
  --keep-workspace \
  --json
```

The harness invokes Claude Code in non-interactive mode with:

- `--print`
- `--bare`
- `--no-session-persistence`
- `--permission-mode bypassPermissions`
- `--add-dir <fixture repo>`
- `--add-dir <copied skill path>` when a skill variant is enabled

Environment knobs:

| Variable | Purpose |
|---|---|
| `FLYWHEEL_CLAUDE_BIN` | Claude binary name or path. Defaults to `claude`. |
| `FLYWHEEL_CLAUDE_MODEL` | Optional Claude model or alias, for example `sonnet`. |
| `FLYWHEEL_CLAUDE_MAX_BUDGET_USD` | Optional per-run budget guard. |
| `FLYWHEEL_CLAUDE_OUTPUT_FORMAT` | Claude output format. Defaults to `text`. |
| `FLYWHEEL_CLAUDE_PERMISSION_MODE` | Permission mode. Defaults to `bypassPermissions`. |
| `FLYWHEEL_CLAUDE_EXTRA_ARGS` | Extra Claude CLI args parsed with shell-style splitting. |

Run through Braintrust:

```bash
FLYWHEEL_HARNESS_RUNNER=claude \
BRAINTRUST_API_KEY=... \
braintrust eval evals/bt-flywheel-harness/eval_harness.py
```

## Generic Command Runner

Use `runner=command` for another agent CLI:

```bash
FLYWHEEL_RUNNER_COMMAND='your-agent --workdir {repo} --prompt-file {prompt_file}' \
python3 evals/bt-flywheel-harness/run_harness.py --runner command
```

Available template variables:

- `{repo}`
- `{prompt_file}`
- `{prompt}`
- `{skill_path}`
- `{scenario_id}`

## Scenarios

Current scenarios:

- `measurement_gap`: repeated citation failures require measurement before agent changes
- `agent_bug`: low math scores require a targeted prompt/code fix
- `blocked_no_convergence`: repeated failed iterations should exit with an investigation handoff

Each scenario has:

- `task`: the prompt context
- `bt.routes`: fake `bt` responses
- `acceptance`: commands run after the agent exits
- `expected`: outcome, required terms, required `bt` commands, and change policy

## What This Does Not Prove Yet

This is a useful harness foundation, not yet a compelling proof that Braintrust evaluates skills well. See [EVALUATION_STRATEGY.md](EVALUATION_STRATEGY.md) for the full gap list and proposed next architecture.

The largest gaps:

- The scripted runner is a harness smoke test, not an agent eval. It proves the checks work, not that the skill helps.
- The fixture repos are tiny. They do not reflect large repos, messy histories, real dependency failures, or ambiguous product constraints.
- The fake `bt` shim is hand-authored. It does not yet replay real Braintrust projects or test whether SQL/search queries are semantically good.
- Deterministic checks are partly term-based and can be gamed by summaries that mention expected words without doing deep diagnosis.
- Full Claude transcripts are not parsed into first-class trace events yet. The harness captures stdout/stderr, changed files, and fake `bt` commands, but not a rich tool-call trace.
- The bundled handoff JSON Schema is not yet used for validation; the harness has a lightweight structural check.
- The optional LLM judge is available behind `FLYWHEEL_HARNESS_LLM_JUDGE=1`, but it is not calibrated against human labels.
- There is no repeated-run flakiness measurement, statistical comparison, cost tracking, or token accounting.
- `none` vs `current` is meaningful only with a real agent runner. With `scripted`, both variants execute the same canned behavior.
- This evaluates skill execution in fixture repos. It does not yet evaluate live production Braintrust projects, real project auth, or real `bt` CLI behavior.

The next quality jump should be real-run evidence: run Claude on the current scenarios, add transcript capture, validate against the actual summary schema, and add fixture scenarios that are difficult enough for `none` to fail.
