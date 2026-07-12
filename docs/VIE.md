# VIE — VQB Intelligence Engine

Provider-agnostic HTTP gateway for LLM calls. Every AI request originating in the Strategy Factory backend flows through **VIE** — no provider SDK is imported anywhere in business logic.

## service surface

```
GET  /health               → { status, providers_total, providers_available, available:[...] }
GET  /providers            → { providers:[ { name, available, default_model, api_key_env } ] }
POST /generate             → { provider, model, output, usage?, task? }
POST /probe                → { results:[ { name, available, tested, ok, latency_ms?, model?, error? } ] }
```

## Operational dashboard (Providers page)

Admins hit `POST /api/admin/providers/probe` from the UI (Providers → **Probe all** or per-card **Probe**). Each probe:
- Sends a minimal prompt (`"ping"`, `max_tokens=5`, `temperature=0.0`) to the target provider.
- Measures wall-clock latency (ms).
- Captures the exact HTTP/auth error message on failure — surfaced inline on the card.
- Records the model actually served — useful for confirming a provider is on the version you configured.

The Providers page also aggregates counters: AVAILABLE (env-configured), OK LAST PROBE, FAIL LAST PROBE, NOT TESTED. All results are ephemeral (per-session in the browser) — no persistent probe history is stored today (Stage 2 opportunity).

`POST /generate` request body:

```json
{
  "prompt": "…",
  "task": "research|generation|validation|explanation|fast|default",
  "provider": "openai|anthropic|gemini|deepseek|groq|kimi",   // optional — overrides task routing
  "model": "gpt-4o-mini",                                     // optional — overrides provider default
  "system_message": "You are …",
  "temperature": 0.3,
  "max_tokens": 1024
}
```

Response is a normalized shape independent of the provider that served it.

## Providers

| Provider | env key | default model | notes |
|---|---|---|---|
| openai    | `OPENAI_API_KEY`    | `gpt-4o-mini` | gpt-5 family: temperature not sent |
| anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5-20250929` | messages API |
| gemini    | `GEMINI_API_KEY`    | `gemini-2.5-flash` | generateContent |
| deepseek  | `DEEPSEEK_API_KEY`  | `deepseek-chat` | OpenAI-compatible |
| groq      | `GROQ_API_KEY`      | `llama-3.3-70b-versatile` | OpenAI-compatible |
| kimi      | `KIMI_API_KEY`      | `kimi-k2` | Moonshot, OpenAI-compatible |

Each provider's default model can be overridden via `{PROVIDER}_MODEL` env var.

## Availability rule (contract)

- A provider is **available** ⇔ its API key env var is present **and** non-empty.
- Missing key → the provider is marked unavailable and **skipped** by the router. **No exception raised; no crash on boot.**
- If **zero** providers are available, `POST /generate` returns HTTP 503 with a clear message. The service itself stays up.

## Routing policy

- **Explicit provider:** if `provider` is set in the request, only that provider is tried. If unavailable → 503.
- **Task-based routing:** if `task` is set, VIE consults an in-memory preference list per task and tries providers in order, skipping unavailable ones. On provider error, the next one is tried (failover).
- **Default:** if neither is set, VIE uses the `"default"` preference list.

Default preferences (may be overridden via `VIE_TASK_MAP` env, JSON):

```json
{
  "research":     ["anthropic","openai","gemini","deepseek","groq","kimi"],
  "generation":   ["openai","anthropic","deepseek","gemini","groq","kimi"],
  "validation":   ["deepseek","openai","anthropic","gemini","groq","kimi"],
  "explanation":  ["anthropic","openai","gemini","deepseek","groq","kimi"],
  "fast":         ["groq","gemini","deepseek","openai","anthropic","kimi"],
  "default":      ["openai","anthropic","gemini","deepseek","groq","kimi"]
}
```

## Failure semantics

- Individual provider HTTP errors → try next in the preference list.
- All candidates fail → HTTP 502 with the last error message.
- No providers available for the requested routing → HTTP 503.

## Backend integration

Business code **must** use `app.vie.client.get_vie().generate(...)`. Direct imports of `openai`, `anthropic`, `google-genai`, etc. are forbidden in `backend/app/**`.

```python
from app.vie.client import get_vie, VIEUnavailable, VIEError

result = await get_vie().generate(
    prompt=user_prompt,
    task="research",
    system_message="You are a quantitative research assistant.",
    temperature=0.3,
    max_tokens=1024,
)
# → {"provider": "anthropic", "model": "claude-sonnet-4-5-…", "output": "...", "usage": {...}}
```

## Deployment

- Runs as a **separate container** (`factory-vie`) inside `vqb-network`.
- Not exposed publicly. Backend reaches it at `http://factory-vie:8100`.
- Provider keys are set via env only (never baked into images).
- Health endpoint `/health` is used by Docker's healthcheck and by the backend's `/api/readiness` aggregator.

## Extending VIE

To add a new provider:
1. Add a class under `vie/providers/<name>_p.py` extending `BaseProvider` with `name`, `api_key_env`, `default_model`, and `generate(...)`.
2. Register the class in `vie/registry.py` (`_ORDER`, `_CLASSES`, `_MODEL_ENV`).
3. Optionally add it to task preference lists in `vie/router.py`.
4. Add the env var to `.env.example` and Docker Compose.

That's the whole surface. No routing config files, no JSON contracts to edit.

## What is deliberately NOT in VIE (yet)

- Persistent conversation memory — deferred (a `ConversationMemory` stub is preserved from the source).
- Streaming responses — Stage 2.
- Tool use / function calling — Stage 2.
- Cost/token accounting — usage is passed through; aggregation belongs in Stage 2.
