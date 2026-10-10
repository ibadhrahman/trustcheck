"""Buyer order outcomes secured by private, unguessable order references."""
import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image
import pytest

from app.auth import create_access_token
from app.config import settings
from app.models import AuditEvent, BuyerAccount, Order, OrderOutcome, User


@pytest.fixture
def private_upload_dir(monkeypatch, request):
    workspace = Path.cwd().resolve()
    root = (workspace / f".test-private-evidence-{uuid.uuid4().hex}").resolve()
    if root.parent != workspace or not root.name.startswith(".test-private-evidence-"):
        raise RuntimeError("Test evidence directory escaped the workspace.")
    root.mkdir()
    monkeypatch.setattr(settings, "private_upload_dir", str(root))

    def cleanup():
        for child in root.iterdir():
            if child.is_file():
                child.unlink()
        root.rmdir()

    request.addfinalizer(cleanup)
    return root


def _reference_headers(code):
    return {"X-Buyer-Access-Code": code}


def _image_upload():
    data = io.BytesIO()
    Image.new("RGB", (8, 8), color=(80, 120, 160)).save(data, format="JPEG")
    return ("photo.jpg", data.getvalue(), "image/jpeg")


def _order(client, auth_headers, db_session, amount=100.0, status="seller_confirmed"):
    response = client.post("/api/orders", json={"expected_amount": amount}, headers=auth_headers)
    assert response.status_code == 201
    result = response.json()
    order = db_session.query(Order).filter(Order.id == result["id"]).one()
    order.status = status
    db_session.commit()
    return result


def _lookup(client, code):
    return client.post("/api/buyer/order/lookup", json={"access_code": code})


def test_private_reference_opens_one_order_without_account_and_positive_outcome_is_not_a_report(
    client, auth_headers, db_session, private_upload_dir
):
    created = _order(client, auth_headers, db_session)

    assert created["buyer_access_code"].startswith("TXN-")
    assert _lookup(client, created["referral_code"]).status_code == 404
    assert _lookup(client, created["buyer_access_code"]).status_code == 200
    assert _lookup(client, created["buyer_access_code"].lower()).status_code == 200
    assert _lookup(client, f"http://127.0.0.1:8000/buyer.html#claim={created['buyer_access_code']}").status_code == 200
    opened = _lookup(client, created["buyer_access_code"]).json()
    assert opened["id"] == created["id"]
    assert opened["status"] == "seller_confirmed"
    assert opened["can_submit_outcome"] is True
    assert client.post("/api/buyer/auth/register", json={}).status_code in {404, 405}

    result = client.post(
        "/api/buyer/order/outcome",
        data={"outcome": "received_as_described", "confirmed_received": "true"},
        files={"photo": _image_upload()},
        headers=_reference_headers(created["buyer_access_code"]),
    )
    assert result.status_code == 201
    assert result.json()["outcome"] == "received"
    assert result.json()["status"] == "received"
    evidence_id = result.json()["events"][0]["evidence_ids"][0]
    assert client.get(f"/api/buyer/order/evidence/{evidence_id}").status_code == 404
    assert client.get(
        f"/api/buyer/order/evidence/{evidence_id}",
        headers=_reference_headers("x" * 40),
    ).status_code == 404
    assert client.get(
        f"/api/buyer/order/evidence/{evidence_id}",
        headers=_reference_headers(created["buyer_access_code"]),
    ).status_code == 200

    seller_reports = client.get("/api/seller/order-outcomes", headers=auth_headers)
    assert seller_reports.status_code == 200
    assert seller_reports.json()[0]["outcome"] == "received"
    assert client.get(
        f"/api/seller/order-outcomes/{result.json()['id']}/evidence/{evidence_id}",
        headers=auth_headers,
    ).status_code == 200


