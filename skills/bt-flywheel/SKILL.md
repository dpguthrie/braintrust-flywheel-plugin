---
name: bt-flywheel
description: Improve Braintrust-backed AI agents through an evidence-backed loop over production traces, measurement, datasets, code changes, evals, and portable exit handoffs. Use when starting an agent-improvement session, running CI/scheduled/post-deploy flywheels, investigating production score degradation, finding eval coverage gaps, or deciding whether to add/update scorers, datasets, instrumentation, or agent behavior.
---

# Braintrust Agent Improvement Flywheel

Five-phase cycle: Orient → Discover → Diagnose → Improve → Verify & Decide. On exit, write a portable handoff contract for the caller; do not execute external side effects.

## The Four Artifacts

Every phase can surface the need to change any of these:

| Artifact | Where it lives | How to change |
|---|---|---|
| **Agent** | Customer codebase (code files) | Code edits |
| **Measurement** | Braintrust scorers/facets/classifiers or codebase | `bt functions push` or code edit |
| **Datasets** | Braintrust | `bt datasets create/update/view/list` |
| **Instrumentation** | Customer codebase/logging config | Code edits |

## Operating Principles

- Gather evidence before edits. Use production traces, eval runs, scorer behavior, and local code context to form hypotheses before changing any artifact.
- Treat query examples as starting points, not a checklist. Discovery should adapt to the project schema, goal, traffic, recent changes, user reports, and surprising rows.
- Treat measurement as part of the system. If a repeated failure mode is not visible in scores, tags, facets, datasets, or evals, route to a new or updated scorer/classifier/facet before optimizing blindly.
- Prefer the smallest targeted change that the evidence supports. Avoid unrelated refactors, broad prompt rewrites, and dataset churn.
- Keep self-improvement bounded: smoke test before full evals, cap loops, log decisions, and leave external side effects to the caller.

## Reference Files

Load these when executing the relevant phase:

- `references/bt-sql-patterns.md` — SQL query templates for Discover and Verify & Decide
- `references/bt-view-patterns.md` — `bt view` command patterns
- `references/bt-eval-patterns.md` — eval invocation patterns
- `references/bt-functions-patterns.md` — scorer, prompt, and dataset CLI patterns
- `references/bt-sync-patterns.md` — bulk log/experiment/dataset sync (pull/push)
- `references/bt-topics-patterns.md` — Topics automation (input clustering, classification)
- `scripts/bt-curate-patterns.py` — ground truth labeling, split assignment, dataset row construction/upsert
- `references/bt-flywheel-output-templates.md` — `bt-flywheel-summary.json` handoff and `bt-flywheel-narrative.md` templates

## Detecting Interaction Mode

Before starting, check for autonomous mode signals in order:

1. Explicit flag: `mode: autonomous` in the invocation
2. `CI=true` environment variable
3. `FLYWHEEL_AUTONOMOUS=true` environment variable
4. Stdin is not a TTY (non-interactive shell context)

If any signal is present: **autonomous mode** — suppress all gates, log all decisions, write `bt-flywheel-summary.json` and `bt-flywheel-narrative.md` on exit.

Otherwise: **interactive mode** — present plans before irreversible actions and wait for confirmation.

## Phase 1: Orient

Establish session context before running any queries.

**Step 1 — Resolve the active project (never ask the user for a project ID):**

Check in this order:
1. `.bt/config.json` in the working directory — written by `bt setup`, contains `project` (name) and/or `project_id`
2. Agent/project instruction files in the project root — `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, `.github/copilot-instructions.md`, or similar files may document project name, ID, score columns, eval paths, dataset names
3. `bt projects list --json` — resolve name → ID programmatically

```bash
# Check local bt config
cat .bt/config.json 2>/dev/null

# If project name is known but ID is not:
bt projects list --json
# Find the entry where "name" matches → use its "id"

