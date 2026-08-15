"""Tests for authentication and user onboarding."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.config.database import get_db
from src.models.user import User, UserPreference

client = TestClient(app)

# Create a mock database session
mock_db_session = MagicMock()


def override_get_db():
    yield mock_db_session


@pytest.fixture(autouse=True)
def reset_mock():
    mock_db_session.reset_mock()
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


def test_google_login_redirect():
    response = client.get("/auth/google", follow_redirects=False)
    assert response.status_code == 307
    assert "accounts.google.com" in response.headers["location"]


@patch("src.api.auth.exchange_code_for_profile", new_callable=AsyncMock)
def test_google_callback_success(mock_exchange):
    test_email = "test@example.com"
    test_user_id = uuid.uuid4()

    mock_exchange.return_value = {
        "email": test_email,
        "name": "Test User",
        "given_name": "Test",
    }

    # Mock DB queries
    mock_db_session.query.return_value.filter.return_value.first.return_value = None

    # When flush is called, assign an ID to the added user
    def mock_flush():
        # Find the user object in the session.add calls
        for call in mock_db_session.add.call_args_list:
            obj = call[0][0]
            if isinstance(obj, User):
                obj.id = test_user_id

    mock_db_session.flush.side_effect = mock_flush

    response = client.get("/auth/google/callback?code=dummy_code")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]

    # Mock for /me endpoint
    mock_user = User(id=test_user_id, email=test_email, name="Test User", is_onboarded=False, is_active=True)
    mock_user.preferences = UserPreference(user_id=test_user_id, categories=[])
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_user

    # Test /api/users/me endpoint
    me_response = client.get("/api/users/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["email"] == test_email
    assert me_data["is_onboarded"] is False
    assert me_data["categories"] == []

    # Test /api/users/onboarding endpoint
    onboard_payload = {"primary_language": "en", "categories": ["technology", "science", "health"]}
    onboard_response = client.post(
        "/api/users/onboarding", headers={"Authorization": f"Bearer {access_token}"}, json=onboard_payload
    )
    assert onboard_response.status_code == 200
    onboard_data = onboard_response.json()
    assert onboard_data["is_onboarded"] is True
    assert onboard_data["primary_language"] == "en"
    assert set(onboard_data["categories"]) == {"technology", "science", "health"}

    # Check refresh token endpoint
    refresh_payload = {"refresh_token": refresh_token}
    refresh_response = client.post("/auth/refresh", json=refresh_payload)
    assert refresh_response.status_code == 200
    refresh_data = refresh_response.json()
    assert "access_token" in refresh_data
    assert "refresh_token" in refresh_data

    # Test invalid access token
    bad_me = client.get("/api/users/me", headers={"Authorization": "Bearer bad_token"})
    assert bad_me.status_code == 401


def test_refresh_with_invalid_token():
    refresh_payload = {"refresh_token": "bad_token"}
    refresh_response = client.post("/auth/refresh", json=refresh_payload)
    assert refresh_response.status_code == 401
