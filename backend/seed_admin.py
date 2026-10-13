"""Enterprise Admin Seeding and Management Utility.

Usage:
    python -m backend.seed_admin
    python -m backend.seed_admin --email admin@stockai.com --password "MySecret@123" --name "Super Admin"

Inside Docker on Oracle Cloud VM:
    sudo docker compose exec backend python -m backend.seed_admin --email admin@stockai.com --password "YourStrongPassword!123"
"""

import argparse
import asyncio
import getpass
import os
import secrets
import string
import sys
from sqlalchemy import select
from backend.core.database import AsyncSessionLocal
from backend.models.user import User
from backend.core.auth import hash_password
from backend.core.auth_security import validate_password_strength


def generate_secure_password(length: int = 16) -> str:
    """Generate a high-entropy password satisfying complexity rules."""
    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*()_+-="
    
    # Guarantee at least one of each category
    chars = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]
    all_chars = upper + lower + digits + symbols
    chars += [secrets.choice(all_chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


async def seed_admin_user(email: str, password: str, name: str) -> None:
    email = email.lower().strip()
    
    # Enforce password strength
    try:
        validate_password_strength(password)
    except ValueError as e:
        print(f"[ERROR] Password does not meet security requirements: {e}", file=sys.stderr)
        sys.exit(1)

    display_name = name or "StockAI Super Admin"
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.email == email))
        user = res.scalar_one_or_none()

        if user:
            user.hashed_password = hash_password(password)
            if name:
                user.name = name
            display_name = user.name
            user.is_admin = True
            user.subscription_tier = "PRO"
            user.pro_status = "APPROVED"
            user.is_active = True
            await db.commit()
            action = "UPDATED and PROMOTED"
        else:
            user = User(
                email=email,
                name=display_name,
                hashed_password=hash_password(password),
                is_admin=True,
                subscription_tier="PRO",
                pro_status="APPROVED",
                is_active=True,
            )
            db.add(user)
            await db.commit()
            action = "CREATED"

    print("\n" + "=" * 60)
    print(" [SECURITY] Admin Account Seeded Successfully")
    print("=" * 60)
    print(f" Status:              {action}")
    print(f" Email:               {email}")
    print(f" Name:                {display_name}")
    print(f" System Role:         SUPER_ADMIN (is_admin=True)")
    print(f" Subscription Tier:   PRO (pro_status=APPROVED)")
    print(f" Account Active:      YES")
    print("=" * 60)
    print(" You can now sign in at the frontend or Swagger (/docs).")
    print("=" * 60 + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Seed or update an administrator account.")
    parser.add_argument("--email", default=os.getenv("ADMIN_EMAIL", "admin@stockai.com"), help="Admin email address")
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"), help="Admin password (will prompt if omitted)")
    parser.add_argument("--name", default="Super Admin", help="Admin display name")
    return parser.parse_args()


def main():
    args = parse_args()
    email = args.email
    password = args.password
    name = args.name

    if not password:
        if sys.stdin.isatty():
            print(f"Configuring admin account for '{email}'...")
            password = getpass.getpass("Enter password (leave blank to auto-generate): ").strip()
        
        if not password:
            password = generate_secure_password()
            print(f"\n[INFO] Auto-generated high-entropy secure password: {password}\n")

    asyncio.run(seed_admin_user(email=email, password=password, name=name))


if __name__ == "__main__":
    main()
