# Optimization Patterns

Use evidence from `bt` samples, `bt` config commands, and local code inspection before recommending changes.

## Evidence Levels

- **Measured**: directly derived from `bt sql`, `bt view`, exported rows, `bt scorers`, or `bt topics`.
- **Config-visible**: derived from code/config search or `bt topics config`; useful but may not prove actual runtime volume.
- **Advisory**: requires billing dashboard, Gateway provider config, org retention settings, or customer confirmation.

Mark each recommendation with one of these evidence levels.

## Logs and GB Ingest

Highest-confidence log-cost levers:

- Sample routine successful production traffic. Keep 100% logging for errors, incidents, low scores, critical workflows, and small traffic segments where complete coverage matters.
- Omit fields that are never used for debugging, search, evals, support, filters, dashboards, or audit.
- Truncate repetitive text fields and log full content only on demand.
- Summarize large payloads into compact metadata: counts, IDs, hashes, byte sizes, route, model, prompt version, selected snippets, and references.
- Deduplicate payloads repeated on parent and child spans. Keep the raw object once and log a stable reference elsewhere.
- Replace full retrieved document bodies with document IDs, chunk IDs, ranks, scores, and short snippets.
- Avoid logging embeddings or high-dimensional numeric arrays unless the vector itself is the object under test.
- Keep provider request/response logging and normalized trace logging from duplicating the same large data.
- Reduce eval/dataset payload size when experiments store full production artifacts unnecessarily.
- Reduce unnecessary span depth. Not every function call needs a span; deep traces with full I/O at each level multiply volume.

Customer-facing impact heuristics from the April 2026 guide:

- Routine traffic sampling from 100% to 10% can reduce routine log ingest by about 90%.
- Moving large affected payloads out of indexed trace bodies can reduce affected trace body size materially; verify with row samples instead of quoting this as guaranteed billable savings.
- Removing unnecessary fields/spans and fixing duplication are usually medium-effort, material savings opportunities when row samples show repeated payloads.

## JSONAttachment Pattern

Use `JSONAttachment` when a large JSON object is useful for debugging but not needed inline.

Python:

```python
from braintrust import JSONAttachment

span.log(
    input={
        "conversation": JSONAttachment(conversation, filename="conversation.json"),
        "conversation_summary": {
            "turns": len(conversation),
            "last_user_message": conversation[-1]["content"][:500],
        },
    },
    metadata={
        "conversation_id": conversation_id,
        "prompt_version": prompt_version,
    },
)
```

TypeScript:

```typescript
import { JSONAttachment } from "braintrust";

span.log({
  input: {
    conversation: new JSONAttachment(conversation, {
      filename: "conversation.json",
    }),
    conversation_summary: {
      turns: conversation.length,
      last_user_message: conversation.at(-1)?.content?.slice(0, 500),
    },
  },
  metadata: {
    conversation_id: conversationId,
    prompt_version: promptVersion,
  },
});
```

Keep summary fields inline if they are used in filters, scorers, eval slicing, dashboards, or incident triage. Good candidates include chat transcripts, retrieved documents, tool call results, raw API responses, and large structured payloads.

## RAG Logging Pattern

Prefer:

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

Avoid logging every full document body, embedding, HTML page, PDF text, and raw retriever response on every span.

## Tool Output Pattern

For large tool responses:

- Inline status, latency, row counts, error code, and a small preview.
- Attach or externally store the raw response only when needed.
- Log a stable hash to correlate duplicates.

## Metadata Pattern

Metadata should be filterable and compact. Avoid dumping entire request bodies, user profiles, retrieved docs, provider payloads, or config trees into `metadata`.

Good metadata:

```json
{
  "customer_tier": "pro",
  "route": "support_agent",
  "model": "gpt-4.1",
  "prompt_version": "2026-04-30",
  "retrieved_doc_count": 10,
  "raw_payload_sha256": "..."
}
```

## Scorer Optimization

Scorer costs have two parts:

- Braintrust platform score count.
- Additional provider tokens for LLM-as-judge scorers; these are measured from scorer/LLM spans when logged.

Optimization levers:

- Lower online scorer `sampling_rate` for high-volume apps. Start with 1-10% for routine traffic and increase only when coverage is statistically or operationally necessary.
- Apply scorers to root spans or named spans only with `apply_to_root_span` and `apply_to_span_names`.
- Use `btql_filter` to score only traces that matter, such as production traffic, enterprise customers, errors, specific routes, or low-confidence outputs.
- Use `skip_logging` when scorer spans are not needed for debugging; otherwise scorer logging can add log volume.
- Replace LLM-as-judge with code-based checks for deterministic criteria: JSON schema validity, regex/keyword checks, length constraints, exact match, string distance, required citations, valid tool calls, and business-rule checks.
- Consolidate multiple LLM-as-judge dimensions into fewer calls when the same context is sent repeatedly.

Keep LLM-as-judge when the dimension is genuinely subjective: helpfulness, coherence, factuality, safety, style, or complex rubric grading.

## Topics as a Cost Lever

Use Topics when the customer is trying to understand production shape rather than score every response.

Good Topics use cases:

- Categorize traffic by user intent, task, issue, sentiment, route, or failure mode.
- Discover emerging production patterns.
- Feed dataset curation and targeted scorer rules.
- Get broad coverage cheaply before applying narrow scorers.

Keep scorers when the customer needs:

- Numeric quality scores.
- Hard quality gates.
- Regression detection on known quality metrics.
- Fine-grained grading that requires a rubric.

Cost-smart playbook:

1. Use Topics to classify broad traffic patterns.
2. Use topic classifications to drive `btql_filter` or span-name filters.
3. Apply code-based scorers broadly where cheap.
4. Apply LLM-as-judge scorers narrowly with low sampling.

## Gateway and Provider Spend

Gateway optimizations reduce provider cost, not Braintrust processed-data ingest by themselves.

Recommend Gateway caching when repeated deterministic LLM calls are visible in code or logs:

```text
x-bt-use-cache: auto
x-bt-cache-ttl: 86400
```

Use `always` only when the application can safely reuse responses despite non-deterministic parameters.

High-impact candidates:

- Repeated classification/extraction with fixed prompts.
- Embeddings for unchanged documents.
- Idempotent moderation or structured extraction calls.

Recommend provider routing when code/config shows multiple provider endpoints and routine tasks can use a cheaper endpoint:

```text
x-bt-endpoint-name: <endpoint>
```

Use `x-bt-used-endpoint` response headers or logged metadata to verify routing when available.

For realtime/audio-heavy workloads, recommend `x-bt-compress-audio: true` when audio attachments are being logged and quality tradeoffs are acceptable.

## Experiments and Datasets

Cost-aware experiment guidance:

- Start with small, representative datasets before scaling runs.
- Add real production failures and high-signal edge cases rather than generic bulk rows.
- Prefer one larger well-configured run over many redundant small runs when setup/prompt/scorer work is repeated.
- Segment results by topic, route, customer tier, or failure mode so scorer budget focuses on cases that still fail.
- Avoid storing full production artifacts in datasets when IDs, expected outputs, summaries, or curated failure snippets are sufficient.

## Recommendation Confidence

- High: `bt` sample shows a specific path/scorer/model dominates and code/config inspection confirms how it is produced.
- Medium: `bt` sample shows a large driver but business need or config is unclear.
- Low: only code/config pattern or only customer-provided heuristic is available.
