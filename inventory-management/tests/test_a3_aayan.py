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

def test_home_links_to_inventory_pages(client):
    response = client.get("/")

    assert response.status_code == 200
    for path in (b"/ui/products", b"/ui/suppliers", b"/ui/transactions"):
        assert b'href="' + path + b'"' in response.data


def test_products_form_creates_and_deletes_product(client):
    response = client.post(
        "/ui/products",
        data={
            "name": "UI Mouse",
            "sku": "UI-MOUSE",
            "unit_price": "12.50",
            "quantity_on_hand": "4",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"UI-MOUSE" in response.data
    product, = client.get("/products").get_json()
    assert product["name"] == "UI Mouse"
    assert product["unit_price"] == 12.50
    assert product["quantity_on_hand"] == 4

    deleted = client.post(
        f"/ui/products/{product['id']}/delete", follow_redirects=True
    )
    assert deleted.status_code == 200
    assert b"UI-MOUSE" not in deleted.data
    assert client.get("/products").get_json() == []


def test_suppliers_form_creates_and_deletes_supplier(client):
    response = client.post(
        "/ui/suppliers",
        data={"name": "UI Supplier", "contact_email": "ui@example.com"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"ui@example.com" in response.data
    supplier, = client.get("/suppliers").get_json()
    assert supplier["name"] == "UI Supplier"
    assert supplier["contact_email"] == "ui@example.com"

    deleted = client.post(
        f"/ui/suppliers/{supplier['id']}/delete", follow_redirects=True
    )
    assert deleted.status_code == 200
    assert b"ui@example.com" not in deleted.data
    assert client.get("/suppliers").get_json() == []


@pytest.mark.parametrize(
    "movement, quantity, with_supplier, expected_stock",
    [("IN", 4, True, 14), ("OUT", 3, False, 7)],
)
def test_transactions_form_records_stock_movement(
    client, movement, quantity, with_supplier, expected_stock
):
    product_id = _create_mouse(client)
    fields = {
        "product_id": str(product_id),
        "type": movement,
        "quantity": str(quantity),
    }
    supplier_id = None
    if with_supplier:
        supplier = client.post(
            "/suppliers",
            json={"name": "Stock Supplier", "contact_email": "stock@example.com"},
        )
        assert supplier.status_code == 201
        supplier_id = supplier.get_json()["id"]
        fields["supplier_id"] = str(supplier_id)

    response = client.post("/ui/transactions", data=fields, follow_redirects=True)

    assert response.status_code == 200
    assert f"<td>{movement}</td>".encode() in response.data
    saved, = client.get("/transactions").get_json()
    assert saved["product_id"] == product_id
    assert saved["type"] == movement
    assert saved["quantity"] == quantity
    assert saved["supplier_id"] == supplier_id
    stock = client.get(f"/products/{product_id}/stock-level").get_json()
    assert stock["quantity_on_hand"] == expected_stock


def test_transactions_form_skips_unknown_product(client):
    response = client.post(
        "/ui/transactions",
        data={"product_id": "999", "type": "OUT", "quantity": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Record a Stock Movement" in response.data
    assert client.get("/transactions").get_json() == []