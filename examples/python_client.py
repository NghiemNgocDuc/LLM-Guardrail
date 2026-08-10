import asyncio
import os

import httpx


BASE_URL = os.environ.get("GUARDRAIL_BASE_URL", "http://localhost:8080")
API_KEY = os.environ["GUARDRAIL_API_KEY"]


def main() -> None:
    response = httpx.post(
        f"{BASE_URL}/chat",
        headers={"X-Api-Key": API_KEY},
        json={
            "prompt": "Summarize why prompt-injection protection matters.",
            "max_tokens": 128,
        },
        timeout=30,
    )
    response.raise_for_status()
    print(response.json())


async def stream_main() -> None:
    """SDK example: stream /chat/stream with retries enabled."""
    from sdk.python.guardrail_client import GuardrailClient

    client = GuardrailClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        with_retry=True,
    )
    async for event in client.chat_stream(
        "Summarize why prompt-injection protection matters.",
        max_tokens=128,
    ):
        print(event)


if __name__ == "__main__":
    main()
    asyncio.run(stream_main())