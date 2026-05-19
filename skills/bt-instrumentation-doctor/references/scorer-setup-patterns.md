# Scorer Setup Patterns

How online scorers, trace-level scorers, and span scope interact with trace structure. Use this reference whenever the customer's scorers are wrong, expensive, or graded at the wrong granularity.

## Scope Decisions

Every scorer answers a question about *some* portion of a trace. Pick the scope to match the question.

| Question | Scope | How to express it |
|---|---|---|
| "Is the final assistant answer good?" | Root span only | Online automation: enable **Root spans** (REST: `apply_to_root_span: true`); or trace-level scorer reading `output`. |
| "Did this tool call return a valid result?" | One named span | Online automation: set **Span names** to the tool span (REST: `apply_to_span_names: ["tool.search_orders"]`). |
| "Across the whole conversation, was the agent polite, did it stay on policy, did it reach a resolution?" | Whole trace | Trace-level scorer (`trace.get_spans()` / `trace.getSpans()` and `trace.get_thread()` / `trace.getThread()`). |
| "Is each LLM call producing well-formed JSON?" | All `type='llm'` spans | Online automation: filter on `span_attributes.type = 'llm'`; or in-eval code scorer checking output schema. |

**Failure signal:** scorer is enabled at trace level but checks only a leaf-span field; or scorer is per-span but the criterion describes the full conversation. Fix by changing scope, not by patching the scorer logic.

## Online Scorer Automation Fields

Fetch automations from `/v1/project_score`. The fields that govern scope and volume:

- `apply_to_root_span` — restricts execution to root spans only.
- `apply_to_span_names` — array of span names to match (empty = all spans).
- `filter` — SQL filter clause; required for any cost-aware sampling beyond "all traces".
- `sampling_rate` — float between 0 and 1.

Recommendation discipline:

- Never propose a sampling rate change without inspecting the *current* rate in `project_score`. If `BRAINTRUST_API_KEY` is unset, the rate must be confirmed in the UI under **Project → Logs → Score** first.
- Every online scorer execution writes a child span. There is no "skip logging" option. The only knobs that reduce scorer span volume are `sampling_rate`, `filter`, and scope (`apply_to_root_span` / `apply_to_span_names`).

## Trace-Level Scorers

Trace-level scorers are the right tool when the rubric depends on more than one span — for example, "did the agent ask for clarification before invoking the destructive tool?" or "was the conversation polite across all turns?".

The handler receives a `trace` argument that exposes:

- TypeScript: `await trace.getSpans({ spanType: ["llm"] })`, `await trace.getThread()`
- Python: `await trace.get_spans(span_type=["llm"])`, `await trace.get_thread()`
- Ruby: `trace.spans(span_type: "llm")`, `trace.thread`

`input`, `output`, `expected`, and `metadata` are auto-populated from the root span and passed alongside the trace.

**Prerequisite:** trace-level scoring requires a coherent trace. If the customer has fragmented spans into separate roots (see `tracing-best-practices.md` → Trace Boundary Discipline), trace-level scorers will only see one fragment. Fix the boundary problem before recommending a trace-level scorer.

**Detection (trace-level scorer would help):**

- The customer has multiple per-span LLM-as-judge scorers grading aspects of the same conversation. A single trace-level scorer is usually cheaper and more coherent.
- The customer is trying to score "tool sequence correctness" — inherently a multi-span property.
- The current scorer can't see the user's earlier message because it only looks at the LLM span input.

## LLM-as-Judge vs. Code Scorers

LLM-as-judge scorers are the dominant scorer-cost driver. Apply them only when the dimension is genuinely subjective.

**Replace with code:**

- JSON schema validity, regex/keyword presence, length constraints, exact match.
- Required-citations checks, valid-tool-call checks, format conformance.
- Number-of-tool-calls thresholds, latency thresholds.

**Keep as LLM judge:**

- Helpfulness, coherence, factuality, safety, style, complex rubric grading.

When the customer has 4–6 per-trace LLM judges grading semantically overlapping dimensions, recommend consolidation into one judge with a structured rubric output. This both reduces token cost and improves coherence.

## Scorer Span Hygiene

Every fired automation writes a child span at `span_attributes.purpose = 'scorer'`. Look for:

- Scorer span volume that dwarfs the application span volume — usually means a scorer is fanning across all spans when it should be root-only.
- Scorer LLM spans where `metadata.model` is the same expensive frontier model the customer uses in the agent itself. Judges typically don't need the highest-tier model.

Detection:

