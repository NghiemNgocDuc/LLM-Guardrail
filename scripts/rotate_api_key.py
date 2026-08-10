#!/usr/bin/env python
"""Rotate a gateway API key: revoke the old one and issue a replacement.

The key is identified by its 12-char prefix (e.g. "grg_abc123...", as shown in
the dashboard) or by its raw key — the script only ever touches the prefix —
or by its UUID id. Edit TARGET_KEY before running.
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.config import get_settings
from app.deps import hash_api_key
from app.models import APIKey, User

# Identify the key by prefix (first 12 chars), or paste the full raw key, or a UUID id
TARGET_KEY = "grg_"

async def rotate_api_key():
    """Revoke the key matching TARGET_KEY and create a replacement for the same owner."""
    settings = get_settings()

    if not settings.DATABASE_URL:
        print("❌ DATABASE_URL not configured")
        return False

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=sessionmaker, expire_on_commit=False)

    try:
        target = TARGET_KEY.strip()
        if len(target) == 36:
            stmt = select(APIKey).where(APIKey.id == target)
        else:
            stmt = select(APIKey).where(APIKey.key_prefix == target[:12])

        async with AsyncSessionLocal() as session:
            result = await session.execute(stmt)
            key = result.scalar_one_or_none()

            if not key:
                print(f"❌ API key {target[:12]} not found")
                return False

            if not key.is_active:
                print(f"❌ API key {key.key_prefix} is already revoked")
                return False

            owner = await session.get(User, key.owner_id)
            owner_label = owner.email if owner else key.owner_id

            # Revoke the old key (same mechanism as DELETE /api-keys/{id})
            key.is_active = False

            # Create a replacement with the same name, owner, org, and scopes
            raw_key = APIKey.generate_raw_key()
            new_key = APIKey(
                name=key.name,
                key_prefix=raw_key[:12],
                key_hash=hash_api_key(raw_key),
                owner_id=key.owner_id,
                org_id=key.org_id,
                scopes=key.scopes,
                expires_at=key.expires_at,
            )
            session.add(new_key)
            await session.commit()

            print("✓ API key rotated")
            print(f"  Name:     {key.name}")
            print(f"  Owner:    {owner_label}")
            print(f"  Org:      {key.org_id}")
            print(f"  Old key:  {key.key_prefix} (revoked)")
            print(f"  New key:  {new_key.key_prefix}")
            print("")
            print("⚠️  New raw API key — shown exactly once, store it now:")
            print(raw_key)
            return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        await engine.dispose()

if __name__ == "__main__":
    success = asyncio.run(rotate_api_key())
    exit(0 if success else 1)