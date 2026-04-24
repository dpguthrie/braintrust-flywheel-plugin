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
/plugin marketplace add dpguthrie/bt-flywheel
/plugin install bt-flywheel@bt-flywheel
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

---

## GitHub Action

A reusable GitHub Actions workflow is included so you can run the flywheel on a schedule or on-demand without any boilerplate.

Copy `examples/flywheel-caller.yml` to `.github/workflows/flywheel.yml` in your repo and fill in the inputs:

```yaml
jobs:
  flywheel:
    uses: dpguthrie/flywheel-plugin/.github/workflows/bt-flywheel.yml@main
    with:
      project_name: my-braintrust-project
      system_context: |
        Describe your agent here...
      code_paths: src/ evals/ scorers.py
      extra_env: |
        OPENAI_API_KEY=${{ secrets.OPENAI_API_KEY }}
    secrets: inherit
```

Required secrets in your repo: `ANTHROPIC_API_KEY`, `BRAINTRUST_API_KEY`.

See [`examples/flywheel-caller.yml`](examples/flywheel-caller.yml) for the full annotated example.

---

## Flywheel Quality Scorers

The `scorers/` directory contains six Braintrust online scorers that evaluate the quality of the flywheel's own execution — i.e., whether Claude Code is following the flywheel methodology correctly when it runs as your CI agent.

These are not scorers for your downstream task agent. They score the flywheel Claude Code session itself, catching things like:

| Scorer | What it catches |
|---|---|
| Evidence Before Change | Claude editing code without first running `bt sql` or `bt view` |
| Smoke Test Discipline | Running a full eval without a smoke run first |
| Run Efficiency | Duplicate Bash commands or unnecessary credential-seeking calls |
| Narrative Specificity | Run summaries that are vague ("improved performance") instead of specific (exact deltas, trace links) |
| Diagnostic Coherence | Code changes that aren't motivated by the actual findings |
| Claimed vs Actual | Summary claiming changes that don't match the actual Edit/Write spans |

### Deploying the scorers

Install dependencies and push once to register them in the Braintrust project where your Claude Code traces are logged:

```bash
pip install -r scorers/requirements.txt

BRAINTRUST_API_KEY=... \
BRAINTRUST_CC_PROJECT=my-agent-claude-code \
FLYWHEEL_CODE_PATHS="src/|evals/|scorers\.py" \
bt functions push --language python \
  --requirements scorers/requirements.txt \
  --if-exists replace \
  scorers/flywheel_scorers.py
```

Re-run any time you want to push updated scorer logic.

`FLYWHEEL_CODE_PATHS` scopes edit-tracking scorers to your source files. Leave it empty to match all Edit/Write spans.

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

Tests whether the LLM judge correctly rates flywheel behavior against 10 synthetic scenarios: 5 positive examples (good behavior to rate A/B) and 5 negative examples (specific failure modes to rate C/D):

| Tag | Scenario | Expected rating |
|---|---|---|
| `healthy-exit` | Healthy production → exits early, no changes | A/B |
| `broken-scorer` | Bimodal distribution → updates scorer | A/B |
| `dataset-gap` | New query patterns → adds examples | A/B |
| `agent-bug-fixed` | Low scores on query type → targeted prompt fix | A/B |
| `no-convergence` | 3 iterations, no improvement → graceful exit | A/B |
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
