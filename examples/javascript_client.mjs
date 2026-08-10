import { GuardrailClient } from "../sdk/javascript/guardrailClient.mjs";

const baseUrl = process.env.GUARDRAIL_BASE_URL ?? "http://localhost:8080";
const apiKey = process.env.GUARDRAIL_API_KEY;

if (!apiKey) {
  throw new Error("Set GUARDRAIL_API_KEY before running this example.");
}

const response = await fetch(`${baseUrl}/chat`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Api-Key": apiKey,
  },
  body: JSON.stringify({
    prompt: "Summarize why prompt-injection protection matters.",
    max_tokens: 128,
  }),
});

if (!response.ok) {
  throw new Error(await response.text());
}

console.log(await response.json());

// SDK example: stream /chat/stream with retries enabled.
const client = new GuardrailClient({ baseUrl, apiKey, withRetry: true });
for await (const event of client.chatStream({
  prompt: "Summarize why prompt-injection protection matters.",
  maxTokens: 128,
})) {
  console.log(event);
}