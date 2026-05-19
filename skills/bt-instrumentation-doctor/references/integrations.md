# Integrations Reference

When a customer is using a popular framework or provider, the right answer is almost always "use the official integration" rather than hand-rolled spans. This file is the doctor's working index of what exists, the recommended entry point, and the questions to ask before recommending it.

Always confirm against the live docs at <https://www.braintrust.dev/docs/integrations> before recommending a specific helper to a customer — packages and call signatures change.

## Entry points

Two complementary entry points handle most cases:

- **Auto-instrumentation** (Python and Ruby today, growing): `braintrust.auto_instrument()` patches common LLM clients and frameworks at import time. Pair with `braintrust.init_logger(project=...)`. See [Trace LLM calls](https://www.braintrust.dev/docs/instrument/trace-llm-calls).
- **Explicit wrappers**: `wrap_openai` / `wrapOpenAI`, `wrap_anthropic`, `wrapAISDK`, etc. Better when the customer wants surgical control or auto-instrument isn't available for the SDK.

If the customer is on a recent Python SDK and using a supported provider/framework, prefer auto-instrumentation. If they're on TypeScript, prefer the explicit wrapper that matches their LLM SDK.

## AI Providers

All major providers are supported. The integration page (`integrations/ai-providers/<provider>.mdx`) shows the recommended Braintrust pattern for each.

| Provider | Doc | Notes |
|---|---|---|
| OpenAI | `ai-providers/openai.mdx` | Python: `wrap_openai(client)` or `auto_instrument()`. TypeScript: `wrapOpenAI(client)`. |
| Anthropic | `ai-providers/anthropic.mdx` | Python: `wrap_anthropic(client)` or `auto_instrument()`. |
| Gemini / Google | `ai-providers/gemini.mdx`, `ai-providers/google.mdx` | |
| AWS Bedrock | `ai-providers/bedrock.mdx` | |
| Azure OpenAI | `ai-providers/azure.mdx` | |
| Mistral | `ai-providers/mistral.mdx` | |
| Together / Groq / Fireworks / Cerebras / Perplexity / xAI / Cohere / Databricks / Replicate / Baseten / Lepton / HuggingFace / OpenRouter | `ai-providers/<name>.mdx` | OpenAI-compatible providers typically use `wrap_openai`/`wrapOpenAI` against the provider's base URL. |
| Custom (BYO endpoint) | `ai-providers/custom.mdx` | |

Doctor question: is the customer calling the provider HTTP API directly with `requests` / `fetch`? If yes, recommend the provider's SDK + Braintrust wrapper — direct HTTP calls miss model and token metrics.

## Agent Frameworks

| Framework | Doc | Recommended entry |
|---|---|---|
| OpenAI Agents SDK | `agent-frameworks/openai-agents-sdk.mdx` | |
| LangGraph | `agent-frameworks/langgraph.mdx` | Python: `braintrust.auto_instrument()` patches LangChain callbacks (which LangGraph uses). TypeScript: `@braintrust/langchain-js`. |
| CrewAI | `agent-frameworks/crew-ai.mdx` | |
| Pydantic AI | `agent-frameworks/pydantic-ai.mdx` | |
| Mastra | `agent-frameworks/mastra.mdx` | |
| Strands | `agent-frameworks/strands-agent.mdx` | |
| OpenRouter Agent | `agent-frameworks/openrouter-agent.mdx` | |
| Claude Agent SDK | `agent-frameworks/claude-agent-sdk.mdx` | |
| Google (ADK / similar) | `agent-frameworks/google.mdx` | |
| AgentScope | `agent-frameworks/agentscope.mdx` | |
| AutoGen | `agent-frameworks/autogen.mdx` | |
| LiveKit Agents | `agent-frameworks/livekit-agents.mdx` | |

Doctor question: is the customer hand-rolling `@traced` decorators around each agent node when their framework has a Braintrust integration? Recommend the integration — it captures graph/node/tool structure automatically and stays current as the framework evolves.

## SDK Integrations

| SDK / Library | Doc | Recommended entry |
|---|---|---|
| Vercel AI SDK | `sdk-integrations/vercel.mdx` | `wrapAISDK(ai)` returns wrapped `generateText`, `streamText`, etc. Tool calls and tool results auto-captured. |
| LangChain | `sdk-integrations/langchain.mdx` | Python: `braintrust.auto_instrument()`. TypeScript: `@braintrust/langchain-js` callback handler. |
| LlamaIndex | `sdk-integrations/llamaindex.mdx` | |
| Instructor | `sdk-integrations/instructor.mdx` | |
| LiteLLM | `sdk-integrations/litellm.mdx` | |
| DSPy | `sdk-integrations/dspy.mdx` | |
| Firebase Genkit | `sdk-integrations/firebase-genkit.mdx` | |
| Agno | `sdk-integrations/agno.mdx` | |
| OpenTelemetry | `sdk-integrations/opentelemetry.mdx` | Go is OTel-native; TypeScript/Python can also push OTel spans into Braintrust. |
| Traceloop | `sdk-integrations/traceloop.mdx` | |
| Temporal | `sdk-integrations/temporal.mdx` | |
| Cloudflare | `sdk-integrations/cloudflare.mdx` | |
| Apollo GraphQL | `sdk-integrations/apollo-graphql.mdx` | |
| Cloudwego Eino | `sdk-integrations/cloudwego-eino.mdx` | |
| Ruby LLM | `sdk-integrations/ruby-llm.mdx` | |
| TrueFoundry | `sdk-integrations/truefoundry.mdx` | |
| LangSmith | `sdk-integrations/langsmith.mdx` | Migration shim — useful when the customer is moving off LangSmith. |
| Pytest / Vitest / Node test runner | `sdk-integrations/{pytest,vitest,node-test-runner}.mdx` | Test-runner integrations for offline evals. |

## How to use this reference in a review

1. From `package.json` / `pyproject.toml` / `go.mod`, list the customer's framework and provider dependencies.
2. Cross-reference against the tables above. For each match, ask: "are they using the recommended Braintrust entry point?"
3. Grep their code for the patterns in `code-search-patterns.md` to confirm.
4. If they're hand-rolling spans where an integration exists, recommend the integration with a link to the matching `integrations/<group>/<name>.mdx` doc. Cite the file path in the finding.
5. If they're using a provider with no SDK (raw HTTP), recommend moving to the provider's SDK + Braintrust wrapper so model and token metrics land in spans.

## Anti-Patterns

| Pattern | Why it's a problem | Fix |
|---|---|---|
| `@traced` decorators wrapping each LangGraph node | Duplicates what the LangChain integration already does; risks divergent span shapes | `braintrust.auto_instrument()` (Python) or `@braintrust/langchain-js` (TS); remove the manual decorators |
| Raw `openai.OpenAI()` client with no Braintrust wrapper | Loses `metadata.model` and token metrics on LLM spans | `wrap_openai(client)` / `wrapOpenAI(client)` |
| Vercel AI SDK with custom `traced()` around every `generateText` | Reinvents `wrapAISDK`; misses tool-call structure | `wrapAISDK(ai)` once at module scope |
| Go service calling provider HTTP directly with no OTel | Cost dashboards blind; no model attribute | Use provider SDK + OTel; set `gen_ai.request.model` and `gen_ai.usage.*_tokens` |
| Custom LangSmith → Braintrust shim | Maintenance burden | Use `sdk-integrations/langsmith.mdx` migration path |
