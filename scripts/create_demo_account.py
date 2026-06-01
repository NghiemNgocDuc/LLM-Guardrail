import argparse
import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.deps import hash_api_key, hash_password
from app.models import APIKey, OrgPolicy, Organization, User
from app.routers.auth import (
    _DEFAULT_COMPLIANCE,
    _DEFAULT_INPUT_RULES,
    _DEFAULT_OUTPUT_RULES,
    _DEFAULT_TOPIC_POLICY,
)


async def create_demo_account(email: str, password: str, org_name: str) -> None:
    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email))
        user = existing.scalar_one_or_none()
        if user:
            print(f"Demo user already exists: {email}")
            return

        slug = "demo"
        suffix = 1
        while True:
            existing_org = await db.execute(select(Organization).where(Organization.slug == slug))
            if not existing_org.scalar_one_or_none():
                break
            suffix += 1
            slug = f"demo-{suffix}"

        org = Organization(name=org_name, slug=slug)
        db.add(org)
        await db.flush()

        db.add(
            OrgPolicy(
                org_id=org.id,
                input_rules=_DEFAULT_INPUT_RULES,
                output_rules=_DEFAULT_OUTPUT_RULES,
                topic_policy=_DEFAULT_TOPIC_POLICY,
                compliance_rules=_DEFAULT_COMPLIANCE,
                rate_limit_rpm=3,
                rate_limit_rpd=20,
            )
        )

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name="Demo User",
            is_admin=True,
            email_verified=True,
            org_id=org.id,
        )
        db.add(user)
        await db.flush()

        raw_key = APIKey.generate_raw_key()
        db.add(
            APIKey(
                name="Public demo key",
                key_prefix=raw_key[:12],
                key_hash=hash_api_key(raw_key),
                owner_id=user.id,
                org_id=org.id,
            )
        )
        await db.commit()

    print("Demo account created.")
    print(f"Email: {email}")
    print(f"Password: {password}")
    print(f"Gateway API key: {raw_key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a fixed demo account and gateway API key.")
    parser.add_argument("--email", default="demo@example.com")
    parser.add_argument("--password", default="demo-password-change-me")
    parser.add_argument("--org-name", default="Demo Org")
    args = parser.parse_args()

    asyncio.run(create_demo_account(args.email, args.password, args.org_name))


if __name__ == "__main__":
    main()
