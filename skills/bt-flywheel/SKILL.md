---
name: bt-flywheel
description: Use when improving an AI agent built on Braintrust — starting a dev session, running a CI/eval pipeline, on a scheduled cadence, after a deployment, or when production scores have degraded.
---

# Braintrust Agent Improvement Flywheel

Eight-phase cycle: Orient → Discover → Diagnose → Curate → Iterate → Eval → Analyze → Loop. On exit, emit non-executing Act recommendations for the calling harness.

## When to Use

- Starting a session to improve an agent ("let's improve my agent", "run the flywheel")
- At the start of a CI/eval pipeline run
- On a scheduled cadence (cron or weekly improvement cycle)
- After deploying a change to measure its impact
- When something degraded in production and you need to diagnose and fix it

## The Three Artifacts

Every phase can surface the need to change any of these:

| Artifact | Where it lives | How to change |
|---|---|---|
| **Agent** | Customer codebase (code files) | Code edits |
| **Scorers** | Braintrust (`bt functions`) or codebase | `bt functions push` or code edit |
| **Datasets** | Braintrust | Python SDK or Braintrust UI (no `bt datasets` CLI) |

## Reference Files

Load these when executing the relevant phase:

- `references/bt-sql-patterns.md` — SQL query templates for Discover and Analyze
- `references/bt-view-patterns.md` — `bt view` command patterns
- `references/bt-eval-patterns.md` — eval invocation patterns
- `references/bt-functions-patterns.md` — scorer/prompt/dataset read-write patterns
- `references/bt-sync-patterns.md` — bulk log/experiment/dataset sync (pull/push)
- `references/bt-topics-patterns.md` — Topics automation (input clustering, classification)
- `scripts/bt-curate-patterns.py` — ground truth labeling, split assignment, dataset insert
- `references/bt-flywheel-output-templates.md` — `bt-flywheel-summary.json` and `bt-flywheel-narrative.md` templates

---

## Detecting Interaction Mode

Before starting, check for autonomous mode signals in order:

1. Explicit flag: `mode: autonomous` in the invocation
2. `CI=true` environment variable
3. `FLYWHEEL_AUTONOMOUS=true` environment variable
4. Stdin is not a TTY (non-interactive shell context)

If any signal is present: **autonomous mode** — suppress all gates, log all decisions, write summary and recommended actions to `bt-flywheel-summary.json` on exit.

Otherwise: **interactive mode** — present plans before irreversible actions and wait for confirmation.

---

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

---

## Phase 2: Discover

Mine production traces for patterns the agent has not been evaluated on.

Load `references/bt-sql-patterns.md`. Run each discovery query, substituting `<PROJECT_ID>` and discovered column names. Use the 7-day window as default; adjust if the project has low traffic.

**Step 1 — Errors:** Find traces with errors.

**Step 2 — Low scores:** For each discovered score column, find traces scoring ≤ 0.5.

**Step 3 — High latency:** Find traces where `metrics.duration_ms > 10000`.

**Step 4 — Score distribution:** GROUP BY score value to detect bimodal distributions. A distribution stuck at 0 or 1 strongly suggests the scorer is broken or its criteria are misaligned.

**Step 5 — Facet distribution** (if facets discovered): GROUP BY facet column to understand input topic coverage and spot underrepresented categories. Alternatively, load `references/bt-topics-patterns.md` and use `bt topics status --full` for Topics automation's clustering view.

**Step 6 — Drill into interesting traces:** Load `references/bt-view-patterns.md` and use `bt view trace` to inspect the full span tree for any trace IDs worth investigating.

**Step 7 — Pull baseline experiment context:** Read recent rows from the baseline experiment to understand what inputs evals are currently testing vs. what's in production:
```bash
bt sql "SELECT id, scores.\"<SCORE_COL>\", output FROM experiment('<baseline-experiment-id>') LIMIT 20"
```

**Compile findings** into a structured report before proceeding to Diagnose:
```
DISCOVER FINDINGS:
- Error rate: X/Y root spans with errors in last 7 days
- Low score rate: X/Y traces scoring ≤ 0.5 on <SCORE_COL>
- Score distribution: [normal / bimodal / all-zero / all-one]
- High latency traces: N found (max duration: Xms)
- Notable patterns: [specific edge cases, input clusters, failure types]
- Production vs. eval gaps: [inputs appearing in prod not represented in datasets]
```

