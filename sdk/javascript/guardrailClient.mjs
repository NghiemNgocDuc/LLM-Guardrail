export class GuardrailClient {
  constructor({ baseUrl, apiKey }) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  async chat({ prompt, model, backend, temperature = 0.7, maxTokens = 256 }) {
    const body = {
      prompt,
      temperature,
      max_tokens: maxTokens,
      ...(model ? { model } : {}),
      ...(backend ? { backend } : {}),
    };

    const response = await fetch(`${this.baseUrl}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Api-Key": this.apiKey,
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  }
}
