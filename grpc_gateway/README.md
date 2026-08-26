# gRPC input-guard service (`grpc_gateway/`)

A thin gRPC front for the input guardrail. It runs the **same
`InputGuardrail` class and the same default policy rules that `/chat` uses**
(`_DEFAULT_INPUT_RULES`), so a verdict over gRPC is identical to the
input-gate half of a REST `/chat` call — byte-for-byte. No database, no rate
limit, no LLM call: it exists so high-throughput services can check many
prompts over one connection.

- Proto: `grpc_gateway/chat_guardrail.proto` (package `llm_guardrails.v1`)
- Service: `GuardrailService` — `Check` (unary) and `CheckStream` (bidirectional)
- Server: `python -m grpc_gateway.server` → `[::]:50051`
- Wire fields mirror `GuardrailResult` exactly: `allowed`, `check`, `reason`,
  `reason_code`, `risk_score` (+ `status` in `delivered|input_blocked`
  vocabulary to match `ChatResponse.status`)

## Regenerating stubs

```bash
python -m grpc_tools.protoc \
  -I grpc_gateway \
  --python_out=grpc_gateway \
  --grpc_python_out=grpc_gateway \
  grpc_gateway/chat_guardrail.proto
```

`grpcio==1.83.0` is pinned in `requirements.txt` (runtime); `grpcio-tools`
is only needed to regenerate. After regenerating, restore the relative
import in `chat_guardrail_pb2_grpc.py`:

```python
from . import chat_guardrail_pb2 as chat__guardrail__pb2
```

(the default generator emits a top-level `import chat_guardrail_pb2`, which
breaks when the module lives in a package).

## OpenAPI generator report (kotlin + swift5)

Tool: openapi-generator-cli 7.14.0 (Java 26), input `scripts/openapi.schema.json`.

| Target  | Exit | Result |
|---------|------|--------|
| `kotlin` (library=jvm-okhttp4) | 0 | 183 Kotlin files; 13 API classes incl. `GatewayApi`; `ChatRequest`/`ChatResponse`/`GuardrailResult` models generated |
| `swift5` | 0 | 96 Swift files; `GatewayAPI`, `ChatRequest`, `ChatResponse` generated |

Findings (why the hand-written SDKs in `sdk/kotlin` and `sdk/swift` are
still the right call):

1. **SSE `/chat/stream` is unmodeled.** The endpoint returns a
   `StreamingResponse`, so the generator emits `chatStreamChatStreamPost(...) :
   kotlin.Any` (Kotlin) and no typed event model (Swift). Streaming
   consumption, `token/done/blocked/error/ping` event parsing, and heartbeat
   handling all have to be hand-written on top either way.
2. **Auth is per-call, not global.** `xApiKey` is a required per-request
   parameter on every operation; neither generator emits a default-header
   auth configuration, so an API-key wrapper is unavoidable.
3. **Heavy dependency trees.** The Kotlin output requires okhttp4 + gson +
   kotlinx-coroutines + moshi adapters (many generated files are just JSON
   adapters); the swift5 output requires Alamofire (or a URLSession swap).
   The task's SDKs are zero-dependency by design.
4. **The unary half is otherwise accurate** — `ChatResponse` fields
   (`request_id`, `status`, `input_guard`, `output_guard`, `latency_ms`,
   `model`, `backend`, `tokens_remaining`) round-trip correctly, and the
   kotlin `GatewayApi.chatChatPost` signature matches the REST contract.

Bottom line: generator output is usable for unary `/chat` but would need
hand-written streaming + auth plumbing for `/chat/stream`; keeping the
existing zero-dependency SDKs is justified. Full generated sources live in
the generator scratch dir (not committed).

## Docker

`docker-compose.yml` gains a `grpc` service (same image as `api`, command
`python -m grpc_gateway.server`, port 50051 exposed on the internal network
only — never published, consistent with `opa`).

## Tests

`tests/test_grpc_checkstream.py` (4 tests): in-process server on an
ephemeral port, then

- bidirectional `CheckStream` verdicts must equal direct `InputGuardrail`
  calls for the same prompts (`allowed`, `reason_code`, `check`,
  `risk_score`, `reason`, and `status`),
- each threat class blocks with its expected `reason_code`
  (`secret_detected`, `pii_detected`, `prompt_injection`,
  `jailbreak_attempt`),
- true interleaved bidi streaming,
- `request_id` passthrough / generation.

```bash
python -m pytest tests/test_grpc_checkstream.py -q
```