---

## Phase 3: Diagnose

Synthesize Discover findings and determine what needs to change. This is the routing intelligence of the flywheel — reason carefully before producing an action plan.

**Is this a scorer problem?**
- Signs: production shows behaviors that should score badly but score well (or vice versa)
- Signs: bimodal score distribution found in Discover (all 0s or all 1s)
- Signs: scorer criteria reference agent behaviors the agent no longer exhibits

**Is this a dataset gap?**
- Signs: failure modes or edge cases from production don't appear in existing dataset examples
- Signs: input patterns in production not represented in evals

**Is this an agent problem?**
- Signs: agent behaves incorrectly on inputs that datasets and scorers already cover well
- Signs: clear behavioral error (wrong tool call, unexpected refusal, wrong output format, hallucinated tool)

**Is this a structural change needed?**
- Signs: the agent was recently changed significantly (new tools, output format, trajectory restructured)
- Signs: both datasets AND scorers need updating to match the new agent interface

**Nothing actionable?**
- Signs: production looks healthy, scores are good, no anomalies, no coverage gaps
- Action: report healthy status and **exit the flywheel**. In autonomous mode, write healthy status to `bt-flywheel-summary.json` before exiting.

Produce a prioritized action plan listing which artifacts to change and in what order. Multiple conditions can apply — list them in priority order and execute sequentially.

**In interactive mode**: Present the action plan with reasoning. Wait for confirmation or override before proceeding. Honor any steps the user wants to skip.

**In autonomous mode**: Log the full action plan and proceed immediately.

---

## Phase 4: Curate

Execute dataset and scorer changes identified in the Diagnose plan.

### Updating Datasets

Load `references/bt-sql-patterns.md` if you need to inspect existing dataset content.

#### Step 1 — Collect candidates (balanced)

Pull both failing *and* passing examples so the dataset doesn't skew toward hard cases only.

```bash
# Failing examples (low scores or errors)
bt sql "SELECT id, input, output, scores.\"<SCORE_COL>\" FROM project_logs('<PROJECT_ID>')
        WHERE scores.\"<SCORE_COL>\" <= 0.5 AND created >= NOW() - INTERVAL 7 day
        ORDER BY RANDOM() LIMIT 50"

# Passing examples (same time window)
bt sql "SELECT id, input, output, scores.\"<SCORE_COL>\" FROM project_logs('<PROJECT_ID>')
        WHERE scores.\"<SCORE_COL>\" >= 0.8 AND created >= NOW() - INTERVAL 7 day
        ORDER BY RANDOM() LIMIT 50"
```

Target roughly 1:1 ratio. If passing examples are scarce (e.g. bimodal scorer issue), proceed with whatever is available.

#### Step 2 — Inspect traces and extract inputs

For each candidate trace ID, retrieve the full span tree to get the actual agent input:

```bash
bt view trace --object-ref project_logs:<project-id> --trace-id <id> --json
```

Extract the root span's `input` field — not the agent's output, which may be wrong.

#### Step 3 — Auto-label ground truth

**Do not use the production output as `expected`** for failing examples. Use an LLM judge to generate correct expected values. Load `scripts/bt-curate-patterns.py` for the `generate_ground_truth` function (uses `gpt-4o`).

For passing examples where the production output looks correct, you may use it directly as `expected` — but spot-check a few first.

**In interactive mode**: Show a sample of generated ground truth labels before inserting. Ask for confirmation or spot corrections.

**In autonomous mode**: Log the labeler model used and insert without confirmation.

#### Step 4 — Assign train/validation splits

Use deterministic split assignment so the same row always lands in the same split across iterations. Load `scripts/bt-curate-patterns.py` for the `assign_split` function (SHA-256 hash of `seed:row_id`, 80/20 split).

#### Step 5 — Insert with metadata

Tag and insert each row with split and provenance metadata. Load `scripts/bt-curate-patterns.py` for `build_dataset_payload()` and `insert_labeled_rows()`, including the `bucket`, `split`, `source_trace_id`, and `flywheel_iteration` metadata fields. The helper defaults to dry-run; write to Braintrust only after the relevant interactive confirmation or autonomous action plan has been logged.

