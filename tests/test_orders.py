"""
Unit tests for Orders management and referral code resolution.
"""
from app.auth import create_access_token
from app.models import SellerProfile, User


def test_create_order(client, auth_headers, test_user):
    payload = {
        "expected_amount": 750.0,
        "customer_label": "buyer_rohit",
        "private_note": "Red silk scarf delivery to Mumbai",
    }
    res = client.post("/api/orders", json=payload, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["expected_amount"] == 750.0
    assert data["status"] == "pending"
    assert data["referral_code"].startswith("TC-")
    assert data["expected_upi_id"] == "testcrafts@okhdfcbank"
    assert "TC-" in data["shareable_message"]


def test_list_orders_isolation(client, auth_headers, test_user, db_session):
    # Create order for test_user
    client.post("/api/orders", json={"expected_amount": 100.0}, headers=auth_headers)

    # Create another seller
    other_user = User(email="other@seller.com", hashed_password="pw", is_active=True)
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)
    other_profile = SellerProfile(user_id=other_user.id, business_name="Other Shop", upi_id="other@upi")
    db_session.add(other_profile)
    db_session.commit()

    other_token = create_access_token(other_user.id)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # other_user creates an order
    client.post("/api/orders", json={"expected_amount": 999.0}, headers=other_headers)

    # test_user lists orders — should only see their own order (100.0)
    res = client.get("/api/orders", headers=auth_headers)
    assert res.status_code == 200
    orders = res.json()
    assert len(orders) == 1
    assert orders[0]["expected_amount"] == 100.0


def test_get_order_by_referral_code(client, auth_headers, test_user):
    create_res = client.post("/api/orders", json={"expected_amount": 350.0}, headers=auth_headers)
    ref_code = create_res.json()["referral_code"]

    res = client.get(f"/api/orders/referral/{ref_code}", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["referral_code"] == ref_code
    assert data["expected_amount"] == 350.0


def test_referral_code_ownership_enforcement(client, auth_headers, test_user, db_session):
    # test_user creates an order
    create_res = client.post("/api/orders", json={"expected_amount": 420.0}, headers=auth_headers)
    ref_code = create_res.json()["referral_code"]

    # another seller tries to look up test_user's code
    other_user = User(email="intruder@seller.com", hashed_password="pw", is_active=True)
    db_session.add(other_user)
    db_session.commit()
    other_token = create_access_token(other_user.id)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    res = client.get(f"/api/orders/referral/{ref_code}", headers=other_headers)
    # Strictly enforced — must return 403 or 404 to prevent unauthorized access
    assert res.status_code in (403, 404)


def test_cancel_order(client, auth_headers, test_user):
    create_res = client.post("/api/orders", json={"expected_amount": 500.0}, headers=auth_headers)
    order_id = create_res.json()["id"]

    res = client.post(f"/api/orders/{order_id}/cancel", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
