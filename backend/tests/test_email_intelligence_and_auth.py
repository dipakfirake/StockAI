"""Unit tests for Email Intelligence, Free Email OTP verification, and Google OAuth2 integration."""

import pytest
import uuid
import time
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.models.user import User
from backend.core.auth import hash_password, create_access_token
from backend.core.auth_security import (
    validate_password_strength,
    validate_email_syntax,
    sanitize_display_name,
)
from backend.core.database import get_db
from backend.core.email_intelligence import (
    canonicalize_email,
    is_disposable_domain,
    analyze_entropy_and_heuristics,
    validate_email_for_registration,
)
from backend.services.email_service import (
    generate_secure_otp,
    email_otp_service,
    _LOCAL_OTP_STORE,
)


# ---------------------------------------------------------------------------
# 1. Email Intelligence Unit Tests
# ---------------------------------------------------------------------------

def test_canonicalize_email():
    """Test Gmail plus-tag stripping and dot removal."""
    # Gmail plus-tags and dots
    assert canonicalize_email("user.name+testing123@gmail.com")[0] == "username@gmail.com"
    assert canonicalize_email("U.S.E.R@googlemail.com")[0] == "user@gmail.com"
    assert canonicalize_email("john.doe@GMAIL.COM")[0] == "johndoe@gmail.com"
    
    # Outlook / Yahoo preserves dots, strips plus tags
    assert canonicalize_email("first.last+newsletter@outlook.com")[0] == "first.last@outlook.com"
    assert canonicalize_email("jane.smith@yahoo.com")[0] == "jane.smith@yahoo.com"
    
    # Invalid email fallback
    assert canonicalize_email("invalid-email")[0] == "invalid-email"


def test_is_disposable_domain():
    """Test rejection of known burner email domains and acceptance of genuine ones."""
    # Disposable domains
    assert is_disposable_domain("mailinator.com") is True
    assert is_disposable_domain("temp-mail.org") is True
    assert is_disposable_domain("10minutemail.com") is True
    assert is_disposable_domain("guerrillamail.com") is True
    assert is_disposable_domain("trashmail.com") is True
    assert is_disposable_domain("subdomain.tempmail.com") is True

    # Legitimate domains
    assert is_disposable_domain("gmail.com") is False
    assert is_disposable_domain("outlook.com") is False
    assert is_disposable_domain("yahoo.com") is False
    assert is_disposable_domain("apple.com") is False


def test_analyze_entropy_and_heuristics():
    """Test algorithmic entropy and consonant clustering for bot usernames."""
    # Legitimate names -> suspicious must be False
    res1 = analyze_entropy_and_heuristics("rahul.sharma")
    assert res1["suspicious"] is False

    res2 = analyze_entropy_and_heuristics("alexandra.morgan")
    assert res2["suspicious"] is False

    res3 = analyze_entropy_and_heuristics("dev99")
    assert res3["suspicious"] is False

    # High entropy / heavy consonant clustering bot patterns -> suspicious must be True
    res_bot1 = analyze_entropy_and_heuristics("qwxzkj1984712")
    assert res_bot1["suspicious"] is True

    res_bot2 = analyze_entropy_and_heuristics("bcdfghjklmnpqr")
    assert res_bot2["suspicious"] is True


@pytest.mark.asyncio
async def test_validate_email_for_registration():
    """Test end-to-end multi-tier email validation."""
    # Valid legitimate email (mock MX check to avoid external DNS queries during tests)
    with patch("backend.core.email_intelligence.check_domain_mx_records", new=AsyncMock(return_value=True)):
        res = await validate_email_for_registration("legit.trader@gmail.com")
        assert res["valid"] is True
        assert res["canonical_email"] == "legittrader@gmail.com"
        assert "valid and accepted" in res["reason"]
        assert res["risk_level"] == "LOW"

        # Disposable domain rejection
        res = await validate_email_for_registration("fake123@mailinator.com")
        assert res["valid"] is False
        assert "disposable" in res["reason"].lower()

        # Bot username flagged with elevated risk
        res_bot = await validate_email_for_registration("bcdfghjklmnpq12345@gmail.com")
        assert res_bot["valid"] is True
        assert res_bot["heuristics"]["suspicious"] is True
        assert res_bot["risk_level"] == "MEDIUM"

        # Invalid format rejection
        res_bad = await validate_email_for_registration("notanemail")
        assert res_bad["valid"] is False
        assert "valid" in res_bad["reason"].lower() or "email address" in res_bad["reason"].lower()


