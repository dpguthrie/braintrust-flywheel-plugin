---
name: bt-instrumentation-doctor
description: Use when reviewing a Braintrust customer's tracing/instrumentation health and producing an actionable improvement plan. Covers trace structure, scorer setup, thread/session grouping, payload shape, cost efficiency, and code-level instrumentation patterns. Run inside the customer's codebase so findings can be tied back to specific files.
---

# Braintrust Instrumentation Doctor

Inspect a customer's Braintrust traces (logs and experiments) plus their codebase, then produce a prioritized plan for improving instrumentation across structure, scorers, threads, payload shape, and cost. The output is a markdown plan and a machine-readable JSON summary the caller can route into review, issues, or follow-up loops.

## When to Use

- A Braintrust customer asks "how can we improve our tracing?"
- A new project's traces look thin, oversized, mis-nested, or hard to grade
- Scorers are running but appear to be on the wrong span scope (per-span instead of trace-level, or root-only when they need turn-level)
- Multi-turn conversations are scattered across separate traces and the Thread view is unusable
- Trace payloads look bloated (full transcripts on every child span, raw documents inline, duplicate request/response logging)
- A periodic instrumentation health check before scaling traffic or before an audit

## What This Skill Owns vs. Companion Skills

| Question | Skill |
|---|---|
| "Is my tracing structure healthy and what should change?" | **bt-instrumentation-doctor** (this) |
| "What's driving cost on this account and how do I reduce it?" | [`bt-cost-optimizer`](../bt-cost-optimizer/SKILL.md) — deeper byte/scorer/Gateway accounting |
| "Mine traces → improve agent/scorers/datasets → re-eval" | [`bt-flywheel`](../bt-flywheel/SKILL.md) — full improvement loop |

This skill covers payload-size and scorer-cost concerns as *tracing health* dimensions. For an isolated billing/usage investigation, route to `bt-cost-optimizer`. Both skills can run on the same project.

## Reference Files

Load only what the current phase needs:

- `references/tracing-best-practices.md` — span structure, naming, error capture, metadata hygiene, model/version capture
- `references/scorer-setup-patterns.md` — online scorer scope, root vs. named spans, trace-level scoring, scorer-coverage rubric (6-category failure taxonomy + 4 named span scores), code vs. LLM judge defaults
- `references/thread-view-patterns.md` — session/thread id propagation, conversation grouping, Thread tab requirements
- `references/data-shape-patterns.md` — inline vs. attachment, deduplication, RAG/tool/embedding payloads, JSONAttachment
- `references/integrations.md` — AI providers, agent frameworks, and SDK integrations: when to recommend an official integration instead of hand-rolled spans
- `references/bt-query-patterns.md` — evidence-collection queries for instrumentation review
- `references/code-search-patterns.md` — SDK-specific grep recipes (Python/TS/Go) to tie findings to files
- `references/report-template.md` — expected plan layout and JSON summary schema
- `scripts/measure-trace-shape.py` — deterministic measurements over exported span/trace JSON (byte accounting, ratios, distributions). Emits raw numbers only — the agent interprets them.

## Core Principles

- Lead with evidence. Inspect real spans before asserting an instrumentation defect.
- Tie every finding to either a sample trace id, a code location, or both — a recommendation a customer cannot act on is noise.
- Distinguish *structural* problems (wrong nesting, missing root inputs, scorer mis-scope) from *cosmetic* ones (verbose field names). Lead with structural.
- Prefer the smallest change that fixes the failure mode the customer cares about. Do not rewrite their instrumentation top-to-bottom.
- Never recommend a Braintrust API/SDK option by name without verifying it exists in the version the customer is actually using. Resolve "actually using" in the user's environment, in this order, before naming a parameter, keyword, helper, or env var in a recommendation:
  1. **Installed package source.** Python: `python -c "import braintrust, os; print(os.path.dirname(braintrust.__file__))"` then read the relevant module (`logger.py`, etc.). TypeScript/JS: inspect `node_modules/braintrust/` (or the package indicated by `pnpm why braintrust` / `npm ls braintrust`). Go: `go doc <symbol>` against the imported module, or read the file under `$(go env GOMODCACHE)/braintrust...`.
  2. **Customer codebase.** `git grep` the symbol — if they already use it elsewhere, that's strong evidence it exists in their pinned version.
  3. **Published docs at the customer's pinned version** (<https://www.braintrust.dev/docs>). Docs reflect the current SDK; if the customer is pinned to an older version, the symbol may not exist yet.
  4. If none of the above can be checked from the current environment, name the *capability* rather than a specific symbol ("the SDK supports passing a `parent` to attach a span to an existing trace") and flag the finding with `confidence: low` until the user can confirm.