# If nothing is configured, list for user to choose by name:
bt projects list
```

If `.bt/config.json` is absent, suggest: "Run `bt setup` in this directory to configure the active project — it stores `project` and `project_id` in `.bt/config.json` so every `bt` command automatically targets the right project."

**Step 2 — Establish goal:**

**In interactive mode**, ask: What metric or behavior to improve? (default if skipped: "general health check")

**In autonomous mode**, read from `FLYWHEEL_GOAL` env var (fallback: "general health check").

**Step 3 — Resolve baseline experiment (never ask the user for an experiment ID):**

Check in this order:
1. `FLYWHEEL_BASELINE_EXPERIMENT` env var
2. Recent `bt eval` output in this session — the experiment ID is printed on completion
3. List recent experiments via CLI and pick automatically (autonomous) or present for selection (interactive):

```bash
bt experiments list --json -p <project-name>
# Returns objects with: id, name, created
# Sort by created descending; use the most recent as baseline
```

**Schema Discovery** (always run after project ID is resolved):

Check project instruction files first for:
- Score column names (e.g., `scores."Response Quality"`)
- Facet column names
- Eval file paths
- Dataset names

If not documented there, run schema introspection using the resolved `<PROJECT_ID>` with progressive time window expansion:

```bash
# Try 1 day
bt sql "SELECT * FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND created >= NOW() - INTERVAL 1 day LIMIT 1"
# If no results, try 7 days
bt sql "SELECT * FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND created >= NOW() - INTERVAL 7 day LIMIT 1"
# If still no results, try 30 days
bt sql "SELECT * FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND created >= NOW() - INTERVAL 30 day LIMIT 1"
```

Inspect the returned row to identify `scores.*` and `facets.*` column names. Null values for nested fields still reveal the column name structure.

If no rows found after 30 days: note this and proceed with generic queries.

Store all discovered column names and the resolved project ID for use in subsequent phases.

**Resolve app URL and org slug** (needed to construct Braintrust links in the summary):

```bash
bt status --json
# Returns: { "org": "<org-name>", ... }
```

Braintrust URLs (URL-encode spaces as `%20`):
- Experiment: `https://www.braintrust.dev/app/<org>/p/<project-name>/experiments/<experiment-id>`
- Trace: `https://www.braintrust.dev/app/<org>/p/<project-name>/r/<trace-id>`

## Phase 2: Discover

Mine production traces for patterns the agent has not been evaluated on. The goal is a truthful map of production behavior, not merely running prewritten queries.

Load `references/bt-sql-patterns.md`; use its examples for Braintrust SQL syntax, data shapes, `search()`, `MATCH`, `ANY_SPAN()`, score unpivoting, and aggregation patterns. Load `references/bt-topics-patterns.md` if Topics or facets are available. Use a 7-day window by default, expand for low traffic, and always keep `project_logs()` queries bounded by time/range or specific IDs.

Run discovery as an iterative hypothesis loop:

1. Start broad: traffic volume, error rate, score coverage/distribution, latency/cost, tags/facets/topics, tool/handoff patterns, and recent model/prompt/deploy metadata.
2. Generate follow-up queries from the goal, recent changes, schema fields, user complaints, surprising aggregates, and trace-level evidence. Do not stop after the canned examples if the data suggests another direction.
3. Use text search when the suspected pattern is lexical or buried in free-form fields. Seed `search('<term>')` or field-level `MATCH` terms from error messages, tool names, refusals, user language, output-format failures, policy words, domain concepts, or newly observed failure labels.
4. Segment results by dimensions that could explain variance: model, prompt/version, route, tool, user/customer segment, topic/facet/classification, tag, environment, hour/day, deployment marker, and eval dataset split.
5. Compare cohorts rather than only reading outliers: failing vs. passing, recent vs. older windows, high-cost vs. normal, production vs. baseline experiment, and represented vs. missing dataset clusters.
6. Drill into both representative and extreme traces. Load `references/bt-view-patterns.md` and inspect full span trees before attributing root cause.
7. Keep a running list of missing measurements. If a repeated failure mode is not captured by an existing score, tag, facet, or dataset field, carry it into Diagnose as a measurement gap.

Explore evidence planes including reliability, quality, coverage, behavior/tooling, performance/cost, change correlation, and eval alignment.

Before Diagnose, write findings with enough detail to support or reject root causes:

```text
DISCOVER FINDINGS:
- Window and traffic: <time range>, <N traces/spans>, low-traffic caveats
- Strongest signals: <aggregate/statistic> with query/trace evidence
- Failure modes: <specific behavior>, example trace IDs/URLs, affected cohorts
- Healthy cohorts: <what works>, so fixes stay targeted
- Production vs eval gaps: <missing inputs/behaviors/labels>
- Measurement gaps: <failure mode not scored/tagged/faceted>, proposed scorer/facet
- Confidence and unknowns: <what still needs trace inspection or human labels>
```

## Phase 3: Diagnose

Synthesize Discover findings and determine what needs to change. This is the routing intelligence of the flywheel — reason carefully before producing an action plan. The examples below are diagnostic prompts, not a closed taxonomy.

For each candidate root cause, name the supporting evidence, counterevidence, confidence, and artifact to change. Prefer "measure first" when production shows a real problem but current evals/scorers cannot observe it.

**Is this a measurement gap or new scorer/facet needed?**
- Signs: repeated production failure is visible in traces but no score, tag, facet, or dataset field separates it
- Signs: humans can describe "bad" behavior but existing eval metrics pass it
- Signs: a new tool, handoff, output contract, policy, or domain constraint creates a new correctness dimension
- Route: create or update scorer/classifier/facet criteria before using the metric as an optimization target

