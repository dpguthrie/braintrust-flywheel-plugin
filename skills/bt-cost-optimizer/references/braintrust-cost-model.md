# Braintrust Cost Model

These notes combine local research in `~/repos/braintrust` with the customer cost-optimization guide supplied for this skill. Treat prices as plan/customer-specific unless the user confirms the applicable contract.

## What `bt` Can Derive

The `bt` CLI can directly help with:

- Production log row samples and counts through `bt sql` against `project_logs(...)`.
- Experiment and dataset row samples through `bt sql` against `experiment(...)` and `dataset(...)`.
- Scorer definitions through `bt scorers list`.
- Scorer span volume and scorer LLM token usage when scorer spans are logged in project logs.
- Topics status and config through `bt topics status` and `bt topics config`.
- Topic/facet traces when those spans are present in project logs.
- LLM token usage by model when LLM spans include `metrics.prompt_tokens`, `metrics.completion_tokens`, and model metadata.

The `bt` CLI usually cannot fully derive:

- Exact billing ledger totals and negotiated plan rates.
- Gateway provider prices, cache hit-rate, endpoint routing, and retention policy unless the customer logs those fields or exposes config.
- Detached attachment body size after the fact if row samples only contain attachment references.
- Whether a field is business-critical for search, audit, dashboards, or incident response without customer/code context.

## Processed Data / Logs

- `docs/plans-and-limits.mdx` defines processed data as total bytes ingested across logs, experiments, and datasets. The tooltip explicitly includes inputs, outputs, prompts, metadata, traces, spans, datasets, attachments, and related information.
- `app/app/(landing)/pricing/faq.tsx` describes processed data as data ingested when sent to Braintrust, not retained storage. Deleting data after exceeding quota does not lower processed data.
- `app/utils/billing/constants.ts` sets soft processed-data allowances at `1,000,000,000` bytes for Starter and `5,000,000,000` bytes for Pro.
- `app/app/api/webhooks/orb/handlers/usage-exceeded-utils.ts` maps the monthly logs ingested GB billable metric to internal `log_bytes` usage.

Insert-time accounting:

- `api-ts/src/run_log_data.ts` computes per-row input bytes as the compact JSON size of the merged row plus bytes for server-side replaced attachments.
- The same `inputRow.byteSize` is used for resource checks through `num_row_bytes`, internal telemetry counter `api.log_data.input_row_num_bytes`, and Orb `LogInsertedEvent.properties.log_bytes`.
- `app-schema/schema.sql` function `update_resource_counts_for_insert` sums `input.logs[org_id].num_row_bytes` into `num_log_bytes` or `num_log_bytes_calendar_months`.
- Tests in `tests/bt_services/test_resource_count.py` validate that project logs, feedback comments, and datasets can hit `num_log_bytes_calendar_months` limits based on payload bytes plus JSON overhead.

Customer guide pricing examples as of April 2026:

- Logs: $3/GB ingested for Enterprise, $4/GB for Starter.
- Use these only if the user asks for estimates and confirms the plan/rate, or pass rates as explicit assumptions.

## Attachments and JSONAttachment

- `docs/instrument/attachments.mdx` says `JSONAttachment` is uploaded separately, bypasses the 20 MB per-span payload limit, is not indexed, and remains viewable in the UI.
- TypeScript `JSONAttachment` lives in `sdk/js/src/logger.ts` and serializes JSON into an `Attachment` with `contentType: "application/json"`.
- Python `JSONAttachment` lives in `sdk-python/py/src/braintrust/logger.py` and serializes JSON into bytes with `content_type="application/json"`.
- `api-ts/src/run_log_data.ts` adds bytes for server-side auto-converted attachments such as inline base64 payloads through `replacedAttachmentBytes`.

Practical guidance: do not sell `JSONAttachment` as a guaranteed billable-byte reduction. Use it to reduce indexed payload size, avoid per-span payload failures, improve ingestion/UI behavior, and preserve large debug artifacts outside searchable fields. Pair it with actual byte reduction strategies when the goal is cost.

SDK availability from the customer guide:

- Python SDK: `JSONAttachment` available.
- TypeScript SDK: `JSONAttachment` available.
- Go SDK: binary attachments available in v0.6.1+; JSON Attachment support was planned in the guide and should be verified before recommending as available.

## Scorers

Customer guide pricing examples as of April 2026:

- Braintrust scorer platform fee: $1.50 per 1,000 scores for Enterprise, $2.50 per 1,000 scores for Starter.
- LLM-as-judge scorers also consume provider tokens; these provider costs are separate from the Braintrust score fee.

What to measure:

- Count scorer spans with `span_attributes.purpose = 'scorer'`.
- Count LLM judge scorer calls with both `span_attributes.purpose = 'scorer'` and `span_attributes.type = 'llm'`.
- Sum `metrics.prompt_tokens` and `metrics.completion_tokens` by `metadata.model`.
- Inspect scorer config/code for `sampling_rate`, `apply_to_root_span`, `apply_to_span_names`, `btql_filter`, and `skip_logging`.

Optimization implications:

- Reducing sampling rate and filtering scored spans directly reduces scorer count.
- Replacing LLM-as-judge with code or Autoevals can reduce provider token cost and often platform scoring volume if consolidated.
- `skip_logging` can reduce log volume from scorer spans when scorer trace debugging is not required.

## Topics

Topics are a cost lever when the customer is using scorers for broad categorization rather than precise quality scoring.

What `bt` can inspect:

- `bt topics status --json`
- `bt topics status --full --json`
- `bt topics config --json`
- recent trace counts through `project_logs(..., shape => 'spans')`
- facet/topic spans if they are present in project logs

Customer guide model:

- Topics answer "what kind of request is this?" and discover production shape.
- Scorers answer "how good is this output?" and provide numeric quality scores.
- Topics can classify broadly and feed targeted scorer filters, reducing LLM-as-judge coverage requirements.

## Gateway and Provider Spend

Gateway optimizations primarily reduce provider cost, not Braintrust processed-data ingest.

Relevant guide details:

- Response caching can use `x-bt-use-cache: auto` or `always`.
- Cache TTL is set with `x-bt-cache-ttl`.
- Provider routing can use `x-bt-endpoint-name`; the response header `x-bt-used-endpoint` confirms the used provider when available.
- Realtime audio logging can use `x-bt-compress-audio: true` to reduce audio attachment storage.

What to measure with `bt`:

- Token usage by model from LLM spans.
- Cache/routing metadata only when the application logs those headers or Gateway metadata.

What requires code/config review:

- Whether calls are deterministic enough for caching.
- Whether cheaper endpoints are configured.
- Whether audio compression is safe for the workload.

## Data Retention

Retention can reduce long-term storage cost but does not fix current-month processed-data ingest already incurred. Treat retention recommendations as advisory unless the user provides org retention/billing settings.

Typical recommendation:

- Keep production logs long enough for support and audit needs.
- Use shorter retention for dev experiments.
- Export to customer-owned cold storage before purging when audit/debug requirements require it.
