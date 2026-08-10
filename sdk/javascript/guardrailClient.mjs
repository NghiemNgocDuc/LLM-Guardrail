const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export class GuardrailClient {
  constructor({ baseUrl, apiKey, withRetry = false, maxRetries = 3 }) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
    this.withRetry = withRetry;
    this.maxRetries = maxRetries;
  }

  _body({ prompt, model, backend, temperature, maxTokens }) {
    return {
      prompt,
      temperature,
      max_tokens: maxTokens,
      ...(model ? { model } : {}),
      ...(backend ? { backend } : {}),
    };
  }

  _retryDelay(retryAfter, attempt) {
    if (retryAfter != null && retryAfter !== "") {
      const seconds = Number(retryAfter);
      if (Number.isFinite(seconds)) {
        return seconds * 1000;
      }
    }
    return Math.min(2 ** (attempt - 1), 8) * 1000;
  }

  async chat({ prompt, model, backend, temperature = 0.7, maxTokens = 256 }) {
    const body = this._body({ prompt, model, backend, temperature, maxTokens });
    const maxRetries = this.withRetry ? this.maxRetries : 0;

    for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
      const response = await fetch(`${this.baseUrl}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Api-Key": this.apiKey,
        },
        body: JSON.stringify(body),
      });

      if ((response.status === 402 || response.status === 429) && attempt <= maxRetries) {
        await sleep(this._retryDelay(response.headers.get("Retry-After"), attempt));
        continue;
      }

      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    }
  }

  async *chatStream({ prompt, model, backend, temperature = 0.7, maxTokens = 256 }) {
    /**
     * SSE stream from /chat/stream.
     *
     * Yields parsed events — each is an object with a "type" field:
     *   { type: "token",   content: "..." }
     *   { type: "done",    status: "...", model: "...", ... }
     *   { type: "blocked", status: "input_blocked" | "output_blocked", ... }
     *   { type: "error",   detail: "..." }
     * Retries only happen before the stream starts: once the first chunk
     * arrives the connection is never retried.
     */
    const body = this._body({ prompt, model, backend, temperature, maxTokens });
    const maxRetries = this.withRetry ? this.maxRetries : 0;

    for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
      const response = await fetch(`${this.baseUrl}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Api-Key": this.apiKey,
        },
        body: JSON.stringify(body),
      });

      if ((response.status === 402 || response.status === 429) && attempt <= maxRetries) {
        await sleep(this._retryDelay(response.headers.get("Retry-After"), attempt));
        continue;
      }

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        let frameEnd;
        while ((frameEnd = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, frameEnd);
          buffer = buffer.slice(frameEnd + 2);
          for (const line of frame.split("\n")) {
            if (line.startsWith("data: ")) {
              yield JSON.parse(line.slice("data: ".length));
            }
          }
        }
      }
      return;
    }
  }
}