- Treat the customer's existing instrumentation as load-bearing. Preserve fields used by filters, scorers, evals, dashboards, or incident workflows unless the report explains why they should change.
- The skill emits a plan. It does not edit customer code unless the user explicitly asks for patches.

## Workflow

### 1. Orient

Resolve project context and locate the codebase before querying.

```bash
bt status --json
cat .bt/config.json 2>/dev/null
bt projects list --json
```

Capture and write to the working notes:

- org name and slug
- project name and project ID
- working-directory path (the customer's codebase — this skill assumes you are running inside it)
- detected SDK languages (look for `braintrust` in `package.json`, `pyproject.toml`/`requirements*.txt`, `go.mod`)
- time window to inspect, defaulting to 7 days
- primary concern from the user request (structure, scorers, threads, payload, cost, or "all")

If `.bt/config.json` is absent: suggest the user run `bt setup` so future commands target the right project, then proceed using `bt projects list --json` to resolve the ID.

### 2. Collect Evidence

Load `references/bt-query-patterns.md`. Pull bounded samples — never run unbounded `project_logs()` queries.

Minimum evidence set:

```bash
# Volume and shape over the window
bt sql --json "SELECT COUNT(*) AS spans, COUNT(DISTINCT root_span_id) AS traces FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day" > /tmp/bt-doc-volume.json

# A representative span sample for structural analysis
bt sql --json "SELECT * FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day LIMIT 1000" > /tmp/bt-doc-spans.json

# A small set of full traces (root + descendants) for nesting/duplication checks
bt sql --json "SELECT root_span_id, COUNT(*) AS spans FROM project_logs('<PROJECT_ID>', shape => 'spans') WHERE created >= NOW() - INTERVAL 7 day GROUP BY root_span_id ORDER BY spans DESC LIMIT 10" > /tmp/bt-doc-deep-traces.json

# Online scorer automations (required before any scorer recommendation)
curl -s "${BRAINTRUST_API_URL:-https://api.braintrust.dev}/v1/project_score?project_id=<PROJECT_ID>&limit=100" \
  -H "Authorization: Bearer ${BRAINTRUST_API_KEY}" > /tmp/bt-doc-automations.json

# Topics (so Thread/Topics recommendations are grounded)
bt topics status --json > /tmp/bt-doc-topics-status.json 2>/dev/null || true
```

Then pull the largest few traces in full so structural patterns are visible:

```bash
bt view trace --json --project-id <PROJECT_ID> --trace-id <ROOT_SPAN_ID> --limit 200 > /tmp/bt-doc-trace-<ROOT_SPAN_ID>.json
```

If the project has experiments and the user mentioned experiments, sample one:

```bash
bt sql --json "SELECT * FROM experiment('<EXPERIMENT_ID>') LIMIT 200" > /tmp/bt-doc-experiment.json
```

If `BRAINTRUST_API_KEY` is unset, automation rules cannot be fetched via REST — note this explicitly and direct the user to **Project → Logs → Score** in the UI for the scope/sampling fields any scorer recommendation depends on.

### 3. Analyze

Two kinds of work happen here: **deterministic computation** (byte accounting, ratios, distributions) belongs in code; **qualitative judgment** (is this trace structure healthy? does this scorer make sense?) belongs with the agent. The script handles the first; the agent does the second.

Work through these passes in order. Each pass is bounded: stop as soon as the dimension is either confidently healthy or has a finding worth writing up.

**Pass A — Sample-wide aggregates (via `bt sql`).** For each dimension, run the aggregate query in `references/bt-query-patterns.md` and capture the result. Aggregates are cheap, run server-side, and give a single number you can reason about. The dimensions and the question each query answers:

- Volume: how many spans/traces in the window? (sets sample size for everything below)
- Span names: cardinality, anonymous count, top-N. Are names stable and bounded?
- Root I/O health: % of roots with empty input or output.
- Errors: traces containing any error span.
- LLM completeness: % of LLM spans with `metadata.model`, `metrics.prompt_tokens`, `metrics.completion_tokens`.
- Scorer spans: by name, by model, scorer-to-total ratio.
- Session coherence: `metadata.session_id` (or equivalent) → distinct `root_span_id` count.

**Pass B — Read sample traces in full.** Pick 5–10 traces from the deepest/largest list (already captured in Orient as `/tmp/bt-doc-deep-traces.json`) and one randomly-selected root span. For each, run `bt view trace --json` and read it end-to-end. This is where structural patterns become visible — parent/child payload duplication, oversized fields, scorer scope, thread coherence — that aggregates can't show. Note the trace ids you used so the report can cite them.

**Pass C — Deterministic measurements.** Run the measurement script on the exported JSONL to get numbers that don't compress well to natural language: per-field byte attribution, duplicate-payload byte counts, payload-size percentiles, span-name cardinality, LLM completeness ratios, scorer-to-total ratio.

```bash
python3 skills/bt-instrumentation-doctor/scripts/measure-trace-shape.py \
  /tmp/bt-doc-spans.json /tmp/bt-doc-trace-*.json \
  --output /tmp/bt-doc-measurements.json
```

The script emits raw numbers only. There are no thresholds or severities — that's interpretation, which happens in pass D. Two reasons to use code here:

- **Determinism on bytes and hashes.** Field-byte attribution and duplicate-payload detection require walking JSON and hashing values; doing it in prose by reading spans is error-prone.
- **Scale.** When the sample is thousands of rows, the agent can't load every row, but the script can in a fraction of a second.

If the sample is small (a few dozen rows) and you've already read the traces in pass B, you can skip the script.

**Pass D — Apply each reference's checklist to the evidence.** For each dimension below, load the matching reference and walk its "Failure signals" / "Anti-Patterns" tables against what you saw in passes A, B, and C. A signal is a candidate finding, not a guaranteed one — confirm it represents real harm before writing it up. Use the script's numbers as inputs to *your* judgment about severity and impact — do not lift them as findings without context.

- Trace structure → `references/tracing-best-practices.md`
- Scorer scope and coverage → `references/scorer-setup-patterns.md` (includes the 6-category failure taxonomy and named span scores)
- Thread / session coherence → `references/thread-view-patterns.md`
- Payload shape and duplication → `references/data-shape-patterns.md`
- Integration vs. hand-rolled instrumentation → `references/integrations.md`

**Pass E — Tie findings to code.** For each candidate finding from pass D, run the language-appropriate search from `references/code-search-patterns.md` (Python: `git grep -nE 'init_logger|@traced|...'`; TS: `wrapTraced|wrapAISDK|...`; Go: `otel\.Tracer|...`). A finding without either a sample trace id or a file path is not actionable — downgrade its confidence or drop it.

If the project is high-volume and reading the JSONL exports in full would exceed your context, prefer additional `bt sql` aggregate queries (`SELECT COUNT(*), AVG(...) GROUP BY ...`) over loading more rows. The patterns file has aggregate examples for every dimension.

### 4. Plan

Load `references/report-template.md`. Write `bt-tracing-plan.md` with prioritized recommendations grouped by dimension. Every recommendation must carry:

- **Evidence:** sample trace id(s), span name(s), or code location(s) (`path/to/file.py:42`)
- **What's wrong:** the observed structural or shape issue
- **Suggested change:** concrete, scoped to one instrumentation site or pattern
- **Expected effect:** what improves (thread grouping, scorer accuracy, payload size, search ergonomics)
- **Tradeoff:** what the customer gives up
- **Confidence:** high / medium / low, per `references/report-template.md`
- **Effort:** small / medium / large

Order recommendations by impact × effort. Structural fixes (broken trace nesting, scorer scope errors, missing thread ids) almost always come before cosmetic improvements.

Also write `bt-tracing-summary.json` matching the schema in `references/report-template.md` so downstream automation (review bots, issue creators, follow-up flywheel runs) can consume the plan without re-parsing the markdown.

### 5. Hand Off

Present the plan. Do not edit customer code by default. If the user asks for patches, change one instrumentation site at a time, preserve fields used by existing filters/scorers/dashboards, and show the before/after shape inline in the report.

When stopping, the plan should make clear:

- the **top 3** changes the user should ship first
- which findings need human judgment (e.g., "is this field used by an internal dashboard?") before action
- which findings are blocked on access (e.g., automation rules visible only in UI without an API key)

## Required Output

- `bt-tracing-plan.md` — human-readable plan; the artifact the customer takes back to their codebase
- `bt-tracing-summary.json` — machine-readable summary keyed by dimension, with finding ids stable across re-runs

If evidence is insufficient for a confident recommendation, write the finding with `confidence: low` and the exact follow-up command, code path, or UI screen needed to confirm.
