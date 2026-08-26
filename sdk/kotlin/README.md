# GuardrailClient — Kotlin SDK

Zero-dependency Kotlin/JVM client for the LLM Guardrails gateway.
API-identical to `sdk/javascript/guardrailClient.mjs`, `sdk/python/guardrail_client.py`,
and `sdk/swift`.

## API

```kotlin
val client = GuardrailClient(
    baseUrl = "https://gateway.example.com",
    apiKey = "gr_...",
    withRetry = true,        // retry 402/429 with Retry-After backoff
    maxRetries = 3,
)

// Non-streaming
val result: ChatResponse = client.chat(
    prompt = "What is the capital of France?",
    model = null, backend = null,
    temperature = 0.7, maxTokens = 256,
)

// SSE streaming (blocking Sequence; no coroutine dependency)
for (event in client.chatStream(prompt = "Explain quarks")) {
    when (event) {
        is StreamEvent.Token   -> print(event.content)
        is StreamEvent.Done    -> print(event.status)
        is StreamEvent.Blocked -> print(event.inputGuard?.reasonCode)
        is StreamEvent.Error   -> print(event.detail)
        is StreamEvent.Ping    -> {}
    }
}
```

`ChatResponse` mirrors the gateway schema: `status` is
`delivered | input_blocked | output_blocked | rate_limited | error`, and
`input_guard` / `output_guard` carry `passed`, `check`, `reason`,
`reason_code`, `risk_score`. Non-2xx responses throw `ApiException(statusCode, detail)`.

## Security — read this before shipping a mobile app

**Do NOT embed a gateway API key in a shipped mobile application.**
Anything compiled into an APK/AAB can be reverse-engineered: key strings are
trivially recoverable from the binary, and an attacker who extracts a key can
spend your token balance and bypass your guardrails. The gateway key is a
server credential.

The supported mobile pattern is **server-side proxying**:

```
mobile app ──► your backend (holds the gateway API key) ──► LLM Guardrails gateway
```

Your backend authenticates its own users (Clerk, session cookies, etc.), applies
per-user quotas, and calls the gateway with the shared `X-Api-Key`. The mobile
app never sees the key. If you must call the gateway directly from a device,
scope the key to the minimum and rotate it aggressively — but prefer proxying.

## Build & test

Requires a JVM and [Kotlin](https://kotlinlang.org) 2.x (`kotlinc`).

```sh
kotlinc src/main/kotlin/com/llmguardrails/sdk/GuardrailClient.kt test/TestMain.kt -d build/out
java -cp "build/out;$(kotlinc -version >/dev/null 2>&1; echo $KOTLIN_HOME)/lib/kotlin-stdlib.jar" com.llmguardrails.sdk.TestMain
```

`test/TestMain.kt` spins up a mock gateway (JDK `HttpServer`) and exercises the
client end-to-end: auth header, response parsing, 429 retry with `Retry-After`,
blocked responses, and SSE token/done/blocked events. No network access needed.