**Is this a scorer problem?**
- Signs: production shows behaviors that should score badly but score well (or vice versa)
- Signs: bimodal score distribution found in Discover (all 0s or all 1s)
- Signs: scorer criteria reference agent behaviors the agent no longer exhibits
- Signs: scorer disagrees with human labels or trace inspection on representative examples

**Is this a dataset gap?**
- Signs: failure modes or edge cases from production don't appear in existing dataset examples
- Signs: input patterns in production not represented in evals
- Signs: evals improve while production cohorts remain bad

**Is this an agent problem?**
- Signs: agent behaves incorrectly on inputs that datasets and scorers already cover well
- Signs: clear behavioral error (wrong tool call, unexpected refusal, wrong output format, hallucinated tool)
- Signs: failures cluster around a prompt/tool/orchestration path that local code owns

**Is this instrumentation or observability drift?**
- Signs: missing root inputs/outputs, inconsistent metadata, renamed score columns, broken trace linkage, or spans that hide tool arguments
- Signs: production behavior cannot be reconstructed well enough to curate data or debug
- Route: fix logging/instrumentation before concluding the agent is healthy

**Is this a structural change needed?**
- Signs: the agent was recently changed significantly (new tools, output format, trajectory restructured)
- Signs: both datasets AND scorers need updating to match the new agent interface

**Nothing actionable?**
- Signs: production looks healthy, scores are good, no anomalies, no coverage gaps
- Route: report healthy status and **exit the flywheel**. In autonomous mode, write healthy status to `bt-flywheel-summary.json` before exiting.

Produce a prioritized action plan listing which artifacts to change and in what order. Multiple conditions can apply — list them in priority order and execute sequentially.

**In interactive mode**: Present the action plan with reasoning. Wait for confirmation or override before proceeding. Honor any steps the user wants to skip.

**In autonomous mode**: Log the full action plan and proceed immediately.

## Phase 4: Improve

Apply the artifact route chosen in Diagnose. Multiple routes can apply; execute them in priority order with measurement/instrumentation fixes before optimizing agent behavior.

**In interactive mode**: Present the planned artifact changes and wait for confirmation before irreversible writes.
**In autonomous mode**: Apply the action plan and log each change with evidence, files/functions touched, and why it was safe.

### Measurement Route

Load `references/bt-functions-patterns.md`.

Create or update a scorer, classifier, or facet when Diagnose found a measurement gap or stale criteria:

1. Define the failure mode in observable terms: what fields/spans prove pass, partial credit, fail, and "not applicable"?
2. Collect a small calibration set with positive, negative, borderline, and adversarial traces.
3. Choose the simplest reliable implementation: deterministic code for structural checks, LLM judge for semantic quality, or a hybrid with explicit rubrics.
4. Validate against the calibration set before trusting the score. If labels are uncertain, set outcome `blocked` or `needs_work` and add a `label_data` next step.
5. Add the measurement to the eval path and verify it is informative rather than all-zero/all-one.

If the function lives in Braintrust, read it first with `bt functions view <slug> -p <project-name>`, make a targeted local change, then push with `bt functions push -p <project-name> --file <path>`. If it lives in the codebase, edit the scorer file directly.

### Dataset Route

Load `references/bt-functions-patterns.md` for dataset CLI examples. Load `references/bt-sql-patterns.md` only when SQL filtering over dataset content is needed.

Pull balanced failing and passing candidates so the dataset does not skew toward hard cases only:

```bash
bt sql "SELECT id, input, output, scores.\"<SCORE_COL>\" FROM project_logs('<PROJECT_ID>')
        WHERE scores.\"<SCORE_COL>\" <= 0.5 AND created >= NOW() - INTERVAL 7 day
        ORDER BY RANDOM() LIMIT 50"

bt sql "SELECT id, input, output, scores.\"<SCORE_COL>\" FROM project_logs('<PROJECT_ID>')
        WHERE scores.\"<SCORE_COL>\" >= 0.8 AND created >= NOW() - INTERVAL 7 day
        ORDER BY RANDOM() LIMIT 50"
```

Inspect candidate traces with `bt view trace --object-ref project_logs:<project-id> --trace-id <id> --json` and extract the root input. Do not use bad production output as `expected`; use `scripts/bt-curate-patterns.py` for generated ground truth, deterministic train/validation splits, stable row IDs, and provenance metadata. In interactive mode, show a sample of generated labels before writing.

Use `bt datasets create/update` with `--id-field id`. If the agent interface changed, inspect and update stale rows so evals fail only for real behavior gaps, not obsolete data shape.

### Agent Route

Edit the agent codebase only after trace/eval evidence points to behavior the agent owns. Keep the change targeted: system prompt, tool schema, output format/parser, routing/trajectory logic, or retrieval/tool-use behavior. Before editing, read the relevant files and local instructions. Do not run `git add` or `git commit`; the caller owns git operations.