`bucket` is `"failing"` for low-score/error examples, `"passing"` for high-score examples.

#### Step 6 — Scope evals to validation split

Once rows have split metadata, scope Phase 6 Eval to the validation split. Load `scripts/bt-curate-patterns.py` for the filter snippet. Use the train split for smoke runs and iterative tuning; validation only for the final measurement.

---

**Existing dataset updates** (structural changes): If the agent's interface changed, update stale dataset rows to use the new format — otherwise evals fail for the wrong reasons. Inspect current rows first:

```bash
bt sql "SELECT * FROM dataset('<dataset-id>') LIMIT 20"
```

There is no `bt datasets` CLI command — use the Python SDK for writes and `bt sql` for reads.

### Updating Scorers

Load `references/bt-functions-patterns.md`.

If scorer lives in Braintrust:
1. Read current scorer: `bt functions view <scorer-slug> -p <project-name>`
2. Identify the specific criteria that are wrong or stale
3. Make targeted changes — only fix what Diagnose identified
4. Push update: `bt functions push -p <project-name> --file <path>`

If scorer lives in the codebase: edit the scorer file directly. Changes should be minimal and targeted.

**In interactive mode**: Present planned changes. Wait for confirmation before any writes.

**In autonomous mode**: Apply changes and log what was changed and why.

---

## Phase 5: Iterate

Edit the agent codebase based on the Diagnose plan.

Make targeted changes only — fix the specific problems Diagnose identified. Do not refactor or improve things outside the scope of the findings.

Common change types:
- **System prompt**: edit the prompt string in agent config/code
- **Tool definitions**: add, remove, or modify tool schemas
- **Output format**: update expected output structure or parser
- **Trajectory/orchestration**: update routing logic or agent flow

Before editing, read the relevant files to understand current structure. Make changes that directly address the Diagnose findings.

**In interactive mode**: Describe the planned code change before making it. Wait for confirmation.

**In autonomous mode**: Apply the change and log what was changed and why (file, what changed, production evidence, experiment ID). Do not run `git add` or `git commit` — the calling workflow owns all git operations.

---

## Phase 6: Eval

Run evals against the current agent + scorer + dataset state.

Load `references/bt-eval-patterns.md`.

**Finding eval files:**
1. Check project `CLAUDE.md` for documented eval file paths
2. Search: `find . -name "eval_*.py" -o -name "eval_*.ts" | grep -v node_modules | grep -v .venv`
3. Check for `evals/` directory: `ls evals/ 2>/dev/null`

**Split scoping**: If the dataset has `split` metadata, run smoke tests against `train` and full evals against `validation`.

**Run a smoke test first** (check `bt eval --help` to confirm `--first` is available):

```bash
set -a && source .env && set +a
bt eval --first 20 <eval_file>
```

If smoke run shows near-zero scores: stop. Go back to Phase 4 or Phase 5 — something is fundamentally broken.

**Run full eval:**

```bash
set -a && source .env && set +a
bt eval <eval_file>
# If bt eval fails, fall back to:
braintrust eval --env-file .env <eval_file>
```

**Capture the experiment ID and URL** from `bt eval` output — required for Phase 7:
```
experiment_url = https://www.braintrust.dev/app/<org>/p/<project-name>/experiments/<experiment-id>
```

**In interactive mode**: Ask — smoke run first? full eval? run and don't ask again? skip?

**In autonomous mode**: Always run smoke first. If smoke passes, run full eval.

---

## Phase 7: Analyze

Compare the new experiment to the baseline.

Load `references/bt-sql-patterns.md` for experiment query templates and `references/bt-view-patterns.md` for trace drill-in commands.

**Step 1 — Score statistics for both experiments:**
```bash
bt sql "SELECT AVG(scores.\"<SCORE_COL>\") AS avg, MIN(scores.\"<SCORE_COL>\") AS min FROM experiment('<new-id>')"
bt sql "SELECT AVG(scores.\"<SCORE_COL>\") AS avg, MIN(scores.\"<SCORE_COL>\") AS min FROM experiment('<baseline-id>')"
```

