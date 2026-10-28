import pytest
import time
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.core.fraud_detection import FraudDetectionEngine, fraud_detection_engine
from backend.core.auth import create_access_token


@pytest.fixture
def clean_engine():
    """Provides a fresh isolated instance of FraudDetectionEngine."""
    return FraudDetectionEngine()


def test_haversine_distance_accuracy(clean_engine):
    """Test Haversine distance between Mumbai (19.0760, 72.8777) and Delhi (28.7041, 77.1025)."""
    # Expected distance is approx 1,148 km
    dist = clean_engine.calculate_haversine_distance(19.0760, 72.8777, 28.7041, 77.1025)
    assert 1140.0 < dist < 1160.0


def test_normal_travel_velocity_accepted(clean_engine):
    """Travel between Mumbai and Pune (~120 km) over 3 hours (40 km/h) is completely valid."""
    user_id = "test-user-normal-travel"
    t0 = time.time()
    
    # 1st login in Mumbai
    is_imp1, dist1, vel1, _ = clean_engine.check_impossible_travel(user_id, 19.0760, 72.8777, current_time=t0)
    assert not is_imp1

    # 2nd login in Pune 3 hours later
    t1 = t0 + (3 * 3600)
    is_imp2, dist2, vel2, reason = clean_engine.check_impossible_travel(user_id, 18.5204, 73.8567, current_time=t1)
    assert not is_imp2
    assert 100.0 < dist2 < 140.0
    assert vel2 < 60.0
    assert reason is None


def test_impossible_travel_anomaly_flagged(clean_engine):
    """Login from Mumbai, then 20 minutes later from Frankfurt (~6,500 km) is physically impossible."""
    user_id = "test-user-impossible-travel"
    t0 = time.time()

    # 1st login in Mumbai
    clean_engine.check_impossible_travel(user_id, 19.0760, 72.8777, current_time=t0)

    # 2nd login in Frankfurt 20 minutes (1200s) later
    t1 = t0 + 1200
    is_imp, dist, vel, reason = clean_engine.check_impossible_travel(user_id, 50.1109, 8.6821, current_time=t1)
    assert is_imp
    assert dist > 6000.0
    assert vel > 800.0
    assert "Impossible travel velocity" in reason


def test_device_fingerprint_shift_detection(clean_engine):
    """Changing User-Agent / subnet in active session triggers device shift warning."""
    user_id = "test-user-device-shift"
    t0 = time.time()

    # Initial device: Chrome on Windows from 103.21.244.15
    is_shift1, _ = clean_engine.check_device_fingerprint_shift(
        user_id, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0", "103.21.244.15", current_time=t0
    )
    assert not is_shift1

    # Changed device 5 minutes later: iPhone Safari from 45.12.88.2
    t1 = t0 + 300
    is_shift2, reason = clean_engine.check_device_fingerprint_shift(
        user_id, "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile Safari/604.1", "45.12.88.2", current_time=t1
    )
    assert is_shift2
    assert "Device fingerprint changed" in reason


def test_distributed_credential_stuffing_detection(clean_engine):
    """Multiple failed attempts from same /24 subnet targeting multiple accounts triggers alert."""
    subnet_ip = "192.168.1.50"
    
    # 4 distinct accounts targeted from 192.168.1.0/24 subnet
    clean_engine.record_failed_attempt("192.168.1.10", "victim1@example.com")
    clean_engine.record_failed_attempt("192.168.1.12", "victim2@example.com")
    clean_engine.record_failed_attempt("192.168.1.14", "victim3@example.com")
    
    is_stuffing, reason = clean_engine.record_failed_attempt("192.168.1.18", "victim4@example.com")
    assert is_stuffing
    assert "Distributed credential stuffing detected" in reason
    assert "192.168.1.0/24" in reason


def test_composite_risk_evaluation_scoring(clean_engine):
    """Clean login scores 0/LOW; impossible travel + suspicious email elevates to CRITICAL/BLOCKED."""
    # 1. Clean evaluation
    clean_eval = clean_engine.evaluate_login_risk(
        email="realtrader@gmail.com",
        user_id="user-123",
        ip_address="103.21.244.10",
        user_agent="Mozilla/5.0 Clean Browser",
        is_registration=False
    )
    assert clean_eval.risk_score == 0
    assert clean_eval.risk_level == "LOW"
    assert not clean_eval.is_blocked

    # 2. Impossible travel combined with disposable email pattern
    t0 = time.time()
    clean_engine.check_impossible_travel("hacker-999", 19.0760, 72.8777, current_time=t0)
    
    high_risk_eval = clean_engine.evaluate_login_risk(
        email="hacker@mailinator.com",
        user_id="hacker-999",
        ip_address="185.220.101.5",
        user_agent="curl/7.68.0",
        client_lat=51.5074,
        client_lon=-0.1278,  # London 1 second later
        is_registration=True
    )
    assert high_risk_eval.risk_score >= 70
    assert high_risk_eval.risk_level == "CRITICAL"
    assert high_risk_eval.is_blocked
    assert len(high_risk_eval.anomalies) >= 2


@pytest.mark.asyncio
async def test_security_fraud_status_api():
    """Verify GET /api/auth/security/fraud-status returns CERT-In compliant audit metadata."""
    from backend.models.user import User
    from backend.core.auth import get_current_user
    import uuid

    mock_user = User(
        id=uuid.uuid4(),
        email="testtrader@gmail.com",
        name="Test Trader",
        hashed_password="hashed_pwd_dummy",
        is_active=True,
        is_admin=False,
        subscription_tier="PRO"
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/auth/security/fraud-status",
                headers={"Authorization": "Bearer dummy-token"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "active"
            assert data["cert_in_retention_days"] == 180
            assert "risk_level" in data
            assert "risk_score" in data
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_security_telemetry_api():
    """Verify POST /api/auth/security/telemetry evaluates client coordinates."""
    from backend.models.user import User
    from backend.core.auth import get_current_user
    import uuid

    mock_user = User(
        id=uuid.uuid4(),
        email="testtrader@gmail.com",
        name="Test Trader",
        hashed_password="hashed_pwd_dummy",
        is_active=True,
        is_admin=False,
        subscription_tier="PRO"
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {
                "lat": 19.0760,
                "lon": 72.8777,
                "screen_resolution": "1920x1080",
                "consent_version": "2023.1"
            }
            resp = await client.post(
                "/api/auth/security/telemetry",
                headers={"Authorization": "Bearer dummy-token"},
                json=payload
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["acknowledged"] is True
            assert data["impossible_travel_flagged"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)

