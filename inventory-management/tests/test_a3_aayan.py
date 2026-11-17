from unittest.mock import patch

import pytest


def _create_mouse(client):
    response = client.post(
        "/products",
        json={
            "name": "Mouse",
            "sku": "MOUSE-A3",
            "quantity_on_hand": 10,
            "reorder_level": 10,
        },
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def _assert_successful_alert_transaction(client, response, product_id):
    assert response.status_code == 201
    transaction = response.get_json()
    assert transaction["notification_sent"] is True

    stock = client.get(f"/products/{product_id}/stock-level").get_json()
    assert stock["quantity_on_hand"] == 3

    saved = client.get("/transactions").get_json()
    assert len(saved) == 1
    assert saved[0]["id"] == transaction["id"]
    assert saved[0]["product_id"] == product_id
    assert saved[0]["type"] == "OUT"
    assert saved[0]["quantity"] == 7


def test_low_stock_alert_success_with_stub(client, monkeypatch):
    product_id = _create_mouse(client)
    monkeypatch.setattr(
        "app.routes.transactions.send_notification",
        lambda recipient, subject, message: True,
    )

    response = client.post(
        "/transactions",
        json={"product_id": product_id, "type": "OUT", "quantity": 7},
    )

    _assert_successful_alert_transaction(client, response, product_id)


def test_low_stock_alert_sends_expected_notification(client):
    product_id = _create_mouse(client)

    with patch(
        "app.routes.transactions.send_notification", return_value=True
    ) as mock_send:
        response = client.post(
            "/transactions",
            json={"product_id": product_id, "type": "OUT", "quantity": 7},
        )

    _assert_successful_alert_transaction(client, response, product_id)
    mock_send.assert_called_once_with(
        "Inventory manager",
        "Low Stock Alert",
        "Mouse inventory has dropped to 3 units. The minimum threshold is 10 units.",
    )