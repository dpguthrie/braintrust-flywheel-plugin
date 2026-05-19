# Tracing Best Practices

The structural and stylistic patterns the doctor looks for when reviewing a customer's traces. Each pattern lists a failure signal, what the customer should do instead, and where to find it in evidence.

## Span Hierarchy

A trace should answer one question: "what did the application do for one user request?" Root span captures the user-facing input and final output; child spans cover the steps that produced it.

**Healthy shape:**

```
root: chat.handle_request   input={user message}, output={final assistant text}
├── retrieve.documents      input={query}, output={doc ids, ranks, snippets}
├── llm.completion          input={messages, model}, output={response}, usage={tokens}
└── tool.lookup_order       input={order_id}, output={order summary}
```

**Failure signals:**

- Root span has empty or generic input/output (`{}`, "ok") while children carry the real payload. Scorers configured to look at the root will see nothing.
- Each LLM call is its own root span (no parent), so multi-step traces appear as N unrelated rows in `project_logs`.
- Function-level spans wrap every internal helper, producing 100+ spans for a trivial request. Trace view is unreadable and cost climbs.
- A single span carries the whole pipeline as one giant payload, so child timings, retries, and tool calls are invisible.

**Fixes (cite the SDK that matches the customer's code):**

- Python: wrap the request handler with `@traced` from `braintrust`, then let inner LLM/tool calls inherit context. Use `start_span(name=...)` for explicit named subspans.
- TypeScript: wrap the handler with `wrapTraced(...)`; use `traced(async (span) => { ... }, { name })` for explicit subspans.
- Go: open one `tracer.Start(ctx, "request.handle")` at the entry, propagate `ctx` through callees, and call `span.End()` on each tracer span. Braintrust ingests via OpenTelemetry.

## Root Span Inputs and Outputs

The Braintrust UI surfaces the root span on the logs list and feeds it to root-scoped scorers. Treat root input/output as the contract.

- Root input should be the user-visible request: the message, the structured task, or the API parameters that triggered the run.
- Root output should be the user-visible answer: the assistant message, the final tool result, or the structured response.
- If the system has post-processing (formatting, redaction, safety checks), log the *delivered* output on the root, not the pre-processed one.

**Failure signals from `bt sql`:**

```sql
SELECT id, input, output
FROM project_logs('<PROJECT_ID>', shape => 'summary')
WHERE created >= NOW() - INTERVAL 7 day
  AND (input IS NULL OR output IS NULL OR length(CAST(output AS VARCHAR)) < 5)
LIMIT 20
```

Many rows with `NULL` or near-empty root output usually mean the customer is logging only inside child spans and never propagating to the root.

## Span Names

Names are how the UI, scorer filters, and `apply_to_span_names` automations target work.

**Good names:**

- Stable verbs/nouns scoped to the operation: `retrieve.documents`, `llm.completion`, `tool.search_orders`, `agent.plan`.
- Consistent casing within a project. Pick one (snake or dot) and stick with it.

**Bad names:**

- Dynamic content in the name itself: `tool.search_orders(order_id=42)` — explodes name cardinality, breaks span-name filters, and bloats the analytics layer.
- Anonymous or auto-generated names from un-named wrappers (e.g., empty `wrapTraced(async function() {...})`) — produces blank or `anonymous` span names.
- Per-file framework names (e.g., `route.ts`, `handlers.py`) — fine for logs but useless for scorer scope.

**Detection query:**

```sql
SELECT span_attributes.name AS name, COUNT(*) AS calls
FROM project_logs('<PROJECT_ID>', shape => 'spans')
WHERE created >= NOW() - INTERVAL 7 day
GROUP BY name
ORDER BY calls DESC
LIMIT 100
```

Flag: high-cardinality names (one occurrence each), blank names, or names containing user data.

## Errors

Capture errors on the span where they happen, not (only) at the boundary. Braintrust surfaces `error` as a first-class column and routes it to filters, dashboards, and alerts.

- Python: raising inside a `@traced` function records the exception automatically. If you catch and recover, call `span.log(error=str(exc))` to keep visibility.
- TypeScript: same with `wrapTraced` / `traced`. Re-thrown errors are captured.
- Go (OTel): set `span.SetStatus(codes.Error, msg)` and `span.RecordError(err)` on failure paths.

**Failure signal:** all spans report success but the user-reported error rate is non-zero — usually means error swallowing in a wrapper.

```sql
SELECT COUNT(*) FROM project_logs('<PROJECT_ID>', shape => 'traces')
WHERE created >= NOW() - INTERVAL 7 day AND ANY_SPAN(error IS NOT NULL)
```

If the result is ~0 but the customer says they see failures, investigate error swallowing.

## Metadata

Metadata is for filterable, compact attributes the customer slices traces by. Keep it small and structured.

**Keep inline:**

- IDs and references: `user_id`, `customer_tier`, `request_id`, `prompt_version`, `route`, `experiment_name`.
- Model and runtime: `model`, `provider`, `region`, `temperature`, `top_p`.
- Counts and hashes: `retrieved_doc_count`, `tool_call_count`, `input_sha256`.
- Topic/facet labels and dataset splits used for slicing.

**Move out (to span body, attachment, or omit):**

- Full request/response payloads.
- Retrieved document bodies, HTML, PDFs, embeddings.
- Long prompt templates — log the version/hash, not the body.

**Failure signal:** average metadata bytes per span > a few KB, or metadata contains arrays > N items. The analyzer surfaces this.

## Model and Cost Capture

For LLM spans, Braintrust expects:

- `metadata.model` — the provider model identifier.
- `metrics.prompt_tokens`, `metrics.completion_tokens`, `metrics.total_tokens` — populated either by `wrapOpenAI` / `wrap_openai` / wrappers for Anthropic/AI SDK/etc., or by manual logging.

If these are missing, cost dashboards and `estimated_cost()` calculations are blind. Recommend the wrapper appropriate to the customer's SDK:

- Python: `wrap_openai(client)`, `wrap_anthropic(client)`, or the auto-instrumentation entry point.
- TypeScript: `wrapOpenAI(client)`, `wrapAISDK(...)` for Vercel AI SDK.
- Go: emit OTel attributes `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.request.model`.

**Detection:**

```sql
SELECT
  COUNT(*) AS llm_spans,
  COUNT(metrics.prompt_tokens) AS spans_with_prompt_tokens,
  COUNT(metadata.model) AS spans_with_model
FROM project_logs('<PROJECT_ID>', shape => 'spans')
WHERE span_attributes.type = 'llm' AND created >= NOW() - INTERVAL 7 day
```

If `spans_with_prompt_tokens` or `spans_with_model` is much less than `llm_spans`, instrumentation is incomplete.

## Trace Boundary Discipline

One run = one trace. The most common structural defect is fragmentation: every internal LLM call or tool call lives in its own root span, so the UI shows them as unrelated rows and scorers can't grade the whole interaction.

The skill flags this when:

- The same `metadata.session_id` (or equivalent customer-side correlation id) appears on N spans with N different `root_span_id` values.
- A multi-turn conversation produces a separate root span per turn instead of all turns sharing one root (see `thread-view-patterns.md`).
- Tool calls that happen inside an agent step produce their own root spans because the tool runtime initialized its own logger rather than inheriting context.

Fix patterns are in `thread-view-patterns.md` (for conversation sessions) and `scorer-setup-patterns.md` (for agent + tool runtimes).

## Reading the Customer's Code

When the doctor runs inside the customer's repo, pair each flagged finding with the code location. The recipes are in `code-search-patterns.md`. A finding without either a sample trace id or a file path is not actionable — downgrade its confidence or drop it.
