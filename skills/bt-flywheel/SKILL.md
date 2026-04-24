---
name: bt-flywheel
description: Guide the full Braintrust agent improvement flywheel — mine production for insights, curate datasets and scorers, iterate on agent code, run evals, and route intelligently based on findings. Use when improving an AI agent built on Braintrust. Works in interactive dev sessions, CI pipelines, and scheduled/cron contexts.
---

# Braintrust Agent Improvement Flywheel

A structured workflow for continuously improving an AI agent using Braintrust: mine production traces for insights → diagnose what needs to change → curate datasets and scorers → update agent code → run evals → analyze results → route back to the right phase.

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

---

## Detecting Interaction Mode

Before starting, check for autonomous mode signals in order:

1. Explicit flag: `mode: autonomous` in the invocation
2. `CI=true` environment variable
3. `FLYWHEEL_AUTONOMOUS=true` environment variable
4. Stdin is not a TTY (non-interactive shell context)

If any signal is present: **autonomous mode** — suppress all gates, log all decisions, write summary to `bt-flywheel-summary.json` on exit.

Otherwise: **interactive mode** — present plans before irreversible actions and wait for confirmation.

---

## Phase 1: Orient

Establish session context before running any queries.

**Step 1 — Resolve the active project (never ask the user for a project ID):**

Check in this order:
1. `.bt/config.json` in the working directory — written by `bt setup`, contains `project` (name) and/or `project_id`
2. `CLAUDE.md` in the project root — may document project name, ID, score columns, eval paths, dataset names
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

Check `CLAUDE.md` first for:
- Score column names (e.g., `scores."Response Quality"`)
- Facet column names
- Eval file paths
- Dataset names

If not in `CLAUDE.md`, run schema introspection using the resolved `<PROJECT_ID>` with progressive time window expansion:

```bash
# Try 1 day
bt sql "SELECT * FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND created >= NOW() - INTERVAL 1 day LIMIT 1"
# If no results, try 7 days
bt sql "SELECT * FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND created >= NOW() - INTERVAL 7 day LIMIT 1"
# If still no results, try 30 days
bt sql "SELECT * FROM project_logs('<PROJECT_ID>') WHERE is_root = true AND created >= NOW() - INTERVAL 30 day LIMIT 1"
```

Inspect the returned row to identify:
- `scores.*` columns — these are your `<SCORE_COL>` values
- `facets.*` columns — these are your `<FACET_COL>` values
- Any other metadata fields

Null values for nested fields still reveal the column name structure.

If no rows are found after 30 days: note this ("project has no production traffic in the last 30 days") and proceed with generic queries.

Store all discovered column names and the resolved project ID for use in subsequent phases.

**Resolve app URL and org slug** (needed to construct Braintrust links in the summary):

```bash
bt status --json
# Returns: { "org": "<org-name>", ... }
```

Store the org name. Braintrust URLs follow this pattern (URL-encode spaces in org/project names as `%20`):
- Experiment: `https://www.braintrust.dev/app/<org>/p/<project-name>/experiments/<experiment-id>`
- Trace: `https://www.braintrust.dev/app/<org>/p/<project-name>/r/<trace-id>`

These links will be embedded in the summary and narrative outputs.

---

## Phase 2: Discover

Mine production traces for patterns the agent has not been evaluated on.

Load `references/bt-sql-patterns.md`. Run each discovery query, substituting `<PROJECT_ID>` and discovered column names. Use the 7-day window as default; adjust if the project has low traffic.

**Step 1 — Errors:** Find traces with errors.

**Step 2 — Low scores:** For each discovered score column, find traces scoring ≤ 0.5.

**Step 3 — High latency:** Find traces where `metrics.duration_ms > 10000`.

**Step 4 — Score distribution:** GROUP BY score value to detect bimodal distributions. A distribution stuck at 0 or 1 (all traces scoring the same) strongly suggests the scorer is broken or its criteria are misaligned.

**Step 5 — Facet distribution** (if facets discovered): GROUP BY facet column to understand input topic coverage and spot underrepresented categories. Alternatively, load `references/bt-topics-patterns.md` and use `bt topics status --full` to get Topics automation's clustering view of production inputs.

**Step 6 — Drill into interesting traces:** For any trace IDs surfaced by the SQL queries that look worth investigating, load `references/bt-view-patterns.md` and use `bt view trace` to inspect the full span tree.

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

