"""
Unit tests for Mobile Fyers Token Manager endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

from backend.api.settings import (
    _extract_auth_code,
    get_fyers_status,
    get_fyers_auth_url,
    update_fyers_token,
    FyersTokenUpdateRequest,
)


def test_extract_auth_code_from_full_url():
    url = "https://trade.fyers.in/api-login/redirect-uri/index.html?s=ok&code=200&auth_code=sample_code_12345&state=None"
    assert _extract_auth_code(url) == "sample_code_12345"


def test_extract_auth_code_from_query_string():
    raw = "auth_code=code_xyz_987&state=test"
    assert _extract_auth_code(raw) == "code_xyz_987"


def test_extract_auth_code_raw():
    assert _extract_auth_code("raw_code_abc") == "raw_code_abc"


@pytest.mark.asyncio
async def test_get_fyers_status_active():
    mock_user = MagicMock(is_admin=True, email="admin@stockai.com")
    mock_db = AsyncMock()

    with patch("backend.api.settings._find_env_path", return_value=None), \
         patch("backend.api.settings.os.getenv", side_effect=lambda k, *args: "MOCK_CLIENT" if "CLIENT" in str(k) else "MOCK_TOKEN"), \
         patch("backend.api.settings.fyersModel.FyersModel") as mock_fyers_cls:
        
        instance = MagicMock()
        instance.get_profile.return_value = {
            "s": "ok",
            "data": {"name": "Dipak Firake", "fy_id": "XY12345"}
        }
        mock_fyers_cls.return_value = instance

        res = await get_fyers_status(db=mock_db, current_user=mock_user)
        assert res["configured"] is True
        assert res["connected"] is True
        assert res["token_status"] == "ACTIVE"
        assert res["name"] == "Dipak Firake"
        assert res["fy_id"] == "XY12345"
        assert res["masked_fy_id"] == "XY***45"
        assert "ping_ms" in res
        assert "checked_at_ist" in res
        assert res["fyers_live_ping"] is True


@pytest.mark.asyncio
async def test_get_fyers_status_expired():
    mock_user = MagicMock(is_admin=True, email="admin@stockai.com")
    mock_db = AsyncMock()

    with patch("backend.api.settings._find_env_path", return_value=None), \
         patch("backend.api.settings.os.getenv", side_effect=lambda k, *args: "MOCK_CLIENT" if "CLIENT" in str(k) else "MOCK_TOKEN"), \
         patch("backend.api.settings.fyersModel.FyersModel") as mock_fyers_cls:
        
        instance = MagicMock()
        instance.get_profile.return_value = {
            "s": "error",
            "message": "Token has expired."
        }
        mock_fyers_cls.return_value = instance

        res = await get_fyers_status(db=mock_db, current_user=mock_user)
        assert res["configured"] is True
        assert res["connected"] is False
        assert res["token_status"] == "EXPIRED"
        assert res["fyers_live_ping"] is False
        assert "ping_ms" in res
        assert "checked_at_ist" in res


@pytest.mark.asyncio
async def test_get_fyers_auth_url():
    mock_admin = MagicMock(is_admin=True, email="admin@stockai.com")
    mock_db = AsyncMock()

    with patch("backend.api.settings._find_env_path", return_value=None), \
         patch("backend.api.settings.os.getenv", side_effect=lambda k: "MOCK_VAL"), \
         patch("backend.api.settings.fyersModel.SessionModel") as mock_session_cls:
        
        instance = MagicMock()
        instance.generate_authcode.return_value = "https://api-t1.fyers.in/api/v3/generate-authcode?sample=1"
        mock_session_cls.return_value = instance

        res = await get_fyers_auth_url(db=mock_db, admin=mock_admin)
        assert "auth_url" in res
        assert "fyers.in" in res["auth_url"]


@pytest.mark.asyncio
async def test_update_fyers_token_success():
    mock_admin = MagicMock(id="admin-id", is_admin=True, email="admin@stockai.com")
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_res

    url_input = "https://trade.fyers.in/api-login/redirect-uri/index.html?s=ok&code=200&auth_code=valid_code_123"

    with patch("backend.api.settings._find_env_path", return_value=None), \
         patch("backend.api.settings.os.getenv", side_effect=lambda k, *args, **kwargs: "MOCK_VAL"), \
         patch("backend.api.settings.fyersModel.SessionModel") as mock_session_cls, \
         patch("backend.api.settings.fyersModel.FyersModel") as mock_fyers_cls, \
         patch("backend.api.settings.dotenv.set_key") as mock_set_key, \
         patch("backend.services.fyers_stream.fyers_stream_service.stop", new_callable=AsyncMock), \
         patch("backend.services.fyers_stream.fyers_stream_service.start", new_callable=AsyncMock):
        
        session_inst = MagicMock()
        session_inst.generate_token.return_value = {
            "s": "ok",
            "access_token": "new_live_jwt_access_token_999"
        }
        mock_session_cls.return_value = session_inst

        fyers_inst = MagicMock()
        fyers_inst.get_profile.return_value = {
            "s": "ok",
            "data": {"name": "Dipak Firake", "fy_id": "XY12345"}
        }
        mock_fyers_cls.return_value = fyers_inst

        req = FyersTokenUpdateRequest(auth_input=url_input)
        res = await update_fyers_token(request=req, db=mock_db, admin=mock_admin)

        assert res["status"] == "success"
        assert res["name"] == "Dipak Firake"
        assert res["fy_id"] == "XY12345"


@pytest.mark.asyncio
async def test_get_all_settings_non_admin_filtering():
    from backend.api.settings import get_all_settings
    from backend.models.settings import SystemSettings

    mock_db = AsyncMock()
    mock_item_risk = SystemSettings(key="default_risk_pct", value="2.0", value_type="float")
    mock_item_fyers = SystemSettings(key="fyers_access_token", value="super_secret_token", value_type="string")
    mock_item_client = SystemSettings(key="fyers_client_id", value="secret_client_id", value_type="string")

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_item_risk, mock_item_fyers, mock_item_client]
    mock_db.execute.return_value = mock_result

    # 1. Non-admin user
    non_admin_user = MagicMock(is_admin=False, email="user@regular.com")
    res_non_admin = await get_all_settings(db=mock_db, current_user=non_admin_user)

    assert "default_risk_pct" in res_non_admin
    assert "fyers_access_token" not in res_non_admin
    assert "fyers_client_id" not in res_non_admin

    # 2. Admin user
    admin_user = MagicMock(is_admin=True, email="admin@stockai.com")
    res_admin = await get_all_settings(db=mock_db, current_user=admin_user)

    assert "default_risk_pct" in res_admin
    assert "fyers_access_token" in res_admin
    assert "fyers_client_id" in res_admin