# ---------------------------------------------------------------------------
# 2. Email OTP Service Unit Tests
# ---------------------------------------------------------------------------

def test_generate_secure_otp():
    """Verify cryptographically secure 6-digit OTP generation."""
    otp = generate_secure_otp()
    assert len(otp) == 6
    assert otp.isdigit()


@pytest.mark.asyncio
async def test_otp_store_cooldown_and_verification():
    """Verify OTP storage, cooldown enforcement, attempt limits, and verification."""
    test_email = "test_otp_user@example.com"
    canonical = "test_otp_user@example.com"
    _LOCAL_OTP_STORE.clear()

    # Fast in-memory mock for cache functions to avoid Redis connection overhead
    mock_cache = {}

    async def mock_get(k):
        return mock_cache.get(k)

    async def mock_set(k, v, ttl=60):
        mock_cache[k] = v

    async def mock_del(k):
        mock_cache.pop(k, None)

    with patch("backend.services.email_service.cache_get", side_effect=mock_get), \
         patch("backend.services.email_service.cache_set", side_effect=mock_set), \
         patch("backend.services.email_service.cache_delete", side_effect=mock_del), \
         patch("backend.services.email_service.EmailOtpService.dispatch_email_async", new=AsyncMock(return_value=(True, ""))):

        # 1. Request OTP
        success, msg, cooldown = await email_otp_service.request_registration_otp(
            canonical_email=canonical,
            user_name="Test User",
            hashed_password="hashed_pwd_123",
            raw_email=test_email
        )
        assert success is True

        # 2. Immediate resend should trigger 60s cooldown
        success2, msg2, cooldown2 = await email_otp_service.request_registration_otp(
            canonical_email=canonical,
            user_name="Test User",
            hashed_password="hashed_pwd_123",
            raw_email=test_email
        )
        assert success2 is False
        assert "Please wait" in msg2

        # Retrieve the OTP that was stored
        cache_key = f"reg_otp:{canonical}"
        stored_entry = mock_cache.get(cache_key) or _LOCAL_OTP_STORE.get(cache_key)
        assert stored_entry is not None
        otp_val = stored_entry["otp"]

        # 3. Incorrect OTP verification should fail
        valid, reason, user_data = await email_otp_service.verify_registration_otp(canonical, "000000")
        assert valid is False
        assert "incorrect" in reason.lower() or "attempts remaining" in reason.lower()

        # 4. Correct OTP verification should succeed and return user_data
        valid, reason, user_data = await email_otp_service.verify_registration_otp(canonical, otp_val)
        assert valid is True
        assert "successfully verified" in reason.lower()
        assert user_data["name"] == "Test User"

        # 5. Subsequent verification with used OTP should fail (burned)
        valid, reason, user_data = await email_otp_service.verify_registration_otp(canonical, otp_val)
        assert valid is False
        assert "expired" in reason.lower()


# ---------------------------------------------------------------------------
# 3. Mock Database & HTTP Client for Auth Routes
# ---------------------------------------------------------------------------

class MockAsyncSession:
    """Mock async database session for auth tests."""

    def __init__(self):
        self.users = {}

    def add(self, obj):
        if isinstance(obj, User):
            if not getattr(obj, "id", None):
                obj.id = uuid.uuid4()
            self.users[str(obj.id)] = obj

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

        if "SELECT" in stmt_str:
            mock_result.scalar_one_or_none.return_value = target
            mock_result.scalars.return_value.all.return_value = [target] if target else []
        return mock_result


