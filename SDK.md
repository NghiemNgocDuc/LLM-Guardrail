# SDK Usage

This repo includes lightweight client helpers for apps that want to call the guardrail gateway instead of calling an LLM provider directly.

## Python

```python
from sdk.python.guardrail_client import GuardrailClient

client = GuardrailClient(
    base_url="https://your-guardrail-domain.com",
    api_key="grg_...",
)

result = client.chat(
    "Summarize why prompt injection matters.",
    max_tokens=128,
)

print(result["status"])
print(result["response"])
```

## JavaScript

```js
import { GuardrailClient } from "./sdk/javascript/guardrailClient.mjs";

const client = new GuardrailClient({
  baseUrl: "https://your-guardrail-domain.com",
  apiKey: "grg_...",
});

const result = await client.chat({
  prompt: "Summarize why prompt injection matters.",
  maxTokens: 128,
});

console.log(result.status);
console.log(result.response);
```

Never send provider keys such as `GROQ_API_KEY` to browser clients. Provider keys stay server-side in the gateway runtime environment.
