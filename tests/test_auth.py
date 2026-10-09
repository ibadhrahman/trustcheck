"""
Unit tests for authentication and seller onboarding routes.
"""
def test_register_success(client):
    payload = {
        "email": "priya@artisan.in",
        "password": "SecurePassword123!",
        "business_name": "Priya Ceramics",
        "contact_name": "Priya",
        "upi_id": "priya@okhdfcbank",
    }
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Verify we can use this token to fetch our profile
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["email"] == "priya@artisan.in"
    assert me_data["profile"]["business_name"] == "Priya Ceramics"
    assert me_data["seller_referral_code"].startswith("SL-")


def test_register_duplicate_email(client, test_user):
    payload = {
        "email": test_user.email,
        "password": "AnotherPassword123!",
        "business_name": "Duplicate Store",
        "upi_id": "dup@okhdfcbank",
    }
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"].lower()


def test_login_success(client, test_user):
    res = client.post("/api/auth/login", json={
        "email": test_user.email,
        "password": "Password123!",
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_password(client, test_user):
    res = client.post("/api/auth/login", json={
        "email": test_user.email,
        "password": "WrongPassword999",
    })
    assert res.status_code == 401
    assert "incorrect" in res.json()["detail"].lower()


def test_auth_me_authenticated(client, auth_headers, test_user):
    res = client.get("/api/auth/me", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == test_user.email
    assert data["profile"]["business_name"] == "Test Crafts Co"
    assert data["seller_referral_code"] == "SL-7K9M-4Q2X"


def test_auth_me_unauthenticated(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401
