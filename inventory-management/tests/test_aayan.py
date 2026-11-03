# tests/test_aayan.py
import pytest
from app import create_app, store


# Fallback fixture in case conftest.py does not automatically provide `client`
@pytest.fixture
def client():
    store.reset()
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# =====================================================================
# Commit 1: Product CRUD & Stock Level Queries
# =====================================================================

def test_create_and_get_product_persists_expected_fields(client):
    """Verify POST /products creates a product and GET /products/<id> retrieves it."""
    post_resp = client.post("/products", json={
        "name": "Industrial Wrench",
        "sku": "WR-100",
        "unit_price": 24.99,
        "quantity_on_hand": 40,
        "reorder_level": 10
    })
    assert post_resp.status_code == 201
    created = post_resp.get_json()
    assert created["id"] == 1
    assert created["name"] == "Industrial Wrench"
    assert created["sku"] == "WR-100"
    assert created["unit_price"] == 24.99
    assert created["quantity_on_hand"] == 40
    assert created["reorder_level"] == 10

    # Verify persistent state via GET /products/1
    get_resp = client.get(f"/products/{created['id']}")
    assert get_resp.status_code == 200
    fetched = get_resp.get_json()
    assert fetched == created


def test_list_products_returns_all_created_items(client):
    """Verify GET /products returns empty list initially and all items after creation."""
    assert client.get("/products").get_json() == []

    client.post("/products", json={"name": "Item 1", "sku": "SKU-1", "quantity_on_hand": 5})
    client.post("/products", json={"name": "Item 2", "sku": "SKU-2", "quantity_on_hand": 15})

    resp = client.get("/products")
    assert resp.status_code == 200
    products = resp.get_json()
    assert len(products) == 2
    assert {p["sku"] for p in products} == {"SKU-1", "SKU-2"}


def test_update_product_modifies_fields_and_persists(client):
    """Verify PUT /products/<id> updates product attributes and stock count (R2, R5, R9)."""
    client.post("/products", json={
        "name": "Old Name", "sku": "OLD-1", "unit_price": 5.0, "quantity_on_hand": 10, "reorder_level": 2
    })

    put_resp = client.put("/products/1", json={
        "name": "New Name",
        "quantity_on_hand": 25,
        "reorder_level": 8
    })
    assert put_resp.status_code == 200
    updated = put_resp.get_json()
    assert updated["name"] == "New Name"
    assert updated["sku"] == "OLD-1"  # unchanged field retained
    assert updated["quantity_on_hand"] == 25
    assert updated["reorder_level"] == 8

    # Verify via subsequent stock-level check
    stock_resp = client.get("/products/1/stock-level")
    assert stock_resp.status_code == 200
    assert stock_resp.get_json() == {"product_id": 1, "quantity_on_hand": 25}


def test_delete_product_removes_item_from_store(client):
    """Verify DELETE /products/<id> returns 204 and makes subsequent GET return 404."""
    client.post("/products", json={"name": "Temp Item", "sku": "TMP-1"})

    del_resp = client.delete("/products/1")
    assert del_resp.status_code == 204

    get_resp = client.get("/products/1")
    assert get_resp.status_code == 404
    assert "error" in get_resp.get_json()


def test_product_not_found_error_cases(client):
    """Verify 404 handling for nonexistent product IDs across GET, PUT, DELETE, and stock-level."""
    assert client.get("/products/999").status_code == 404
    assert client.put("/products/999", json={"name": "Ghost"}).status_code == 404
    assert client.delete("/products/999").status_code == 404
    assert client.get("/products/999/stock-level").status_code == 404

# =====================================================================
# Commit 2: Low-Stock Thresholds & Boundary Conditions
# =====================================================================

def test_low_stock_identifies_items_at_or_below_reorder_level(client):
    """Verify GET /products/low-stock checks boundary conditions (below, equal, above threshold)."""
    # Below threshold (3 < 10) -> should be flagged
    client.post("/products", json={"name": "Below", "sku": "B-1", "quantity_on_hand": 3, "reorder_level": 10})
    # Exactly at threshold (10 == 10) -> should be flagged per R10
    client.post("/products", json={"name": "Equal", "sku": "E-1", "quantity_on_hand": 10, "reorder_level": 10})
    # Above threshold (11 > 10) -> should NOT be flagged
    client.post("/products", json={"name": "Above", "sku": "A-1", "quantity_on_hand": 11, "reorder_level": 10})

    resp = client.get("/products/low-stock")
    assert resp.status_code == 200
    flagged_skus = [p["sku"] for p in resp.get_json()]
    assert "B-1" in flagged_skus
    assert "E-1" in flagged_skus
    assert "A-1" not in flagged_skus


# =====================================================================
# Commit 3: Inventory Transactions, Chained Workflows & Defects
# =====================================================================

def test_inbound_and_outbound_transactions_update_stock_level(client):
    """Chained workflow: create product -> log IN -> log OUT -> verify final stock level."""
    client.post("/products", json={"name": "Cable", "sku": "CBL-1", "quantity_on_hand": 20, "reorder_level": 15})

    # Log IN transaction (+10) -> stock becomes 30
    in_resp = client.post("/transactions", json={"product_id": 1, "type": "IN", "quantity": 10})
    assert in_resp.status_code == 201
    assert in_resp.get_json()["type"] == "IN"
    assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == 30

    # Log OUT transaction (-18) -> stock becomes 12 (which also triggers low-stock <= 15)
    out_resp = client.post("/transactions", json={"product_id": 1, "type": "OUT", "quantity": 18})
    assert out_resp.status_code == 201
    assert client.get("/products/1/stock-level").get_json()["quantity_on_hand"] == 12

    # Confirm product now appears in low-stock endpoint
    low_stock_ids = [p["id"] for p in client.get("/products/low-stock").get_json()]
    assert 1 in low_stock_ids


def test_transaction_validation_errors(client):
    """Verify POST /transactions rejects nonexistent products and invalid transaction types."""
    # Nonexistent product
    resp_missing = client.post("/transactions", json={"product_id": 999, "type": "IN", "quantity": 5})
    assert resp_missing.status_code == 404

    # Invalid transaction type
    client.post("/products", json={"name": "Valve", "sku": "V-1", "quantity_on_hand": 10})
    resp_bad_type = client.post("/transactions", json={"product_id": 1, "type": "ADJUST", "quantity": 5})
    assert resp_bad_type.status_code == 400


def test_filter_transactions_by_product_id_returns_matching_records(client):
    """
    DEFECT TEST (Expected to FAIL on baseline app):
    Verify GET /transactions?product_id=<id> filters by t.product_id (supports R21/R16).
    Currently fails because app/routes/transactions.py checks `t.supplier_id == product_id`.
    """
    client.post("/products", json={"name": "Prod 1", "sku": "P-1", "quantity_on_hand": 10})
    client.post("/products", json={"name": "Prod 2", "sku": "P-2", "quantity_on_hand": 10})

    # Create transaction for product_id=1 with no supplier_id (supplier_id=None)
    client.post("/transactions", json={"product_id": 1, "type": "IN", "quantity": 5})
    # Create transaction for product_id=2
    client.post("/transactions", json={"product_id": 2, "type": "OUT", "quantity": 3})

    resp = client.get("/transactions?product_id=1")
    assert resp.status_code == 200
    results = resp.get_json()
    assert len(results) == 1
    assert results[0]["product_id"] == 1