@pytest.fixture
def mock_db():
    session = MockAsyncSession()
    # Pre-populate an existing user
    existing_user = User(
        id=uuid.uuid4(),
        email="existing@gmail.com",
        name="Existing User",
        hashed_password=hash_password("Existing123!"),
        is_admin=False,
        is_active=True,
    )
    session.add(existing_user)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield session
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# 4. Route Integration Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_config_endpoint(mock_db):
    """Verify GET /api/auth/config returns feature flags."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "google_client_id" in data
        assert "email_otp_enabled" in data


@pytest.mark.asyncio
async def test_send_registration_otp_tempmail_blocked(mock_db):
    """Verify disposable emails are rejected at OTP request."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/auth/send-registration-otp",
            json={"email": "throwaway@mailinator.com", "password": "StrongPassword123!", "name": "Fake User"}
        )
        assert resp.status_code == 422
        assert "disposable" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_send_registration_otp_existing_email(mock_db):
    """Verify existing user cannot request registration OTP."""
    with patch("backend.core.email_intelligence.check_domain_mx_records", new=AsyncMock(return_value=True)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/auth/send-registration-otp",
                json={"email": "existing@gmail.com", "password": "StrongPassword123!", "name": "Existing User"}
            )
            assert resp.status_code == 400
            assert "already exists" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_send_and_verify_registration_otp_flow(mock_db):
    """Verify valid OTP dispatch (mocked SMTP) and verification."""
    _LOCAL_OTP_STORE.clear()
    mock_cache = {}

    async def mock_get(k):
        return mock_cache.get(k)

    async def mock_set(k, v, ttl=60):
        mock_cache[k] = v

    async def mock_del(k):
        mock_cache.pop(k, None)

    raw_test_email = "fresh_user@gmail.com"
    canonical = canonicalize_email(raw_test_email)[0]

    with patch("backend.core.email_intelligence.check_domain_mx_records", new=AsyncMock(return_value=True)), \
         patch("backend.services.email_service.cache_get", side_effect=mock_get), \
         patch("backend.services.email_service.cache_set", side_effect=mock_set), \
         patch("backend.services.email_service.cache_delete", side_effect=mock_del), \
         patch("backend.services.email_service.EmailOtpService.dispatch_email_async", new=AsyncMock(return_value=(True, ""))):
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Send OTP
            resp = await client.post(
                "/api/auth/send-registration-otp",
                json={"email": raw_test_email, "password": "StrongPassword123!", "name": "Fresh User"}
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

            # Retrieve generated OTP from cache
            cache_key = f"reg_otp:{canonical}"
            stored = mock_cache.get(cache_key) or _LOCAL_OTP_STORE.get(cache_key)
            assert stored is not None
            otp_val = stored["otp"]

            # Verify with wrong OTP
            bad_resp = await client.post(
                "/api/auth/verify-registration-otp",
                json={"email": raw_test_email, "otp": "999999"}
            )
            assert bad_resp.status_code == 400

            # Verify with correct OTP
            good_resp = await client.post(
                "/api/auth/verify-registration-otp",
                json={"email": raw_test_email, "otp": otp_val}
            )
            assert good_resp.status_code == 200
            resp_data = good_resp.json()
            assert "access_token" in resp_data
            assert resp_data["user"]["email"] == raw_test_email


@pytest.mark.asyncio
async def test_google_auth_registers_secure_default_user(mock_db):
    """Verify Google OAuth registers new user with default FREE tier and is_admin=False."""
    mock_google_user_payload = {
        "email": "new.trader@gmail.com",
        "email_verified": "true",
        "name": "New Trader",
        "picture": "https://lh3.googleusercontent.com/photo.jpg",
        "sub": "google-user-id-12345",
    }

    with patch("backend.api.auth.verify_google_id_token", new=AsyncMock(return_value=mock_google_user_payload)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/auth/google",
                json={"credential": "mock-valid-google-jwt-token"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            assert data["user"]["email"] == "new.trader@gmail.com"
            assert data["user"]["is_admin"] is False
            assert data["user"]["subscription_tier"] == "FREE"



@pytest.mark.asyncio
async def test_google_auth_regular_user_creation(mock_db):
    """Verify Google OAuth registers regular user."""
    mock_google_user_payload = {
        "email": "trader.joe@gmail.com",
        "email_verified": "true",
        "name": "Trader Joe",
        "sub": "google-user-id-67890",
    }

    with patch("backend.api.auth.verify_google_id_token", new=AsyncMock(return_value=mock_google_user_payload)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/auth/google",
                json={"credential": "mock-valid-google-jwt-token-2"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["user"]["email"] == "trader.joe@gmail.com"
            assert data["user"]["is_admin"] is False


# ---------------------------------------------------------------------------
# 5. Full-System Input Validation & 5-Minute Expiry Tests
# ---------------------------------------------------------------------------

def test_validate_email_syntax():
    """Verify RFC 5322 compliance, length checks, and CRLF injection defenses."""
    # Valid emails normalize to lowercase and stripped
    assert validate_email_syntax("Trader@Example.com  ") == "trader@example.com"
    assert validate_email_syntax("john.doe+algo@sub.domain.co.in") == "john.doe+algo@sub.domain.co.in"

    # Rejection of empty or too short / long
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_email_syntax("   ")

    with pytest.raises(ValueError, match="too short"):
        validate_email_syntax("a@b")

    with pytest.raises(ValueError, match="exceed 254 characters"):
        validate_email_syntax("a" * 250 + "@test.com")

    # CRLF and control character injection protection
    with pytest.raises(ValueError, match="illegal control characters"):
        validate_email_syntax("victim@gmail.com\r\nBcc: attacker@evil.com")

    with pytest.raises(ValueError, match="illegal control characters"):
        validate_email_syntax("victim@gmail.com\0evil")

    # Malformed syntax
    with pytest.raises(ValueError, match="valid email address"):
        validate_email_syntax("missing-at-sign.com")


def test_sanitize_display_name():
    """Verify XSS tag stripping, whitespace collapse, and length boundaries."""
    # HTML and Script tag stripping
    assert sanitize_display_name("<script>alert('xss')</script>John Doe") == "alert('xss')John Doe"
    assert sanitize_display_name("<b>Deepak</b>  Firake") == "Deepak Firake"

    # Whitespace collapsing
    assert sanitize_display_name("  Super   Trader  ") == "Super Trader"

    # Rejection of empty or invalid lengths
    with pytest.raises(ValueError, match="cannot be empty"):
        sanitize_display_name("   ")

    with pytest.raises(ValueError, match="at least 2 characters"):
        sanitize_display_name("A")

    with pytest.raises(ValueError, match="exceed 60 characters"):
        sanitize_display_name("A" * 65)


def test_validate_password_strength_and_dos_protection():
    """Verify password complexity requirements and 128-character bcrypt DoS defense."""
    # Valid passwords
    validate_password_strength("ValidPass123!")
    validate_password_strength("MySecureP@ssw0rd")

    # Too short (<8)
    with pytest.raises(ValueError, match="at least 8 characters"):
        validate_password_strength("Short1!")

    # Too long (>128 - DoS CPU attack protection)
    with pytest.raises(ValueError, match="exceed 128 characters"):
        validate_password_strength("A" * 129 + "1!")

    # Missing letter
    with pytest.raises(ValueError, match="at least one alphabetic character"):
        validate_password_strength("1234567890!@#$")

    # Missing digit or special character
    with pytest.raises(ValueError, match="at least one digit or special character"):
        validate_password_strength("OnlyAlphabetCharacters")


@pytest.mark.asyncio
async def test_otp_strict_5min_expiration():
    """Verify that an OTP strictly expires after 300 seconds (5 minutes)."""
    canonical = "expiry_test_user@gmail.com"
    raw_email = "expiry_test_user@gmail.com"
    _LOCAL_OTP_STORE.clear()

    mock_cache = {}

    async def mock_get(k):
        return mock_cache.get(k)

    async def mock_set(k, v, ttl=60):
        mock_cache[k] = v

    async def mock_del(k):
        mock_cache.pop(k, None)

    with patch("backend.services.email_service.cache_get", side_effect=mock_get), \
         patch("backend.services.email_service.cache_set", side_effect=mock_set), \
         patch("backend.services.email_service.cache_delete", side_effect=mock_del), \
         patch("backend.services.email_service.EmailOtpService.dispatch_email_async", new=AsyncMock(return_value=(True, ""))):

        # Initial request at t0
        t0 = 1000000.0
        with patch("time.time", return_value=t0):
            success, msg, cooldown = await email_otp_service.request_registration_otp(
                canonical_email=canonical,
                user_name="Test Expiry",
                hashed_password="hashed_pwd_123",
                raw_email=raw_email,
            )
            assert success is True

        cache_key = f"reg_otp:{canonical}"
        otp_val = (mock_cache.get(cache_key) or _LOCAL_OTP_STORE.get(cache_key))["otp"]

        # Verification at t0 + 290s (within 5 minutes) -> should succeed
        with patch("time.time", return_value=t0 + 290.0):
            valid, reason, user_data = await email_otp_service.verify_registration_otp(canonical, otp_val)
            assert valid is True
            assert "successfully verified" in reason.lower()

        # Re-request at t0 + 360s
        with patch("time.time", return_value=t0 + 360.0):
            success, msg, cooldown = await email_otp_service.request_registration_otp(
                canonical_email=canonical,
                user_name="Test Expiry",
                hashed_password="hashed_pwd_123",
                raw_email=raw_email,
            )
            assert success is True

        otp_val_2 = (mock_cache.get(cache_key) or _LOCAL_OTP_STORE.get(cache_key))["otp"]

        # Verification at t0 + 360 + 305s (expired by 5 seconds past 300s TTL)
        with patch("time.time", return_value=t0 + 360.0 + 305.0):
            valid, reason, user_data = await email_otp_service.verify_registration_otp(canonical, otp_val_2)
            assert valid is False
            assert "expired (valid for 5 minutes)" in reason


@pytest.mark.asyncio
async def test_otp_non_numeric_and_length_rejection():
    """Verify that non-numeric and wrong-length OTPs are strictly rejected."""
    canonical = "format_test@gmail.com"
    _LOCAL_OTP_STORE.clear()

    mock_cache = {}

    async def mock_get(k):
        return mock_cache.get(k)

    async def mock_set(k, v, ttl=60):
        mock_cache[k] = v

    async def mock_del(k):
        mock_cache.pop(k, None)

    with patch("backend.services.email_service.cache_get", side_effect=mock_get), \
         patch("backend.services.email_service.cache_set", side_effect=mock_set), \
         patch("backend.services.email_service.cache_delete", side_effect=mock_del), \
         patch("backend.services.email_service.EmailOtpService.dispatch_email_async", new=AsyncMock(return_value=(True, ""))):

        await email_otp_service.request_registration_otp(
            canonical_email=canonical,
            user_name="Format Tester",
            hashed_password="hashed_pwd_123",
            raw_email=canonical,
        )

        # Reject alphabet characters
        valid, reason, _ = await email_otp_service.verify_registration_otp(canonical, "ABCDEF")
        assert valid is False
        assert "exactly 6 numeric digits" in reason

        # Reject short length
        valid, reason, _ = await email_otp_service.verify_registration_otp(canonical, "123")
        assert valid is False
        assert "exactly 6 numeric digits" in reason

        # Reject long length
        valid, reason, _ = await email_otp_service.verify_registration_otp(canonical, "1234567")
        assert valid is False
        assert "exactly 6 numeric digits" in reason

