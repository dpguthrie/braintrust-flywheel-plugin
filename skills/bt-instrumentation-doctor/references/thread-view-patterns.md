# Thread View Patterns

How to instrument multi-turn conversations so the Braintrust Thread view, trace-level scorers, and conversation grouping all work.

## What Thread View Needs

The Thread tab on a trace renders a conversation timeline by stitching together messages across spans inside one trace. For this to work:

1. All turns of one conversation belong to **one trace** (one shared `root_span_id`).
2. Each turn's LLM span (or `traced()` step) carries the full message history that was sent on that turn, not just the latest user message.
3. The root span represents the session/conversation, not a single turn.

If any of these is violated, the Thread view falls back to whatever subset of messages it can find, and trace-level scorers that call `get_thread()` see an incomplete conversation.

## Anti-Patterns

### Each turn is its own root span

The most common defect. Symptoms:

```sql
SELECT metadata.session_id, COUNT(DISTINCT root_span_id) AS roots
FROM project_logs('<PROJECT_ID>', shape => 'spans')
WHERE created >= NOW() - INTERVAL 7 day
  AND metadata.session_id IS NOT NULL
GROUP BY metadata.session_id
HAVING COUNT(DISTINCT root_span_id) > 1
ORDER BY roots DESC
LIMIT 20
```

If many sessions have N roots each, the customer is creating a fresh trace per turn. Thread view never sees more than one message.

### `previous_response_id` (OpenAI) with no local message history

When OpenAI's `previous_response_id` parameter manages conversation server-side, the application only sends the current user turn. Braintrust traces what is sent; only the latest turn appears. The Thread view looks empty after turn 1.

Fix: maintain a `messages` array client-side and send the full history on every call. The provider can still use `previous_response_id` for context — Braintrust just needs the messages locally to log them.

### `messages` array thrown away after the LLM call

Some applications append the assistant response, then truncate or drop the array before logging. Recommend logging `messages` as the LLM span's `input` (with the assistant turn appended for `output`).

### Tool runtimes that re-initialize a logger

If the agent calls a tool that imports `braintrust` and calls `init_logger(...)` again with a default project, the tool's spans land in a different project or as new roots. Symptom: tool spans missing from the main trace.

Fix: tool runtimes should inherit the caller's logging context (don't call `init_logger` inside library code), or use explicit `parent` propagation.

## Session-Root Span Pattern

The canonical pattern for multi-turn chat is one session-root span with each turn attached as a child.

### Python

```python
from braintrust import init_logger, traced, start_span

logger = init_logger(project="My Project")

# At session start:
session_span = start_span(name="chat.session")
session_root_id = session_span.export()
session_span.end()
# Persist session_root_id (cookie, session store)

# On each turn:
@traced(name="chat.turn")
def handle_turn(user_message: str, session_root_id: str):
    # Children attach to the session via parent=session_root_id when needed.
    # If using @traced, pass parent via the underlying span APIs.
    ...
```

For request handlers, the Python SDK accepts `parent=session_root_id` on `start_span(...)` and on the `Eval()` test-case level. Verify in `repos/braintrust/sdk-python/py/src/braintrust/logger.py` before recommending a specific keyword to the customer.

### TypeScript

```typescript
import { traced } from "braintrust";

// At session start:
let sessionRootId: string | undefined;
await traced(async (span) => {
  sessionRootId = await span.export();
}, { name: "chat.session" });
// Persist sessionRootId — an httpOnly cookie works well for Next.js.

// On each turn:
await traced(async (span) => {
  // The full messages history is the input; the assistant reply is the output.
  span.log({ input: { messages }, output: assistantMessage });
}, { name: "chat.turn", parent: sessionRootId });
```

Cosmetic note: ending the session span immediately gives it a near-zero duration in the waterfall. This is harmless — the backend builds the tree from IDs in the exported handle. If a clean end time matters, call `updateSpan({ exported: sessionRootId, metrics: { end: ... } })` at session close and flush.

### Vercel AI SDK (`wrapAISDK`)

`wrapAISDK` integrates with the Vercel AI SDK so each `streamText` / `generateText` call logs an LLM span. Combined with the session-root pattern above, every turn becomes a child of the session span and Thread view stitches the full conversation.

## Required Metadata for Conversation Grouping

Even with one root per session, the Thread view and dashboards need a small set of metadata to be useful:

- `metadata.session_id` — stable conversation identifier (helpful for cross-trace correlation if a single conversation has to span multiple traces).
- `metadata.user_id` (or hash) — for slicing.
- `metadata.turn_index` — integer turn counter; useful for dashboards.
- `metadata.role` — on per-turn spans, indicates whose turn it represents.

Log these once at the root and re-log on key child spans only where filtering on them inside the span list is required.

## Topics, Threads, and the Logs UI

When Topics is enabled, topic labels attach to the trace and are queryable from `project_logs`. Combined with one-trace-per-session:

- The logs list shows one row per conversation, labeled with the topic.
- Trace-level scorers can use both the messages and the topic in their rubric.
- Automation filters can route scorers by topic without re-running classification inside the scorer.

If the customer is doing LLM-as-judge classification per turn to label conversations, recommend Topics with a thread-aware classifier instead. See `scorer-setup-patterns.md` → Topics as a Pre-Scorer Filter.

## Detection Summary

The doctor flags conversation/thread issues when:

- A `session_id`-style metadata field exists but maps to many `root_span_id`s.
- Root spans contain a single user/assistant message pair where the full history is available client-side.
- The customer asks about Thread view but no `session_id` or equivalent appears in metadata.
- Tool-call spans are roots instead of children of an agent step.
- The customer uses `previous_response_id` and the trace contains only the latest turn.

Each detection should cite at least one trace id (so the user can open Thread view themselves) and the code location where the session/turn boundary is established.
