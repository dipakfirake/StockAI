"""Unit tests for Pro access controls, admin approvals, and payment verification."""

import pytest
import uuid
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.models.user import User
from backend.core.auth import hash_password, create_access_token
from backend.core.database import get_db


class MockAsyncSession:
    """Mock async database session for isolated auth and pro tests."""

    def __init__(self):
        self.users = {}
        self.orders = []

    def add(self, obj):
        if isinstance(obj, User):
            if not getattr(obj, "id", None):
                obj.id = uuid.uuid4()
            self.users[str(obj.id)] = obj
        else:
            self.orders.append(obj)

    def add_all(self, objs):
        for o in objs:
            self.add(o)

    async def commit(self):
        pass

    async def flush(self):
        pass

    async def refresh(self, obj):
        pass

    async def execute(self, statement):
        mock_result = MagicMock()
        stmt_str = str(statement)
        params = {}
        try:
            params = statement.compile().params or {}
        except Exception:
            params = {}

        target = None
        for p in params.values():
            p_str = str(p)
            if p_str in self.users:
                target = self.users[p_str]
                break
            for u in self.users.values():
                if str(u.id) == p_str or u.email == p_str:
                    target = u
                    break

        if "ORDER BY" in stmt_str and "users" in stmt_str:
            user_list = list(self.users.values())
            mock_result.scalars.return_value.all.return_value = user_list
            mock_result.scalar_one_or_none.return_value = user_list[0] if user_list else None
            return mock_result

        mock_result.scalar_one_or_none.return_value = target
        mock_result.scalars.return_value.first.return_value = target
        mock_result.scalars.return_value.all.return_value = [target] if target else []
        return mock_result


