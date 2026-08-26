import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Organization, OrgPolicy, User, APIKey
from app.deps import hash_password, hash_api_key

SEED_EMAIL    = "test@guardrails.dev"
SEED_PASSWORD = "testpass123"
SEED_RAW_KEY  = "grg_testkey_dev_000000000000000000000000"

async def seed():
    async with AsyncSessionLocal() as db:
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
    print("Done! Email: test@guardrails.dev | Password: testpass123 | Key: " + SEED_RAW_KEY)

asyncio.run(seed())
