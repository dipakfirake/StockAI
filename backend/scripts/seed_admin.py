"""Seed or promote an Administrator account with high security.

Usage inside Docker on the server:
    sudo docker compose exec backend python -m backend.scripts.seed_admin --email admin@stockai.com --password "YourStrongPassword@123"

Or interactively (prompt for password):
    sudo docker compose exec backend python -m backend.scripts.seed_admin --email admin@stockai.com
"""

import argparse
import asyncio
import getpass
import sys
import uuid
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(root_dir))
sys.path.append("/app")

from sqlalchemy import select
from backend.core.database import AsyncSessionLocal, create_db_tables
from backend.models.user import User
from backend.core.auth import hash_password
from backend.core.auth_security import validate_password_strength


async def seed_admin(email: str, password: str | None = None, name: str = "Administrator"):
    email = email.lower().strip()
    
    # Prompt password if not provided
    if not password:
        if sys.stdin.isatty():
            password = getpass.getpass(f"Enter password for admin ({email}): ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("[-] Error: Passwords do not match.")
                sys.exit(1)
        else:
            print("[-] Error: Password must be supplied via --password in non-interactive mode.")
            sys.exit(1)

    # Validate security policy
    try:
        validate_password_strength(password)
    except ValueError as err:
        print(f"[-] Password does not meet security requirements: {err}")
        print("    Requirements: Min 8 chars, at least one letter, and at least one digit or special character.")
        sys.exit(1)

    # Ensure tables are ready
    await create_db_tables()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user:
            print(f"[*] User '{email}' already exists. Promoting to Admin & Active PRO...")
            user.is_admin = True
            user.subscription_tier = "PRO"
            user.pro_status = "ACTIVE"
            user.is_active = True
            if password:
                user.hashed_password = hash_password(password)
            await session.commit()
            print(f"[+] Successfully updated admin privileges for '{email}'!")
        else:
            print(f"[*] Creating new Administrator account '{email}'...")
            user = User(
                id=uuid.uuid4(),
                email=email,
                name=name,
                hashed_password=hash_password(password),
                is_active=True,
                is_admin=True,
                subscription_tier="PRO",
                pro_status="ACTIVE",
            )
            session.add(user)
            await session.commit()
            print(f"[+] Successfully seeded new Administrator account for '{email}'!")


def main():
    parser = argparse.ArgumentParser(description="Seed or promote an Administrator account.")
    parser.add_argument("--email", default="admin@stockai.com", help="Admin email (default: admin@stockai.com)")
    parser.add_argument("--password", default=None, help="Admin password (prompts securely if omitted)")
    parser.add_argument("--name", default="Administrator", help="Admin display name (default: Administrator)")
    args = parser.parse_args()

    asyncio.run(seed_admin(email=args.email, password=args.password, name=args.name))


if __name__ == "__main__":
    main()