### Instrumentation Route

Fix instrumentation when production behavior cannot be reconstructed well enough to diagnose, curate, or verify. Typical changes: restore root input/output logging, add compact metadata used for slicing, expose tool arguments/results safely, repair trace IDs, or normalize renamed score/facet fields. Keep large payloads out of inline logs unless they are required for eval/debugging.

## Phase 5: Verify & Decide

Run evals, compare against baseline, inspect regressions, route the next loop, and write the exit handoff when stopping.

### Verify

Load `references/bt-eval-patterns.md`. Find eval files from project instructions, `find . -name "eval_*.py" -o -name "eval_*.ts" | grep -v node_modules | grep -v .venv`, or an `evals/` directory.

If the dataset has `split` metadata, use train for smoke/iteration and validation for the final measurement. Always run a smoke eval before a full eval:

```bash
set -a && source .env && set +a
bt eval --first 20 <eval_file>
```

If smoke scores are near zero or the eval is structurally broken, stop and route back to Improve. If smoke passes, run the full eval and capture the experiment ID/URL:

```bash
set -a && source .env && set +a
bt eval <eval_file>
# If bt eval fails, fall back to:
braintrust eval --env-file .env <eval_file>
```

### Compare

Load `references/bt-sql-patterns.md` for experiment query templates and `references/bt-view-patterns.md` for trace drill-in. Compare new vs baseline score statistics, check scorer distributions, and inspect regressions with full traces:

```bash
bt sql "SELECT AVG(scores.\"<SCORE_COL>\") AS avg, MIN(scores.\"<SCORE_COL>\") AS min FROM experiment('<new-id>')"
bt sql "SELECT AVG(scores.\"<SCORE_COL>\") AS avg, MIN(scores.\"<SCORE_COL>\") AS min FROM experiment('<baseline-id>')"
bt sql "SELECT id, scores.\"<SCORE_COL>\" FROM experiment('<new-id>') WHERE scores.\"<SCORE_COL>\" < 0.5"
```

Compile a verdict with metric deltas, regression count, scorer health, new failure patterns, remaining dataset gaps, and confidence.

### Decide

When multiple conditions apply, address them in this priority order:

| Condition | Next route |
|---|---|
| Production failure is real but unmeasured | Improve: measurement |
| Scorer distribution stuck at 0/1 or clearly wrong | Improve: measurement |
| Trace data cannot support diagnosis | Improve: instrumentation |
| New failure pattern emerged, not in datasets | Discover focused → Improve: dataset |
| Metric improved on validation but not on train | Improve: dataset |
| Metric did not move despite agent change | Improve: agent |
| Metric improved and new edge cases were found | Improve: dataset → Verify |
| Datasets do not cover eval-discovered cases | Improve: dataset → Verify |
| Metric improved, no regressions, measurement healthy | Exit handoff with outcome `improved` |
| Production healthy and no follow-up needed | Exit handoff with outcome `healthy` |

In interactive mode, present the routing decision and let the user override or stop. In autonomous mode, route automatically. If the target metric has not improved after 3 full loop iterations, stop with outcome `no_convergence`.

## Exit Handoff

Write `bt-flywheel-summary.json` and `bt-flywheel-narrative.md` when stopping in autonomous mode, and present the same content in interactive mode. The handoff is adapter-neutral: it should help a local developer, triggered workflow, GitHub Action, embedded app, or internal orchestrator decide what to do next. Do not open PRs, create issues, send Slack/Jira/Linear messages, call webhooks, block deploys, or trigger rollbacks from the skill itself.

Use `references/bt-flywheel-output-templates.md` for the schema and examples. Required handoff concepts:

- `outcome`: `healthy`, `improved`, `needs_work`, `blocked`, or `no_convergence`
- `severity`, `blocking`, and `confidence`
- concise `summary`, evidence-backed `findings`, artifact-specific `changes`, and `verification`
- structured `links` for Braintrust experiments, traces, queries, docs, or external references
- structured `artifacts` for local files produced by the run
- `next_steps` with adapter-neutral intent, priority, title/body, optional suggested destination, and idempotency key

Prefer intent over destination. Example intents: `no_action`, `review_change`, `investigate`, `label_data`, `rerun`, `notify`, `block_release`, `rollback`. Example suggested destinations: `local_summary`, `code_review`, `issue_tracker`, `chat`, `release_gate`, `scheduler`, `app_ui`, `external_system`, `none`.

## Success State

The flywheel run is complete when any of the following is true:

1. Verify & Decide exits with outcome `improved`: target metric improved, no blocking regressions, measurement healthy
2. Diagnose exits early with outcome `healthy`: production is already healthy
3. The user says they are done for this session
4. Autonomous mode completes one full loop iteration, stops, and writes summary, narrative, links, artifacts, and next steps
