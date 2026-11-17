"""Assignment 3 coverage-directed tests for Brian (Member B)."""

from unittest.mock import patch
import pytest

from app import store


def _create_product(client, *, name="Test Product", sku="TP-1", quantity=10):
    response = client.post(
        "/products",
        json={"name": name, "sku": sku, "quantity_on_hand": quantity},
    )
    assert response.status_code == 201
    return response.get_json()


def _create_purchase_order(client, *, quantity_ordered=6):
    supplier_response = client.post(
        "/suppliers",
        json={"name": "Test Supplier", "contact_email": "supplier@example.com"},
    )
    assert supplier_response.status_code == 201

    product = _create_product(client, quantity=10)
    po_response = client.post(
        "/purchase-orders",
        json={
            "supplier_id": supplier_response.get_json()["id"],
            "product_id": product["id"],
            "quantity_ordered": quantity_ordered,
        },
    )
    assert po_response.status_code == 201
    return po_response.get_json()


def test_update_product_rejects_more_than_three_location_tags(client):
    """An update with more than three location tags is rejected without changing the product."""
    _create_product(client)

    response = client.put(
        "/products/1",
        json={"locations": ["Warehouse A", "Aisle 2", "Bin 4", "Overflow"]},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "A product can have at most 3 location tags"
    }
    product = client.get("/products/1").get_json()
    assert product["locations"] == []


def test_update_product_accepts_up_to_three_location_tags(client):
    """A valid location-tag update is saved and returned by the product endpoint."""
    _create_product(client)
    locations = ["Warehouse A", "Aisle 2", "Bin 4"]

    response = client.put("/products/1", json={"locations": locations})

    assert response.status_code == 200
    assert response.get_json()["locations"] == locations
    assert client.get("/products/1").get_json()["locations"] == locations


def test_reconcile_returns_not_found_for_unknown_product(client):
    """Reconciling a product ID that does not exist returns a 404 response."""
    response = client.post(
        "/products/999/reconcile",
        json={"physical_count": 4, "reason": "Cycle count"},
    )

    assert response.status_code == 404
    assert response.get_json() == {"error": "Product not found"}


@pytest.mark.parametrize("physical_count", [-1, 2.5, "12"])
def test_reconcile_rejects_invalid_physical_count_and_preserves_stock(
    client, physical_count
):
    """A physical count must be a non-negative integer and invalid input changes no stock."""
    _create_product(client, quantity=10)

    response = client.post(
        "/products/1/reconcile",
        json={"physical_count": physical_count, "reason": "Cycle count"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "Valid non-negative physical_count is required"
    }
    assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == 10
    assert client.get("/products/reconciliations").get_json() == []


def test_reconcile_initializes_history_when_it_does_not_exist(client, monkeypatch):
    """The first successful reconciliation creates the reconciliation-history list."""
    # Force the first-use condition regardless of whether another test previously
    # created store.reconciliations. Restore any prior value after this test.
    monkeypatch.delattr(store, "reconciliations", raising=False)
    _create_product(client, quantity=10)

    try:
        response = client.post(
            "/products/1/reconcile",
            json={"physical_count": 7, "reason": "Damaged units removed"},
        )

        assert response.status_code == 200
        record = response.get_json()
        assert record["previous_quantity"] == 10
        assert record["physical_count"] == 7
        assert record["net_difference"] == -3
        assert record["reason"] == "Damaged units removed"
        assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == 7
        assert client.get("/products/reconciliations").get_json() == [record]
    finally:
        # store.reset() does not remove this dynamically-created attribute.
        if hasattr(store, "reconciliations"):
            delattr(store, "reconciliations")


def test_receive_purchase_order_rejects_negative_received_quantity(client):
    """A negative received quantity is rejected without receiving the PO or changing stock."""
    purchase_order = _create_purchase_order(client, quantity_ordered=6)

    response = client.put(
        f"/purchase-orders/{purchase_order['id']}/receive",
        json={"received_quantity": -1},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error": "received_quantity must be a non-negative integer"
    }
    assert client.get(f"/purchase-orders/{purchase_order['id']}").get_json()["status"] == "pending"
    assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == 10
    assert client.get("/transactions").get_json() == []


@pytest.mark.parametrize("quantity", [0, -3, 1.5])
def test_transaction_rejects_non_positive_or_non_integer_quantity(client, quantity):
    """Transaction quantities must be positive integers and invalid requests have no effect."""
    _create_product(client, quantity=10)

    response = client.post(
        "/transactions",
        json={"product_id": 1, "type": "IN", "quantity": quantity},
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "quantity must be a positive integer"}
    assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == 10
    assert client.get("/transactions").get_json() == []


def test_failed_low_stock_notification_still_saves_transaction(
    client, monkeypatch
):
    product_response = client.post(
        "/products",
        json={
            "name": "Keyboard",
            "sku": "KB-1",
            "quantity_on_hand": 10,
            "reorder_level": 10,
        },
    )
    assert product_response.status_code == 201
    product_id = product_response.get_json()["id"]

    # Stub notification service to simulate failure
    monkeypatch.setattr(
        "app.routes.transactions.send_notification",
        lambda recipient, subject, message: False,
    )

    response = client.post(
        "/transactions",
        json={
            "product_id": product_id,
            "type": "OUT",
            "quantity": 7,
        },
    )

    assert response.status_code == 201
    assert response.get_json()["notification_sent"] is False

    # Stock still decreases
    stock = client.get(
        f"/products/{product_id}/stock-level"
    ).get_json()
    assert stock["quantity_on_hand"] == 3

    # Transaction is still saved
    transactions = client.get("/transactions").get_json()
    assert len(transactions) == 1
    assert transactions[0]["quantity"] == 7
    assert transactions[0]["type"] == "OUT" 


def test_low_stock_notification_not_triggered_at_threshold(client):
    product_response = client.post(
        "/products",
        json={
            "name": "Mouse",
            "sku": "MS-1",
            "quantity_on_hand": 12,
            "reorder_level": 10,
        },
    )
    assert product_response.status_code == 201
    product_id = product_response.get_json()["id"]

    # Remove 2 units, leaving exactly 10
    with patch(
        "app.routes.transactions.send_notification"
    ) as mock_send:
        response = client.post(
            "/transactions",
            json={
                "product_id": product_id,
                "type": "OUT",
                "quantity": 2,
            },
        )

    assert response.status_code == 201
    mock_send.assert_not_called()

    # Verify stock and transaction
    stock = client.get(
        f"/products/{product_id}/stock-level"
    ).get_json()
    assert stock["quantity_on_hand"] == 10

    transactions = client.get("/transactions").get_json()
    assert len(transactions) == 1
    assert transactions[0]["quantity"] == 2
    assert transactions[0]["type"] == "OUT"
