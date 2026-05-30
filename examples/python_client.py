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


if __name__ == "__main__":
    main()
