"""Create a development account with one-time, randomly generated credentials."""
import asyncio
import os
import secrets
import sys
sys.path.insert(0, os.path.dirname(__file__))
from sqlalchemy import select
from app.config import get_settings
from app.database import get_sessionmaker
from app.models import Organization, OrgPolicy, User, APIKey
from app.deps import hash_password, hash_api_key

SEED_EMAIL    = "test@guardrails.dev"
SEED_PASSWORD = os.environ.get("SEED_PASSWORD") or secrets.token_urlsafe(24)
SEED_RAW_KEY  = APIKey.generate_raw_key()

async def seed():
    if get_settings().APP_ENV != "development":
        raise RuntimeError("The seed account can only be created in development.")
    async with get_sessionmaker()() as db:
        existing = await db.execute(select(User).where(User.email == SEED_EMAIL))
        if existing.scalar_one_or_none():
            print("Seed account already exists — nothing to do.")
            return
        org = Organization(name="Test Org", slug="test-org")
        db.add(org)
        await db.flush()
        db.add(OrgPolicy(org_id=org.id, input_rules={}, output_rules={}, topic_policy={}, compliance_rules={}))
        user = User(email=SEED_EMAIL, hashed_password=hash_password(SEED_PASSWORD),
                    full_name="Test User", is_admin=True, is_active=True,
                    email_verified=True, org_id=org.id)
        db.add(user)
        await db.flush()
        db.add(APIKey(name="dev-key", key_prefix=SEED_RAW_KEY[:12],
                      key_hash=hash_api_key(SEED_RAW_KEY), owner_id=user.id, org_id=org.id))
        await db.commit()
    print(f"Development account created. Email: {SEED_EMAIL} | Password: {SEED_PASSWORD} | Key: {SEED_RAW_KEY}")

if __name__ == "__main__":
    asyncio.run(seed())
