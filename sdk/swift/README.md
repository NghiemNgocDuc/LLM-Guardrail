# GuardrailClient — Swift SDK

Dependency-free Swift client for the LLM Guardrails gateway (SwiftPM,
iOS 16+ / macOS 13+). API-identical to `sdk/javascript/guardrailClient.mjs`,
`sdk/python/guardrail_client.py`, and `sdk/kotlin`.

## API

```swift
import GuardrailClient

let client = try GuardrailClient(
    baseURL: "https://gateway.example.com",
    apiKey: "gr_...",
    withRetry: true,
    maxRetries: 3
)

// Non-streaming
let result: ChatResponse = try await client.chat(
    prompt: "What is the capital of France?",
    temperature: 0.7,
    maxTokens: 256
)

// SSE streaming
for try await event in try await client.chatStream(prompt: "Explain quarks") {
    switch event {
    case .token(let content):   print(content)
    case .done(let status, _, _, _, _, _): print(status)
    case .blocked(_, let inputGuard, _): print(inputGuard?.reasonCode ?? "?")
    case .error(let detail):    print(detail)
    case .ping:                 break
    }
}
```

`ChatResponse.status` is `delivered | input_blocked | output_blocked |
rate_limited | error`; `input_guard`/`output_guard` carry `passed`, `check`,
`reason`, `reason_code`, `risk_score`. Non-2xx responses throw `ApiError(statusCode, detail)`.

## Security — read this before shipping a mobile app

**Do NOT embed a gateway API key in a shipped iOS app.**
Anything inside an `.ipa` or a macOS app bundle can be reverse-engineered:
key strings are trivially recoverable from the binary, and an attacker who
extracts a key can spend your token balance and bypass your guardrails. The
gateway key is a server credential.

The supported mobile pattern is **server-side proxying**:

```
mobile app ──► your backend (holds the gateway API key) ──► LLM Guardrails gateway
```

Your backend authenticates its own users (Clerk, session cookies, etc.), applies
per-user quotas, and calls the gateway with the shared `X-Api-Key`. The mobile
app never sees the key. If you must call the gateway directly from a device,
scope the key to the minimum and rotate it aggressively — but prefer proxying.

## Build & test

```sh
swift build
swift test
```

`Tests/GuardrailClientTests` intercepts URLSession via `MockURLProtocol` and
covers: auth header, response parsing, 429 retry with `Retry-After`, blocked
responses, and SSE token/done/blocked events — no network access required.

> Note: the tests require a Swift toolchain (macOS or Linux). They cannot run
> on Windows — that is a limitation of this development environment, not of
> the SDK.