def test_problem_report_requires_receipt_or_explicit_not_received_and_keeps_resolution_history(
    client, auth_headers, db_session
):
    created = _order(client, auth_headers, db_session)
    path = "/api/buyer/order/outcome"
    headers = _reference_headers(created["buyer_access_code"])

    damaged = {"outcome": "report_problem", "reason": "damaged_item", "description": "The item arrived damaged."}
    assert client.post(path, data=damaged, headers=headers).status_code == 409

    reported = client.post(path, data={**damaged, "confirmed_received": "true"}, headers=headers)
    assert reported.status_code == 201
    assert reported.json()["status"] == "awaiting_seller"
    assert client.post(path, data={**damaged, "confirmed_received": "true"}, headers=headers).status_code == 409
    assert client.post(
        f"/api/orders/{created['id']}/buyer-access-code", headers=auth_headers
    ).status_code == 409
    assert db_session.query(AuditEvent).filter(AuditEvent.event_type == "buyer_problem_reported").count() == 1

    offered = client.post(
        f"/api/orders/{created['id']}/outcome/offer",
        json={"resolution_type": "replacement", "message": "We will send a replacement."},
        headers=auth_headers,
    )
    assert offered.status_code == 200
    assert offered.json()["status"] == "resolution_offered"

    still_open = client.post(
        "/api/buyer/order/outcome/resolution",
        json={"resolved": False, "message": "I have not received the replacement."},
        headers=headers,
    )
    assert still_open.status_code == 200
    assert still_open.json()["status"] == "awaiting_seller"

    client.post(
        f"/api/orders/{created['id']}/outcome/offer",
        json={"resolution_type": "refund", "message": "Refund sent."},
        headers=auth_headers,
    )
    resolved = client.post(
        "/api/buyer/order/outcome/resolution",
        json={"resolved": True},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert [event["event_type"] for event in resolved.json()["events"]] == [
        "problem_reported", "seller_resolution_offered", "buyer_says_unresolved",
        "seller_resolution_offered", "buyer_confirmed_resolved",
    ]


def test_buyer_can_report_order_not_received_without_checking_a_received_box(
    client, auth_headers, db_session
):
    created = _order(client, auth_headers, db_session)
    result = client.post(
        "/api/buyer/order/outcome",
        data={
            "outcome": "report_problem",
            "confirmed_not_received": "true",
            "reason": "not_received",
            "description": "The order has not arrived.",
        },
        headers=_reference_headers(created["buyer_access_code"]),
    )
    assert result.status_code == 201
    assert result.json()["buyer_received_at"] is None
    assert result.json()["reason"] == "not_received"
    assert _lookup(client, created["buyer_access_code"]).json()["outcome"]["status"] == "awaiting_seller"


def test_invalid_or_other_order_reference_cannot_read_or_change_this_order(
    client, auth_headers, db_session
):
    first = _order(client, auth_headers, db_session, 100)
    second = _order(client, auth_headers, db_session, 200)
    assert _lookup(client, "not-a-valid-private-reference").status_code == 404
    assert _lookup(client, first["buyer_access_code"]).json()["id"] == first["id"]
    assert _lookup(client, second["buyer_access_code"]).json()["id"] == second["id"]

    response = client.post(
        "/api/buyer/order/outcome",
        data={"outcome": "report_problem", "confirmed_received": "true", "reason": "wrong_item", "description": "Wrong."},
        headers=_reference_headers(first["buyer_access_code"]),
    )
    assert response.status_code == 201
    assert _lookup(client, second["buyer_access_code"]).json()["outcome"] is None
    assert client.get("/api/buyer/orders").status_code == 404
    assert client.get("/api/buyer/auth/me").status_code == 404

    other_seller = User(email="second-seller@example.com", hashed_password="unused", is_active=True)
    db_session.add(other_seller)
    db_session.commit()
    other_headers = {"Authorization": f"Bearer {create_access_token(other_seller.id)}"}
    assert client.get("/api/seller/order-outcomes", headers=other_headers).json() == []
    assert client.post(
        f"/api/orders/{first['id']}/outcome/offer",
        json={"resolution_type": "refund"},
        headers=other_headers,
    ).status_code == 404
    assert client.get("/api/seller/order-outcomes").status_code == 401


def test_seller_can_rotate_private_reference_and_old_reference_stops_working(
    client, auth_headers, db_session
):
    created = _order(client, auth_headers, db_session, status="pending")
    legacy_buyer = BuyerAccount(email="legacy@example.com", hashed_password="unused")
    db_session.add(legacy_buyer)
    db_session.flush()
    order = db_session.query(Order).filter(Order.id == created["id"]).one()
    order.buyer_id = legacy_buyer.id
    order.buyer_access_hmac = None
    db_session.commit()

    rotated = client.post(
        f"/api/orders/{created['id']}/buyer-access-code", headers=auth_headers
    )
    assert rotated.status_code == 200
    assert _lookup(client, rotated.json()["access_code"]).status_code == 200
    assert _lookup(client, created["buyer_access_code"]).status_code == 404

    other = User(email="rotate-other@example.com", hashed_password="unused", is_active=True)
    db_session.add(other)
    db_session.commit()
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id)}"}
    assert client.post(f"/api/orders/{created['id']}/buyer-access-code", headers=other_headers).status_code == 404
    assert client.post(f"/api/orders/{created['id']}/buyer-access-code").status_code == 401


def test_warning_counts_distinct_unresolved_orders_after_response_deadline(
    client, auth_headers, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "order_issue_warning_threshold", 3)
    created_orders = []
    for amount in (25, 26, 27):
        created = _order(client, auth_headers, db_session, amount)
        report = client.post(
            "/api/buyer/order/outcome",
            data={"outcome": "report_problem", "confirmed_received": "true", "reason": "wrong_item", "description": "Different item received."},
            headers=_reference_headers(created["buyer_access_code"]),
        )
        assert report.status_code == 201
        row = db_session.query(OrderOutcome).filter(OrderOutcome.order_id == created["id"]).one()
        row.response_deadline = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
        created_orders.append(created)
    db_session.commit()

    warning_url = "/api/orders/referral/SL-7K9M-4Q2X/warning"
    assert client.get(warning_url).json()["warning"] is False
    for created in created_orders:
        row = db_session.query(OrderOutcome).filter(OrderOutcome.order_id == created["id"]).one()
        row.response_deadline = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    db_session.commit()

    warning = client.get(warning_url).json()
    assert warning["warning"] is True
    assert warning["message"] == "Multiple unresolved order issues have been reported. Review before purchasing."
    assert "Different item" not in warning["message"]

    client.post(
        f"/api/orders/{created_orders[0]['id']}/outcome/offer",
        json={"resolution_type": "refund"},
        headers=auth_headers,
    )
    client.post(
        "/api/buyer/order/outcome/resolution",
        json={"resolved": True},
        headers=_reference_headers(created_orders[0]["buyer_access_code"]),
    )
    assert client.get(warning_url).json()["warning"] is False
