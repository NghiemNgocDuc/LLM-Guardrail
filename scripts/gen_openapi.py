"""Regenerate src/api-types.ts from the live FastAPI OpenAPI schema.

The API does not need to be running — this dumps app.openapi() via
FastAPI's TestClient without entering the lifespan (no DB connection is
made). Requires the Python dependencies installed (pip install -r
requirements.txt -r requirements-dev.txt).

Usage:
    python scripts/gen_openapi.py
    npx openapi-typescript scripts/openapi.schema.json -o src/api-types.ts
"""
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent / "openapi.schema.json"


def main() -> None:
    client = TestClient(app)
    resp = client.get("/openapi.json")
    resp.raise_for_status()
    SCHEMA_PATH.write_text(json.dumps(resp.json(), indent=2), encoding="utf-8")
    print(f"Wrote {SCHEMA_PATH}")


if __name__ == "__main__":
    main()