# app/routes/products.py
from datetime import date
from flask import Blueprint, jsonify, request

from app import store
from app.models.product import Product

products_bp = Blueprint("products", __name__, url_prefix="/products")


@products_bp.route("", methods=["GET"])
def list_products():
    results = list(store.products.values())

    name_q = request.args.get("name", type=str)
    sku_q = request.args.get("sku", type=str)
    category_q = request.args.get("category", type=str)
    supplier_q = request.args.get("supplier", type=str)

    if name_q:
        results = [p for p in results if name_q.lower() in p.name.lower()]
    if sku_q:
        results = [p for p in results if sku_q.lower() in p.sku.lower()]
    if category_q:
        results = [p for p in results if category_q.lower() in p.category.lower()]
    if supplier_q:
        matching_supplier_ids = {
            s.id for s in store.suppliers.values()
            if supplier_q.lower() in s.name.lower()
        }
        linked_product_ids = {
            t.product_id for t in store.transactions.values()
            if t.supplier_id in matching_supplier_ids
        } | {
            po.product_id for po in store.purchase_orders.values()
            if po.supplier_id in matching_supplier_ids
        }
        results = [p for p in results if p.id in linked_product_ids]

    return jsonify([p.to_dict() for p in results])


@products_bp.route("/low-stock", methods=["GET"])
def low_stock():
    """Return products where quantity_on_hand is at or below their reorder_level."""
    flagged = [
        p for p in store.products.values()
        if p.quantity_on_hand <= p.reorder_level
    ]
    return jsonify([p.to_dict() for p in flagged])


@products_bp.route("", methods=["POST"])
def create_product():
    data = request.get_json()
    locations = data.get("locations", [])
    if not isinstance(locations, list) or len(locations) > 3:
        return jsonify({"error": "A product can have at most 3 location tags"}), 400

    product_id = store.next_id("product")
    product = Product(
        id=product_id,
        name=data["name"],
        sku=data["sku"],
        unit_price=data.get("unit_price", 0.0),
        quantity_on_hand=data.get("quantity_on_hand", 0),
        reorder_level=data.get("reorder_level", 0),
        category=data.get("category", "Uncategorized"),
        unit_of_measure=data.get("unit_of_measure", "each"),
        locations=locations,
    )
    store.products[product_id] = product
    return jsonify(product.to_dict()), 201


@products_bp.route("/<int:product_id>", methods=["GET"])
def get_product(product_id):
    product = store.products.get(product_id)
    if product is None:
        return jsonify({"error": "Product not found"}), 404
    return jsonify(product.to_dict())


@products_bp.route("/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    product = store.products.get(product_id)
    if product is None:
        return jsonify({"error": "Product not found"}), 404
    data = request.get_json()

    if "locations" in data:
        if not isinstance(data["locations"], list) or len(data["locations"]) > 3:
            return jsonify({"error": "A product can have at most 3 location tags"}), 400
        product.locations = data["locations"]

    product.name = data.get("name", product.name)
    product.sku = data.get("sku", product.sku)
    product.unit_price = data.get("unit_price", product.unit_price)
    product.quantity_on_hand = data.get("quantity_on_hand", product.quantity_on_hand)
    product.reorder_level = data.get("reorder_level", product.reorder_level)
    product.category = data.get("category", product.category)
    product.unit_of_measure = data.get("unit_of_measure", product.unit_of_measure)
    return jsonify(product.to_dict())


@products_bp.route("/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    product = store.products.pop(product_id, None)
    if product is None:
        return jsonify({"error": "Product not found"}), 404
    return "", 204


@products_bp.route("/<int:product_id>/stock-level", methods=["GET"])
def stock_level(product_id):
    product = store.products.get(product_id)
    if product is None:
        return jsonify({"error": "Product not found"}), 404
    return jsonify({"product_id": product.id, "quantity_on_hand": product.quantity_on_hand})


@products_bp.route("/<int:product_id>/reconcile", methods=["POST"])
def reconcile_product_stock(product_id):
    """Overwrite system stock with physical count and require a mandatory reason (R5, R20)."""
    product = store.products.get(product_id)
    if product is None:
        return jsonify({"error": "Product not found"}), 404

    data = request.get_json() or {}
    reason = data.get("reason", "").strip()
    if not reason:
        return jsonify({"error": "Reason for adjustment is required"}), 400
    if "physical_count" not in data or not isinstance(data["physical_count"], int) or data["physical_count"] < 0:
        return jsonify({"error": "Valid non-negative physical_count is required"}), 400

    previous_qty = product.quantity_on_hand
    new_qty = data["physical_count"]
    net_difference = new_qty - previous_qty
    product.quantity_on_hand = new_qty

    if not hasattr(store, "reconciliations"):
        store.reconciliations = []

    record = {
        "product_id": product.id,
        "sku": product.sku,
        "previous_quantity": previous_qty,
        "physical_count": new_qty,
        "net_difference": net_difference,
        "reason": reason,
        "date": date.today().isoformat(),
    }
    store.reconciliations.append(record)
    return jsonify(record), 200


@products_bp.route("/reconciliations", methods=["GET"])
def list_reconciliations():
    """Return all inventory reconciliation adjustments (R20)."""
    records = getattr(store, "reconciliations", [])
    return jsonify(records)