**Step 2 — Find regressions:**
```bash
bt sql "SELECT id, scores.\"<SCORE_COL>\" FROM experiment('<new-id>') WHERE scores.\"<SCORE_COL>\" < 0.5"
```

**Step 3 — Scorer distribution check:**
```bash
bt sql "SELECT scores.\"<SCORE_COL>\", COUNT(*) as count FROM experiment('<new-id>') GROUP BY scores.\"<SCORE_COL>\" ORDER BY scores.\"<SCORE_COL>\""
```

**Step 4 — Drill into regressions:** For each regressed trace ID, construct its URL and attempt to fetch its span tree:
```bash
bt view trace --object-ref project_logs:<project-id> --trace-id <id> --json
# If not found via project_logs, try the experiment object ref:
bt view trace --object-ref experiment:<experiment-id> --trace-id <id> --json
```

**Compile verdict:**
```
ANALYZE VERDICT:
- <SCORE_COL>: baseline avg=X → new avg=Y (delta: Z)
- Experiment: <url>
- Regressions: N rows scoring < 0.5
  - <trace-id>: score=X — <url>
- Scorer health: [normal distribution / bimodal — possible scorer issue]
- New failure patterns: [describe if any]
- Datasets still missing: [describe uncovered cases if any]
```

---

## Phase 8: Loop

Route based on the Analyze verdict. When multiple conditions apply, address them in this priority order:

| Condition | Next action |
|---|---|
| Scorer distribution stuck at 0/1 or clearly wrong | → Phase 4: Curate (scorer fix — highest priority) |
| New failure pattern emerged, not in datasets | → Phase 2: Discover (focused) → Phase 4: Curate |
| Metric improved on validation but not on train | → Phase 4: Curate (expand training set — likely overfitting) |
| Metric didn't move despite agent change | → Phase 5: Iterate (find a different fix) |
| Metric improved AND new edge cases found in eval | → Phase 4: Curate (add new cases) → re-run Phase 6: Eval |
| Datasets don't cover cases found in eval | → Phase 4: Curate (dataset additions) → re-run Phase 6: Eval |
| Metric improved, no regressions, scorers healthy | **Exit** — set new experiment as baseline, write summary and Act recommendations, exit |

**In interactive mode**: Present the routing decision and reasoning. Allow the user to override or stop.

**In autonomous mode**: Route automatically and log the decision. Write `bt-flywheel-summary.json` and `bt-flywheel-narrative.md` to the working directory root — see `references/bt-flywheel-output-templates.md` for both schemas.

**Max iterations:** If the metric has not improved after 3 full loop iterations, exit with `loop_decision: "no-convergence"` — do not loop indefinitely.

---

## Act Recommendations

Before exit, choose what a downstream harness should do next. Do not open PRs, create issues, send Slack messages, or create Jira/Linear tickets from the skill itself. The skill owns evidence-backed recommendation; the caller owns side effects, permissions, idempotency, and destination-specific policy.

Add `recommended_actions` to `bt-flywheel-summary.json`. Use `references/bt-flywheel-output-templates.md` for the schema.

Choose actions with these defaults:

| Situation | Recommended action |
|---|---|
| Codebase changes were made, eval passed, no blocking regressions | `pull_request` |
| Codebase changes were made, but regressions or uncertain impact remain | `pull_request` with `requires_human_review: true` |
| No code changes, but production degradation, dataset gap, scorer issue, setup blocker, or no-convergence needs follow-up | `issue` |
| Findings need human labeling, product judgment, credentials, or policy approval | `issue` |
| Urgent degradation or completed autonomous run should notify a team | `slack` as an additional notification action |
| The downstream team uses Jira or Linear instead of GitHub Issues | `jira` or `linear` instead of `issue` |
| Production is healthy and no follow-up is needed | `none` |

Each non-`none` action must include a title, body, reason, evidence links, `requires_human_review`, and an `idempotency_key` stable enough for the caller to deduplicate repeated scheduled runs.

---

## Success State

The flywheel run is complete when any of the following is true:

1. Loop routes to "exit" — target metric improved, no regressions, scorers healthy
2. Diagnose exits early with "nothing actionable" — production is already healthy
3. The user says they are done for this session (interactive mode)
4. Autonomous mode completes one full loop iteration, routes to "done", and writes summary, narrative, and Act recommendations
