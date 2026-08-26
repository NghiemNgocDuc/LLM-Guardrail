#!/usr/bin/env python
"""Setup test account cs@umass.edu as admin."""
import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.config import get_settings
from app.models import User
from app.deps import hash_password

async def setup_test_account():
    """Create or promote cs@umass.edu to admin."""
    settings = get_settings()
    
    if not settings.DATABASE_URL:
        print("[FAIL] DATABASE_URL not configured")
        return False
    
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with AsyncSessionLocal() as session:
            # Check if account exists
            stmt = select(User).where(User.email == "cs@umass.edu")
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if user:
                # Promote existing account
                if user.is_admin:
                    print("[OK] Test account cs@umass.edu is already admin")
                else:
                    user.is_admin = True
                    user.email_verified = True
                    session.add(user)
                    await session.commit()
                    print("[OK] Test account cs@umass.edu promoted to admin")
            else:
                # Create new account
                user = User(
                    id=str(uuid.uuid4()),
                    email="cs@umass.edu",
                    hashed_password=hash_password("123456789"),
                    full_name="Test Account",
                    is_active=True,
                    is_admin=True,
                    email_verified=True,
                )
                session.add(user)
                await session.commit()
                print("[OK] Test account cs@umass.edu created as admin")
            
            print(f"\n  Email:     cs@umass.edu")
            print(f"  Password:  123456789")
            print(f"  Admin:     [OK]")
            print("\nThe test account is ready for use!")
            return True
            
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await engine.dispose()

if __name__ == "__main__":
    success = asyncio.run(setup_test_account())
    exit(0 if success else 1)
