#!/usr/bin/env python
"""Promote test account cs@umass.edu to admin status."""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.config import get_settings
from app.models import User

async def promote_test_account():
    """Promote cs@umass.edu to admin role."""
    settings = get_settings()
    
    if not settings.DATABASE_URL:
        print("❌ DATABASE_URL not configured")
        return False
    
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=sessionmaker, expire_on_commit=False)
    
    try:
        async with AsyncSessionLocal() as session:
            # Find the test account
            stmt = select(User).where(User.email == "cs@umass.edu")
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                print("❌ Test account cs@umass.edu not found")
                print("   Create the account first via the signup form")
                return False
            
            if user.is_admin:
                print("✓ Test account cs@umass.edu is already admin")
                return True
            
            # Promote to admin
            user.is_admin = True
            await session.merge(user)
            await session.commit()
            
            print("✓ Test account cs@umass.edu promoted to admin")
            print(f"  Email:    {user.email}")
            print(f"  Name:     {user.full_name}")
            print(f"  Admin:    {user.is_admin}")
            print(f"  Org:      {user.org_id}")
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        await engine.dispose()

if __name__ == "__main__":
    success = asyncio.run(promote_test_account())
    exit(0 if success else 1)
