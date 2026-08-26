#!/usr/bin/env python
"""Export RequestLog rows for an org and date range to a CSV file.

Columns mirror the RequestLog model fields. The date-range filter reuses the
same pattern as GET /analytics/logs. Edit ORG_ID / START_DATE / END_DATE
(ISO format, e.g. "2026-01-01") before running.
"""
import asyncio
import csv
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.config import get_settings
from app.models import Organization, RequestLog

ORG_ID = ""
START_DATE = ""
END_DATE = ""

CSV_FIELDS = [
    "id",
    "api_key_id",
    "org_id",
    "prompt_hash",
    "prompt_preview",
    "full_prompt",
    "model",
    "backend",
    "input_passed",
    "input_block_reason",
    "output_passed",
    "output_block_reason",
    "fired_rule",
    "status",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "created_at",
]

async def export_audit_log():
    """Dump matching RequestLog rows to audit-log-*.csv in the current directory."""
    settings = get_settings()

    if not settings.DATABASE_URL:
        print("[FAIL] DATABASE_URL not configured")
        return False

    if not ORG_ID:
        print("[FAIL] ORG_ID is not set — edit the variable at the top of this script")
        return False

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=sessionmaker, expire_on_commit=False)

    try:
        filters = [RequestLog.org_id == ORG_ID]
        if START_DATE:
            try:
                since = datetime.fromisoformat(START_DATE).replace(tzinfo=timezone.utc)
                filters.append(RequestLog.created_at >= since)
            except ValueError:
                print(f"[FAIL] START_DATE {START_DATE!r} is not a valid ISO date")
                return False
        if END_DATE:
            try:
                until = datetime.fromisoformat(END_DATE).replace(tzinfo=timezone.utc)
                filters.append(RequestLog.created_at <= until)
            except ValueError:
                print(f"[FAIL] END_DATE {END_DATE!r} is not a valid ISO date")
                return False

        async with AsyncSessionLocal() as session:
            org = await session.get(Organization, ORG_ID)
            if not org:
                print(f"[FAIL] Organization {ORG_ID} not found")
                return False

            result = await session.execute(
                select(RequestLog)
                .where(*filters)
                .order_by(RequestLog.created_at.desc())
            )
            logs = result.scalars().all()

        filename = f"audit-log-{ORG_ID}-{START_DATE or 'start'}_{END_DATE or 'now'}.csv"
        with Path(filename).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for log in logs:
                writer.writerow({
                    "id":                   log.id,
                    "api_key_id":           log.api_key_id or "",
                    "org_id":               log.org_id or "",
                    "prompt_hash":          log.prompt_hash,
                    "prompt_preview":       log.prompt_preview,
                    "full_prompt":          log.full_prompt or "",
                    "model":                log.model,
                    "backend":              log.backend,
                    "input_passed":         log.input_passed,
                    "input_block_reason":   log.input_block_reason or "",
                    "output_passed":        log.output_passed if log.output_passed is not None else "",
                    "output_block_reason":  log.output_block_reason or "",
                    "fired_rule":           log.fired_rule or "",
                    "status":               log.status,
                    "latency_ms":           log.latency_ms,
                    "input_tokens":         log.input_tokens,
                    "output_tokens":        log.output_tokens,
                    "created_at":           log.created_at.isoformat(),
                })

        print(f"[OK] Exported {len(logs)} rows to {filename}")
        if not logs:
            print("  (no RequestLog rows matched ORG_ID + date range)")
        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        return False
    finally:
        await engine.dispose()

if __name__ == "__main__":
    success = asyncio.run(export_audit_log())
    exit(0 if success else 1)