Work through each question:

**Is this a scorer problem?**
- Signs: production shows behaviors that should score badly but score well (or vice versa)
- Signs: bimodal score distribution found in Discover (all 0s or all 1s)
- Signs: scorer criteria reference agent behaviors the agent no longer exhibits (e.g., old output format)

**Is this a dataset gap?**
- Signs: failure modes or edge cases from production don't appear in existing dataset examples
- Signs: input patterns in production (topic clusters, edge cases) not represented in evals

**Is this an agent problem?**
- Signs: agent behaves incorrectly on inputs that datasets and scorers already cover well
- Signs: clear behavioral error (wrong tool call, unexpected refusal, wrong output format, hallucinated tool)

**Is this a structural change needed?**
- Signs: the agent was recently changed significantly (new tools added, output format changed, trajectory restructured)
- Signs: both datasets AND scorers need updating to match the new agent interface

**Nothing actionable?**
- Signs: production looks healthy, scores are good, no anomalies, no coverage gaps
- Action: report healthy status and **exit the flywheel**. Do not proceed to Curate or Iterate. In autonomous mode, write healthy status to `bt-flywheel-summary.json` before exiting.

Produce a prioritized action plan listing which artifacts to change and in what order. Multiple conditions can apply simultaneously — list them in priority order and execute them sequentially.

**In interactive mode**: Present the action plan with reasoning. Wait for confirmation or override before proceeding. Honor any steps the user wants to skip.

**In autonomous mode**: Log the full action plan and proceed immediately.

---

## Phase 4: Curate

Execute dataset and scorer changes identified in the Diagnose plan.

### Updating Datasets

Load `references/bt-sql-patterns.md` if you need to inspect existing dataset content.

To add examples from production traces:
1. Retrieve the trace content: `bt view trace --object-ref project_logs:<project-id> --trace-id <id> --json`
2. Extract the relevant `input` and `expected` output from the span tree
3. Tag the example descriptively (e.g., `["production", "edge-case", "routing-failure"]`)
4. Insert via Python SDK:

```python
import braintrust, os
braintrust.login(api_key=os.getenv("BRAINTRUST_API_KEY"))
dataset = braintrust.init_dataset(project="<project-name>", name="<dataset-name>")
dataset.insert({"input": ..., "expected": ..., "tags": [...]})
```

Use the project name from `CLAUDE.md` or as confirmed in Phase 1 Orient. Use the dataset name from Discover findings or ask the user (in interactive mode).

If the agent's interface changed structurally (new tool calls, new output format, trajectory changes), update existing dataset rows to use the new format — otherwise evals will fail for the wrong reasons.

To inspect existing dataset content, use `bt sql`:
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

If scorer lives in the codebase: edit the scorer file directly. Changes should be minimal and targeted — only update what's actually wrong.

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

**Run a smoke test first** (recommended before full eval during iteration — check `bt eval --help` to confirm `--first` is available in your version):

```bash
set -a && source .env && set +a
bt eval --first 20 <eval_file>
```

If smoke run shows near-zero scores (catastrophic failure): stop, do not run full eval. Go back to Phase 4 (Curate) or Phase 5 (Iterate) — something is fundamentally broken.

**Run full eval:**

```bash
# Source .env (if not already sourced from smoke run)
set -a && source .env && set +a
bt eval <eval_file>
# If bt eval fails, fall back to:
braintrust eval --env-file .env <eval_file>
```

**Capture the experiment ID and URL** from `bt eval` output — the ID is printed on completion and is required for Phase 7. Immediately construct the experiment URL using the pattern resolved in Phase 1 Orient and store it alongside the ID:
```
experiment_url = https://www.braintrust.dev/app/<org>/p/<project-name>/experiments/<experiment-id>
```

**In interactive mode**: Present the eval command. Ask:
- "Run smoke run first?" → run `--first 20` first (if available in your `bt` version)
- "Run full eval?" → run full eval
- "Run and don't ask again?" → run full eval and suppress further eval gates this session
- "Skip?" → skip eval this iteration

**In autonomous mode**: Always run smoke first. If smoke passes (non-catastrophic), run full eval.

---

## Phase 7: Analyze

Compare the new experiment to the baseline.

Load `references/bt-sql-patterns.md` for experiment query templates and `references/bt-view-patterns.md` for trace drill-in commands.

