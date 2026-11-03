import pytest
from app import create_app, store


@pytest.fixture
def client():
    store.reset()
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# =====================================================================
# COMMIT 1: Supplier CRUD & Boundary/Error Cases
# =====================================================================

def test_create_and_get_supplier_persists_data(client):
    """Verify POST /suppliers creates a supplier and GET /suppliers/<id> returns it (R22)."""
    post_resp = client.post("/suppliers", json={
        "name": "Kingston Industrial Supply",
        "contact_email": "orders@kingstonsupply.ca"
    })
    assert post_resp.status_code == 201
    supplier = post_resp.get_json()
    assert supplier["id"] == 1
    assert supplier["name"] == "Kingston Industrial Supply"
    assert supplier["contact_email"] == "orders@kingstonsupply.ca"

    get_resp = client.get("/suppliers/1")
    assert get_resp.status_code == 200
    assert get_resp.get_json() == supplier


def test_list_update_and_delete_supplier(client):
    """Verify full lifecycle of listing, updating, and deleting a supplier."""
    client.post("/suppliers", json={"name": "Alpha Corp", "contact_email": "a@alpha.com"})

    # List suppliers
    list_resp = client.get("/suppliers")
    assert list_resp.status_code == 200
    assert len(list_resp.get_json()) == 1

    # Update supplier
    put_resp = client.put("/suppliers/1", json={"contact_email": "new@alpha.com"})
    assert put_resp.status_code == 200
    assert put_resp.get_json()["name"] == "Alpha Corp"
    assert put_resp.get_json()["contact_email"] == "new@alpha.com"

    # Delete supplier
    del_resp = client.delete("/suppliers/1")
    assert del_resp.status_code == 204
    assert client.get("/suppliers/1").status_code == 404


def test_supplier_not_found_error_cases(client):
    """Verify 404 responses for nonexistent supplier IDs."""
    assert client.get("/suppliers/999").status_code == 404
    assert client.put("/suppliers/999", json={"name": "None"}).status_code == 404
    assert client.delete("/suppliers/999").status_code == 404
    assert client.get("/suppliers/999/products").status_code == 404


# =====================================================================
# COMMIT 2: Supplier Products Relational Query
# =====================================================================

def test_supplier_products_returns_only_products_with_in_transactions(client):
    """Verify GET /suppliers/<id>/products returns unique products received via IN transactions."""
    client.post("/suppliers", json={"name": "Sup 1", "contact_email": "s1@test.com"})
    client.post("/suppliers", json={"name": "Sup 2", "contact_email": "s2@test.com"})
    client.post("/products", json={"name": "Bolt", "sku": "B-1", "quantity_on_hand": 10})
    client.post("/products", json={"name": "Nut", "sku": "N-1", "quantity_on_hand": 10})

    # Log IN transaction for Bolt from Sup 1
    client.post("/transactions", json={"product_id": 1, "supplier_id": 1, "type": "IN", "quantity": 20})
    # Log OUT transaction for Nut with Sup 1 (should not count as received from supplier)
    client.post("/transactions", json={"product_id": 2, "supplier_id": 1, "type": "OUT", "quantity": 5})

    resp = client.get("/suppliers/1/products")
    assert resp.status_code == 200
    products = resp.get_json()
    assert len(products) == 1
    assert products[0]["sku"] == "B-1"

    # Sup 2 has no IN transactions
    assert client.get("/suppliers/2/products").get_json() == []


# =====================================================================
# COMMIT 3: Purchase Orders & Receiving Workflow (Includes Defect Test)
# =====================================================================

def test_create_and_get_purchase_order(client):
    """Verify POST /purchase-orders creates a pending PO and validates supplier/product IDs."""
    client.post("/suppliers", json={"name": "Sup 1", "contact_email": "s1@test.com"})
    client.post("/products", json={"name": "Motor", "sku": "M-1", "quantity_on_hand": 5})

    po_resp = client.post("/purchase-orders", json={
        "supplier_id": 1,
        "product_id": 1,
        "quantity_ordered": 15
    })
    assert po_resp.status_code == 201
    po = po_resp.get_json()
    assert po["id"] == 1
    assert po["status"] == "pending"
    assert po["quantity_ordered"] == 15
    assert po["received_date"] is None

    # Verify GET /purchase-orders and GET /purchase-orders/1
    assert len(client.get("/purchase-orders").get_json()) == 1
    assert client.get("/purchase-orders/1").get_json() == po


