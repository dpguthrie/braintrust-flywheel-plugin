# Data Shape Patterns

What goes inline, what goes to `JSONAttachment`, what becomes a reference, and what gets dropped. This is the dimension most directly tied to ingest cost and span-size limits, but the doctor frames it as "what's the right shape for *this* data, given how the customer will use it".

For deeper byte-by-byte accounting, the [`bt-cost-optimizer`](../../bt-cost-optimizer/SKILL.md) skill runs a dedicated row analyzer. This file covers the shape decisions; route to that skill when the question becomes "how much will this save".

## Decision Rule

For every large field on a span, ask:

1. **Is it queried or filtered on in `bt sql`, dashboards, or scorer filters?** → Keep inline, in compact form.
2. **Is it read by a scorer or eval?** → Keep inline.
3. **Is it useful only for debugging?** → `JSONAttachment` or external reference, keep a summary inline.
4. **Is it duplicated on multiple spans?** → Keep on one span; reference by id elsewhere.
5. **Is it never actually opened in the UI or by a scorer?** → Stop logging it.

This is the same hierarchy `bt-cost-optimizer` uses; the doctor applies it on a per-finding basis rather than aggregating bytes globally.

## Common Oversized Fields

### Full retrieved documents on every span

Pattern: each LLM span gets the entire retrieved-context block inline, often 50–200 KB. Often the parent retrieval span *also* has the same documents.

Recommend:

```json
{
  "retrieval": {
    "query": "user question",
    "top_k": 10,
    "documents": [
      {"id": "doc-1", "chunk_id": "c1", "rank": 1, "score": 0.83, "snippet": "first 500 chars"}
    ]
  }
}
```

Keep ids, ranks, scores, and short snippets inline. The full body lives in the retrieval span (once) or in `JSONAttachment` if it needs to be opened in the UI.

### Raw provider request/response duplicated with normalized trace

A common bug: the customer logs both the raw HTTP request/response from OpenAI and a normalized `messages`/`output` view, identical content twice. Detection: span has both `raw_response` (or `provider_response`) and `output` fields with large overlapping content.

Fix: pick one. If support/debugging requires the raw form, put it in `JSONAttachment` and keep the normalized view inline for search and scoring.

### Embeddings and high-dimensional arrays

Embeddings are almost never useful inline. Log the embedding model and a hash if needed for cache lookups; do not log the vector unless the embedding itself is the artifact under test.

### Tool outputs with full body

Tool spans often dump multi-MB JSON (search results, database row sets). Recommend the tool-output pattern:

```json
{
  "tool": "search_orders",
  "status": "ok",
  "latency_ms": 412,
  "row_count": 132,
  "preview": [/* first 3 rows */],
  "raw_sha256": "..."
}
```

Attach the raw body or store it externally only when actually needed.

### Metadata used as a payload dump

The metadata column is for filterable scalars, not blobs. The doctor flags rows where any single `metadata.*` field exceeds a few KB or is a deeply nested object containing the same content as `input`/`output`. Move blobs out of metadata.

## Duplication Across Parent and Child Spans

Trace structure makes it easy to over-log: the parent span's `input` contains the user message, then every child re-logs the same message in its own input. Result: 5× the byte count for no analytic value.

Detection inside `analyze-tracing.py`:

- Hash compact-JSON of every `input`/`output` on every span.
- If the same hash appears on a parent and ≥1 child, count the duplicated bytes.

Fix: log the user input once on the root span and have child spans log only their delta (the prompt template, the tool arguments, the retrieved docs they touched).

## JSONAttachment Mechanics

`JSONAttachment` (Python and TypeScript SDKs) uploads JSON as a separate object that bypasses the 20 MB per-span payload limit. It remains viewable in the UI but is not indexed for search.

**Use it for:** transcripts that must remain available for debug but are too big to keep inline; raw provider responses kept for audit; large retrieved-context bodies; large tool outputs.

**Do not promise it as guaranteed billable-byte savings.** Processed-data accounting includes the attachment bytes; `JSONAttachment` reduces *indexed* trace body size and avoids per-span payload failures. Pair it with actual byte reduction (omit/sample/summarize) when the goal is cost. The [`bt-cost-optimizer`](../../bt-cost-optimizer/SKILL.md) skill quantifies this against the customer's actual project.

SDK availability: Python and TypeScript. For Go, recommend `JSONAttachment` only after verifying current SDK support in `repos/braintrust-sdk-go/` or the published docs.

## Span Depth and Volume

Too few spans hides structure; too many overwhelms the UI and inflates cost.

**Heuristics the doctor uses:**

- Median spans per trace > ~50 and most spans wrap trivial functions → flag for span-volume review.
- Single-span traces for multi-step agents → recommend at least separating retrieval, LLM, and tool steps.
- Deepest path > ~10 levels for a request that the customer describes as "simple" → likely over-instrumentation.

These are rules of thumb. Always show the customer the actual trace before recommending changes — what looks deep on paper may be the correct shape for their workflow.

## Sampling

The biggest non-structural lever on log volume is sampling routine traffic:

- Keep 100% logging for errors, low-score traces, incidents, critical workflows, and small traffic segments.
- Sample routine successful traffic at 10% (or lower).

The doctor surfaces this as a recommendation only when:

- Routine traffic dominates the project log volume.
- The customer is not already sampling at the application level.
- No regulatory/audit constraint forces full retention.

For exact savings estimates and existing sampling-rate detection, route to `bt-cost-optimizer`.

## Reference Pattern: RAG Logging

A correctly shaped RAG span set:

- **Root (`chat.handle_request`)**: input = user message; output = final assistant text; metadata = `{user_id, route, prompt_version, retrieved_doc_count}`.
- **Child (`retrieve.documents`)**: input = query; output = compact docs (id, rank, score, snippet); attachment = full bodies if needed.
- **Child (`llm.completion`)**: input = `{messages, model}`; output = assistant message; metrics = token counts; metadata = `model`, `temperature`.
- **Child (`tool.<name>`)** (if any): input = arguments; output = compact result with preview + hash; attachment = raw body if needed.

Use this as the comparator when reviewing a customer's RAG instrumentation.