```sql
SELECT
  span_attributes.name AS scorer,
  COUNT(*) AS calls,
  metadata.model AS model
FROM project_logs('<PROJECT_ID>', shape => 'spans')
WHERE span_attributes.purpose = 'scorer'
  AND created >= NOW() - INTERVAL 7 day
GROUP BY scorer, model
ORDER BY calls DESC
LIMIT 50
```

Cross-check the `calls` column against the customer's expected scorer count (rate × eligible spans × window). A 10× mismatch usually means an automation has the wrong `apply_to_*` scope.

## Topics as a Pre-Scorer Filter

If the customer is using LLM-as-judge scorers to answer "what kind of request is this?", that's a Topics use case, not a scoring use case.

- Use Topics to classify request shape (intent, task, sentiment, failure mode).
- Use the resulting topic label in scorer `filter` clauses to grade only the cases that matter.

`bt topics status --json` and `bt topics config --json` show whether Topics is already configured. If it is and topic labels appear in spans, recommend wiring them into automation filters before adding more LLM judges.

## Scorer Coverage Rubric

A tracing review should not just ask "are the scorers configured well?" — it should ask "is the set of scorers sufficient to catch the ways this agent can fail?"

### Failure taxonomy

Most agent failures fall into one of these six categories. Treat them as the coverage checklist:

| Category | What it looks like | Typical scorer scope |
|---|---|---|
| Contradictions and unsupported claims | Output asserts X then ~X, or claims facts not present in retrieved evidence | Trace-level or root-scope LLM judge |
| Missing citations or weak grounding | Answer references no sources, or cites sources that don't support the claim | Span-scope on retrieval + LLM, or trace-level |
| Coverage gaps and incomplete reports | Output skips part of the asked-for structure (e.g., 3 of 5 sections) | Code scorer at root (format/structure check) |
| Wrong tool choice or wrong tool arguments | Agent calls the wrong tool, or right tool with malformed args | Span-scope on tool spans (code check on arg schema) |
| Loopiness, latency spikes, cost blowups | Tool call count exceeds a threshold, repeated identical calls, runaway tokens | Code scorer at root reading `metrics.*` and span counts |
| Formatting or report contract failures | Output violates schema, missing keys, wrong markdown structure | Code scorer at root (JSON schema / regex / structure) |

A project with multi-step agents and only one root-scope LLM-judge "is the answer good" scorer almost always has gaps in this matrix.

### Named span scores worth recommending

For agents with retrieval and tools, four span-scope scores cover most of the matrix above:

| Score | Scope | Implementation hint |
|---|---|---|
| Retrieval relevance | `retrieve.*` spans | Code or LLM judge against the documents returned; autoevals has `ContextRelevancy`, `ContextPrecision`, `ContextRecall`. |
| Grounding quality | LLM span on the synthesis step | Compare answer against retrieved evidence; autoevals has `Faithfulness`, `AnswerSimilarity`. |
| Tool correctness | `tool.*` spans | Code check on tool input schema; code check on tool output shape/error. |
| Verification rigor | Verifier/checker span (or trace-level) | Did the agent verify before delivering? Code rule: was a verification span present and successful? |

The doctor surfaces these as recommendations when the customer's automation list shows only root-scope or only LLM-as-judge "quality" scorers and the trace contains retrieval/tool/verification spans.

### Code scorers vs. LLM judges, by default

Per the customer-facing guidance: run code-based scorers broadly and judge scorers selectively. The default scorer layout for a well-instrumented agent looks like:

- Broad code scorers (cheap, run on every trace or high-rate sample): structure/contract, tool-arg schema, latency thresholds, tool-call counts, cost ceiling, citation presence.
- Selective LLM judges (lower sample rate, narrow filter): grounding quality, helpfulness, factuality, retrieval relevance.

When the customer's automation list is the inverse — judges everywhere, no code scorers — that's the first scorer-coverage finding.

## Common Defects and Fixes

| Defect | Symptom | Fix |
|---|---|---|
| Scorer reads root output but root output is empty | Scorer always returns null/0 | Either propagate the final output to root (preferred), or move the scorer to the leaf span that holds it. |
| Scorer applied to every span | Scorer span volume ~ total span volume | Add `apply_to_root_span: true` or `apply_to_span_names: [...]`. |
| Multi-turn quality scored per turn | Scores oscillate, conversation context invisible | Migrate to a trace-level scorer using `get_thread()`. |
| Two LLM judges grading near-identical dimensions | Double token spend | Consolidate into one judge with structured rubric. |
| Scorer LLM model = production LLM model | Disproportionate provider cost | Move judge to a cheaper, capable judge model. |
| Scorer logs are themselves huge | Scorer spans contain full transcripts | Reduce inputs sent to the judge; use only the fields the rubric needs. |