def test_purchase_order_creation_and_lookup_errors(client):
    """Verify 404 when creating PO with invalid supplier/product or fetching invalid PO."""
    client.post("/suppliers", json={"name": "Sup 1", "contact_email": "s1@test.com"})
    client.post("/products", json={"name": "Motor", "sku": "M-1", "quantity_on_hand": 5})

    # Invalid supplier_id
    assert client.post("/purchase-orders", json={
        "supplier_id": 999, "product_id": 1, "quantity_ordered": 10
    }).status_code == 404

    # Invalid product_id
    assert client.post("/purchase-orders", json={
        "supplier_id": 1, "product_id": 999, "quantity_ordered": 10
    }).status_code == 404

    # Nonexistent PO
    assert client.get("/purchase-orders/999").status_code == 404
    assert client.put("/purchase-orders/999/receive").status_code == 404


def test_receive_purchase_order_prevents_double_receiving(client):
    """Verify receiving a PO transitions status to received, creates an IN transaction, and blocks repeat receive."""
    client.post("/suppliers", json={"name": "Sup 1", "contact_email": "s1@test.com"})
    client.post("/products", json={"name": "Pump", "sku": "PMP-1", "quantity_on_hand": 10})
    client.post("/purchase-orders", json={"supplier_id": 1, "product_id": 1, "quantity_ordered": 25})

    # First receive succeeds
    rec_resp = client.put("/purchase-orders/1/receive")
    assert rec_resp.status_code == 200
    rec_data = rec_resp.get_json()
    assert rec_data["status"] == "received"
    assert rec_data["received_date"] is not None

    # Audit trail transaction was created
    txs = client.get("/transactions?supplier_id=1").get_json()
    assert len(txs) == 1
    assert txs[0]["type"] == "IN"
    assert txs[0]["quantity"] == 25

    # Second receive attempt fails with 400 Bad Request
    dup_resp = client.put("/purchase-orders/1/receive")
    assert dup_resp.status_code == 400


def test_receive_purchase_order_increments_product_stock_level(client):
    """
    DEFECT TEST (Expected to FAIL on baseline app):
    Verify receiving a purchase order increments the product's quantity_on_hand (R3).
    Currently fails because app/routes/purchase_orders.py omits updating product.quantity_on_hand.
    """
    client.post("/suppliers", json={"name": "Sup 1", "contact_email": "s1@test.com"})
    client.post("/products", json={"name": "Gearbox", "sku": "GB-1", "quantity_on_hand": 10})
    client.post("/purchase-orders", json={"supplier_id": 1, "product_id": 1, "quantity_ordered": 15})

    client.put("/purchase-orders/1/receive")

    # Expected: 10 initial + 15 received = 25. Observed in baseline: remains 10.
    stock_resp = client.get("/products/1/stock-level")
    assert stock_resp.get_json()["quantity_on_hand"] == 25 

# =====================================================================
# COMMIT 4: Functional Enhancement Tests (Overdraft Guard & PO Discrepancy)
# =====================================================================

def test_outbound_transaction_exceeding_stock_requires_confirmation(client):
    """Verify OUT transaction > quantity_on_hand blocks with 400 unless confirm=True (R14)."""
    client.post("/products", json={"name": "Sensor", "sku": "SN-1", "quantity_on_hand": 5})

    # Unconfirmed overdraft is blocked and stock remains 5
    unconfirmed = client.post("/transactions", json={"product_id": 1, "type": "OUT", "quantity": 8})
    assert unconfirmed.status_code == 400
    assert unconfirmed.get_json()["requires_confirmation"] is True
    assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == 5

    # Confirmed overdraft proceeds
    confirmed = client.post("/transactions", json={
        "product_id": 1, "type": "OUT", "quantity": 8, "confirm": True
    })
    assert confirmed.status_code == 201
    assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == -3


def test_receive_po_discrepancy_requires_confirmation_and_records_notes(client):
    """Verify receiving a PO with a different quantity requires confirmation and logs discrepancy (R3, R15)."""
    client.post("/suppliers", json={"name": "Sup 1", "contact_email": "s1@test.com"})
    client.post("/products", json={"name": "Bearing", "sku": "BR-1", "quantity_on_hand": 10})
    client.post("/purchase-orders", json={"supplier_id": 1, "product_id": 1, "quantity_ordered": 20})

    # Unconfirmed quantity discrepancy (12 instead of 20) returns 400 warning
    warn_resp = client.put("/purchase-orders/1/receive", json={"received_quantity": 12})
    assert warn_resp.status_code == 400
    assert warn_resp.get_json()["requires_confirmation"] is True
    assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == 10

    # Confirmed discrepancy updates stock by actual received_quantity (+12 -> 22) and records note
    ok_resp = client.put("/purchase-orders/1/receive", json={
        "received_quantity": 12,
        "confirm": True,
        "status": "partially_received",
        "discrepancy_note": "8 units backordered by supplier"
    })
    assert ok_resp.status_code == 200
    po_data = ok_resp.get_json()
    assert po_data["status"] == "partially_received"
    assert po_data["received_quantity"] == 12
    assert po_data["discrepancy_note"] == "8 units backordered by supplier"
    assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == 22