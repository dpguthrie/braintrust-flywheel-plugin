# Code Search Patterns

Recipes for locating instrumentation in a customer's repo so every finding can cite a file path. Use `git grep` when the repo is git-managed; fall back to `rg` otherwise.

## Language Detection

```bash
# Quick signal of which SDKs are in play
ls package.json pyproject.toml requirements.txt requirements*.txt go.mod 2>/dev/null
git grep -lE '^"braintrust"|braintrust ?=|braintrust/v[0-9]+' || true
```

If multiple SDKs are present (e.g., a TS web app + Python service), search each.

## Python

```bash
# Logger init + tracing decorators
git grep -nE 'init_logger|@traced|start_span|span\.log|Eval\(|JSONAttachment' || true

# LLM client wrappers and provider calls
git grep -nE 'wrap_openai|wrap_anthropic|braintrust\.init|openai\.OpenAI|Anthropic\(' || true

# Scorer definitions and registrations
git grep -nE 'def\s+\w+_scorer|Scorer\(|autoevals\.|@traced.*scorer' || true

# Session / thread correlation
git grep -nE 'session_id|conversation_id|thread_id|user_id' -- '*.py' || true
```

What to look for:

- `init_logger(...)` called in a library imported by tools — usually means tool spans don't inherit the caller's project.
- `@traced` decorators with no `name=...` — leads to anonymous span names.
- `start_span(...)` without a matching `end()` or context manager — risk of leaked open spans.
- `parent=` keyword usage that does or doesn't match the session-root pattern.

## TypeScript / JavaScript

```bash
# Logger init + tracing wrappers
git grep -nE 'initLogger|wrapTraced|wrapAISDK|wrapOpenAI|startSpan|span\.log\(' || true

# Vercel AI SDK integration points
git grep -nE 'streamText|generateText|generateObject|streamObject' || true

# JSONAttachment and large-payload sites
git grep -nE 'JSONAttachment|new Attachment' || true

# Session/thread correlation
git grep -nE 'sessionId|conversationId|threadId|userId' -- '*.ts' '*.tsx' '*.js' '*.jsx' || true

# Eval/Scorer files
git grep -nE 'Eval\(|Scorer\b|defineScorer' || true
```

What to look for:

- `wrapTraced(async function () { ... })` with no name — produces empty span names. Recommend `wrapTraced(async function namedFn() {...})` or `traced(async (span) => {...}, { name: "..." })`.
- `initLogger` called inside a per-request handler instead of module scope — risk of repeated init.
- `previous_response_id` usage on OpenAI calls without a local messages array — breaks Thread view.
- Conversation handlers that call `traced(...)` per turn without a `parent` from a session export.

## Go

```bash
# OTel + Braintrust gateway usage
git grep -nE 'otel\.Tracer|tracer\.Start|SetAttributes|braintrust\.tags|braintrust\.' || true

# Manual span management
git grep -nE 'span\.End|RecordError|SetStatus' || true

# Provider clients
git grep -nE 'openai-go|anthropic|gen_ai\.' || true
```

What to look for:

- `tracer.Start(ctx, ...)` without `defer span.End()`.
- LLM calls without `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` attributes — Braintrust loses model/token tracking.
- New tracers created per request instead of reusing one.

## Cross-Language Checks

### Duplicate logging

Look for places that log the same payload twice (provider raw + normalized):

```bash
git grep -nE 'raw_response|provider_response|provider_request|raw_request' || true
```

### Embeddings logged inline

```bash
git grep -nE 'embedding|embed_query|embed_documents' || true
```

Inspect callers — if the resulting vector is passed into `span.log(input=...)` or similar, that's an inline-embedding defect.

### Tool runtimes

```bash
git grep -nE 'def\s+\w+_tool|class \w+Tool|registerTool|tools:\s*\[' || true
```

Check whether tools share the agent's tracing context (typically by being called inside an already-traced agent function) or whether they call `init_logger` / `initLogger` themselves.

## Mapping Findings to Files

For every analyzer finding tied to a span name (e.g., `tool.search_orders`), run the matching grep in the customer's repo and include the file:line in the report:

```bash
git grep -nE 'tool\.search_orders|search_orders' || true
```

If a finding has no code match (e.g., spans named after auto-instrumentation), say so explicitly and recommend the customer add an explicit name or wrapper.

## Configuration Files to Check

- `package.json` / `pyproject.toml` / `requirements.txt` / `go.mod` — SDK versions. Recommend upgrades only when a known fix or feature is required and verified against the changelog.
- `.bt/config.json` — active project and project ID. If missing, the customer should run `bt setup`.
- `.env` / environment templates — look for `BRAINTRUST_API_KEY`, `BRAINTRUST_API_URL`, `BRAINTRUST_PROJECT` placement. Misuse (committed keys, mismatched project names) is a common defect.

## Anti-Patterns to Flag

| Pattern | Where to look | Why it matters |
|---|---|---|
| `init_logger` / `initLogger` inside a tool or library | tool implementations | Breaks span inheritance, fragments traces. |
| `@traced` / `wrapTraced` without `name=...` | handler/wrapper sites | Produces blank or anonymous span names. |
| `messages = []` mutated then dropped before logging | chat handlers | Thread view loses history. |
| Direct `console.log` / `print` of large payloads alongside `span.log` | mixed logging sites | Customer is double-storing data; pick one. |
| `previous_response_id` with no local messages mirror | OpenAI Responses calls | Thread view contains only one turn. |
| Span body construction that pulls in entire request / DB row | logging helpers | Inline payload bloat. |
