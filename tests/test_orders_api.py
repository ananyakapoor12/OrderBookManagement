"""
test_orders_api.py — API-level tests for create-order HTTP semantics.

These tests verify that idempotent duplicate submissions return HTTP 200 while
new orders return HTTP 201 Created.
"""
from fastapi.testclient import TestClient

from app.main import app


def test_create_order_returns_201_for_new_submission():
    with TestClient(app) as client:
        response = client.post(
            "/orders/",
            json={
                "client_order_id": "api-create-001",
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": 100,
                "price": 150.0,
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["client_order_id"] == "api-create-001"
    assert payload["status"] == "NEW"


def test_create_order_returns_200_for_duplicate_idempotent_submission():
    with TestClient(app) as client:
        first = client.post(
            "/orders/",
            json={
                "client_order_id": "api-idempotent-001",
                "symbol": "MSFT",
                "side": "BUY",
                "quantity": 50,
                "price": 300.0,
            },
        )
        second = client.post(
            "/orders/",
            json={
                "client_order_id": "api-idempotent-001",
                "symbol": "MSFT",
                "side": "BUY",
                "quantity": 50,
                "price": 300.0,
            },
        )

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