Run these queries (replacing experiment IDs and column names):

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
Construct the trace URL: `https://www.braintrust.dev/app/<org>/p/<project-name>/r/<trace-id>` — include this in the verdict even if the span fetch fails.

**Compile verdict:**
```
ANALYZE VERDICT:
- <SCORE_COL>: baseline avg=X → new avg=Y (delta: Z)
- Experiment: <url>
- Regressions: N rows scoring < 0.5
  - <trace-id>: score=X — <url>
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
| Metric didn't move despite agent change | → Phase 5: Iterate (find a different fix) |
| Metric improved AND new edge cases found in eval | → Phase 4: Curate (add new cases) → re-run Phase 6: Eval |
| Datasets don't cover cases found in eval | → Phase 4: Curate (dataset additions) → re-run Phase 6: Eval |
| Metric improved, no regressions, scorers healthy | **Exit** — set new experiment as baseline (update `FLYWHEEL_BASELINE_EXPERIMENT` env var or note the new baseline ID for the user), write summary, exit |

**In interactive mode**: Present the routing decision and reasoning. Allow the user to override the routing or stop the session.

**In autonomous mode**: Route automatically and log the decision. Then write `bt-flywheel-summary.json` to the working directory root:

**Max iterations:** If the metric has not improved after 3 full loop iterations, exit with `loop_decision: "no-convergence"` and surface the findings to the user — do not loop indefinitely.

```json
{
  "timestamp": "<ISO8601>",
  "goal": "<goal or 'general health check'>",
  "phases_run": ["<phase-name>", ...],
  "findings": ["<finding 1>", "<finding 2>"],
  "changes": {
    "agent": ["<description>"],
    "scorers": ["<description>"],
    "datasets": ["<description>"]
  },
  "experiment": {
    "new": "<experiment-id>",
    "new_url": "https://www.braintrust.dev/app/<org>/p/<project>/experiments/<experiment-id>",
    "baseline": "<experiment-id>",
    "baseline_url": "https://www.braintrust.dev/app/<org>/p/<project>/experiments/<baseline-id>",
    "metric_delta": { "<SCORE_COL>": 0.05 }
  },
  "regressions": [
    {
      "trace_id": "<trace-id>",
      "score": 0.0,
      "url": "https://www.braintrust.dev/app/<org>/p/<project>/r/<trace-id>"
    }
  ],
  "loop_decision": "<done | re-discover | re-curate | re-iterate>",
  "loop_reasoning": "<reasoning>"
}
```

---

## CI Narrative (autonomous mode only)

After writing `bt-flywheel-summary.json`, write a second file `bt-flywheel-narrative.md` to the working directory. This file is consumed by CI to populate a GitHub PR description (if changes were made) or job summary (if nothing changed). Write it while you still have full context — do not summarize from the JSON.

**If changes were made**, structure the narrative as a GitHub PR body:

```
## Flywheel Optimization Run

> Auto-generated by the bt-flywheel self-improvement cycle.

### What Changed
[List each change with the specific file/component modified]

### Why These Changes
[Cite the actual production evidence that drove each change: SQL query results,
specific score values, trace IDs with Braintrust links, failure patterns observed]

### Score Impact
[Before/after comparison from Phase 7 Analyze — use actual numbers and link to both experiments]

| | Baseline | New |
|---|---|---|
| Experiment | [<baseline-id>](<baseline_url>) | [<new-id>](<new_url>) |
| <SCORE_COL> avg | X | Y |
| Regressions | — | [<trace-id>](<url>), ... |

### Reviewer Checklist
- [ ] Score improvements are genuine (not overfitting to the eval dataset)
- [ ] No regressions in non-targeted metrics
- [ ] Dataset additions reflect real production failure patterns
- [ ] Agent/prompt changes are intentional and appropriately scoped
```

**If no changes were made**, write a concise summary of what was found and why no action was taken — cite specific numbers and whether production is healthy or needs human attention.

---

## Success State

The flywheel run is complete when any of the following is true:

1. Loop routes to "exit" — target metric improved, no regressions, scorers healthy
2. Diagnose exits early with "nothing actionable" — production is already healthy
3. The user says they are done for this session (interactive mode)
4. Autonomous mode completes one full loop iteration, routes to "done", and writes both summary files