@pytest.fixture
def mock_db():
    session = MockAsyncSession()
    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield session
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_pro_direct_self_upgrade_disallowed(mock_db):
    """Verify that calling /api/auth/upgrade directly returns 402 Payment Required."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a standard user
        email = f"free_user_{uuid.uuid4().hex[:6]}@example.com"
        user = User(
            id=uuid.uuid4(),
            email=email,
            name="Free User",
            hashed_password=hash_password("Secret123!"),
            is_active=True,
            is_admin=False,
            subscription_tier="FREE",
            pro_status="NONE",
        )
        mock_db.add(user)

        token = create_access_token({"sub": str(user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt direct mock upgrade
        response = await client.post("/api/auth/upgrade", headers=headers)
        assert response.status_code == 402
        assert "Direct self-upgrade is disabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_pro_request_admin_approval_flow(mock_db):
    """Verify standard user can submit request for admin approval."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"applicant_{uuid.uuid4().hex[:6]}@example.com"
        user = User(
            id=uuid.uuid4(),
            email=email,
            name="Applicant",
            hashed_password=hash_password("Secret123!"),
            is_active=True,
            is_admin=False,
            subscription_tier="FREE",
            pro_status="NONE",
        )
        mock_db.add(user)

        token = create_access_token({"sub": str(user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Check initial status
        res1 = await client.get("/api/subscription/status", headers=headers)
        assert res1.status_code == 200
        assert res1.json()["subscription_tier"] == "FREE"
        assert res1.json()["pro_status"] == "NONE"

        # 2. Submit admin approval request
        res2 = await client.post(
            "/api/subscription/request-pro",
            headers=headers,
            json={"note": "Please approve my institutional research account"},
        )
        assert res2.status_code == 200
        assert res2.json()["pro_status"] == "REQUESTED"

        # 3. Verify status changed to REQUESTED
        res3 = await client.get("/api/subscription/status", headers=headers)
        assert res3.json()["pro_status"] == "REQUESTED"
        assert res3.json()["subscription_tier"] == "FREE"


@pytest.mark.asyncio
async def test_admin_approval_and_revocation(mock_db):
    """Verify admin user can approve and revoke Pro status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create standard user
        target_email = f"trader_{uuid.uuid4().hex[:6]}@example.com"
        target_user = User(
            id=uuid.uuid4(),
            email=target_email,
            name="Swing Trader",
            hashed_password=hash_password("Secret123!"),
            is_active=True,
            is_admin=False,
            subscription_tier="FREE",
            pro_status="REQUESTED",
        )
        # Create admin user
        admin_email = f"admin_{uuid.uuid4().hex[:6]}@example.com"
        admin_user = User(
            id=uuid.uuid4(),
            email=admin_email,
            name="Chief Admin",
            hashed_password=hash_password("AdminSecret123!"),
            is_active=True,
            is_admin=True,
            subscription_tier="PRO",
            pro_status="APPROVED",
        )
        mock_db.add_all([target_user, admin_user])

        admin_token = create_access_token({"sub": str(admin_user.id)})
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Admin lists users
        res1 = await client.get("/api/admin/users", headers=admin_headers)
        assert res1.status_code == 200
        emails = [u["email"] for u in res1.json()]
        assert target_email in emails

        # 2. Admin approves PRO
        res2 = await client.post(f"/api/admin/users/{target_user.id}/approve-pro", headers=admin_headers)
        assert res2.status_code == 200
        assert res2.json()["subscription_tier"] == "PRO"
        assert res2.json()["pro_status"] == "APPROVED"

        # 3. Target user checks status
        target_token = create_access_token({"sub": str(target_user.id)})
        res3 = await client.get("/api/subscription/status", headers={"Authorization": f"Bearer {target_token}"})
        assert res3.json()["subscription_tier"] == "PRO"
        assert res3.json()["pro_status"] == "APPROVED"

        # 4. Admin revokes PRO
        res4 = await client.post(f"/api/admin/users/{target_user.id}/revoke-pro", headers=admin_headers)
        assert res4.status_code == 200
        assert res4.json()["subscription_tier"] == "FREE"


@pytest.mark.asyncio
async def test_pro_payment_checkout_flow(mock_db):
    """Verify user can upgrade via verified payment reference."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"subscriber_{uuid.uuid4().hex[:6]}@example.com"
        user = User(
            id=uuid.uuid4(),
            email=email,
            name="Paid Subscriber",
            hashed_password=hash_password("Secret123!"),
            is_active=True,
            is_admin=False,
            subscription_tier="FREE",
            pro_status="NONE",
        )
        mock_db.add(user)

        token = create_access_token({"sub": str(user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        # Checkout payment
        res = await client.post(
            "/api/subscription/checkout",
            headers=headers,
            json={"payment_method": "UPI", "payment_reference": "UPI-REF-998877", "amount": 29.0},
        )
        assert res.status_code == 200
        assert res.json()["subscription_tier"] == "PRO"
        assert res.json()["pro_status"] == "ACTIVE"
        assert res.json()["payment_reference"] == "UPI-REF-998877"


@pytest.mark.asyncio
async def test_admin_registration_persists_is_admin(mock_db):
    """Verify that registering admin@stockai.com explicitly sets is_admin=True and PRO tier."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/auth/register",
            json={
                "email": "admin@stockai.com",
                "name": "Super Administrator",
                "password": "SecurePassword123!",
            },
        )
        assert res.status_code == 200
        reg_data = res.json()
        token = reg_data["token"]
        assert reg_data["email"] == "admin@stockai.com"

        me_res = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["is_admin"] is True
        assert me_data["subscription_tier"] == "PRO"


@pytest.mark.asyncio
async def test_auth_ping_lightweight_jwt_validation(mock_db):
    """Verify that /api/auth/ping validates JWT instantly without querying DB."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Valid Token
        fake_user_id = str(uuid.uuid4())
        valid_token = create_access_token({"sub": fake_user_id})
        res = await client.get("/api/auth/ping", headers={"Authorization": f"Bearer {valid_token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["valid"] is True
        assert data["user_id"] == fake_user_id

        # 2. Invalid Token
        res_invalid = await client.get("/api/auth/ping", headers={"Authorization": "Bearer invalid.jwt.token"})
        assert res_invalid.status_code == 401

        # 3. Missing Token
        res_missing = await client.get("/api/auth/ping")
        assert res_missing.status_code == 401



