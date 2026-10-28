"""
Automated Security Tests for Admin-Protected Swagger, OpenAPI & Health Telemetry.

Verifies:
1. GET /docs requires Admin credentials and returns 401 + WWW-Authenticate header when unauthenticated.
2. GET /openapi.json requires Admin credentials and returns 401 when unauthenticated.
3. GET /health/live allows internal/local probes without proxy headers.
4. GET /health/live blocks external untrusted clients without Admin credentials.
5. verify_admin_docs_access validates HTTP Basic Auth and JWT Bearer tokens for Admin users.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException

from backend.main import app
from backend.core.auth import verify_admin_docs_access, verify_admin_or_local


client = TestClient(app)


def test_docs_unauthenticated_returns_401():
    """Verify unauthenticated requests to /docs are rejected with HTTP 401 and Basic challenge."""
    response = client.get("/docs")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "Basic" in response.headers["WWW-Authenticate"]
    assert "Administrator credentials required" in response.json().get("detail", "")


def test_openapi_unauthenticated_returns_401():
    """Verify unauthenticated requests to /openapi.json are rejected with HTTP 401."""
    response = client.get("/openapi.json")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "Administrator credentials required" in response.json().get("detail", "")


def test_redoc_unauthenticated_returns_401():
    """Verify unauthenticated requests to /redoc are rejected with HTTP 401."""
    response = client.get("/redoc")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


def test_swagger_redirect():
    """Verify /swagger redirects to /docs."""
    response = client.get("/swagger", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_local_health_live_probe_succeeds():
    """Verify local/internal health probes without external proxy headers succeed with 200 OK."""
    # Default TestClient requests have no X-Forwarded-For header and client host 'testclient'
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "alive"
    assert "uptime_seconds" in data
    assert "timestamp" in data


def test_external_health_live_probe_requires_auth():
    """Verify external requests passing through reverse proxy (X-Forwarded-For) require Admin credentials."""
    response = client.get(
        "/health/live",
        headers={"X-Forwarded-For": "203.0.113.195", "X-Real-IP": "203.0.113.195"}
    )
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


@pytest.mark.asyncio
async def test_verify_admin_docs_access_with_valid_admin():
    """Verify verify_admin_docs_access grants access to active Admin users via HTTP Basic credentials."""
    from fastapi.security import HTTPBasicCredentials
    from backend.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.id = "admin-uuid-123"
    mock_user.email = "headadmin@stockai.com"
    mock_user.is_admin = True
    mock_user.is_active = True
    mock_user.hashed_password = "$2b$12$mockedhashedpassword"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    mock_request = MagicMock()
    mock_request.query_params = {}
    mock_request.cookies = {}

    credentials = HTTPBasicCredentials(username="headadmin@stockai.com", password="SecretAdminPassword123!")

    with patch("backend.core.auth.verify_password", return_value=True):
        user = await verify_admin_docs_access(
            request=mock_request,
            credentials=credentials,
            token=None,
            db=mock_db,
        )
        assert user == mock_user


@pytest.mark.asyncio
async def test_verify_admin_docs_access_rejects_non_admin():
    """Verify verify_admin_docs_access rejects regular non-admin users."""
    from fastapi.security import HTTPBasicCredentials
    from backend.models.user import User

    mock_user = MagicMock(spec=User)
    mock_user.is_admin = False  # Not an admin!
    mock_user.is_active = True
    mock_user.hashed_password = "$2b$12$mockedhashedpassword"

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute.return_value = mock_result

    mock_request = MagicMock()
    mock_request.query_params = {}
    mock_request.cookies = {}

    credentials = HTTPBasicCredentials(username="regularuser@stockai.com", password="Password123!")

    with patch("backend.core.auth.verify_password", return_value=True):
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_docs_access(
                request=mock_request,
                credentials=credentials,
                token=None,
                db=mock_db,
            )
        assert exc_info.value.status_code == 401

