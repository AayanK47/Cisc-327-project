from datetime import date

from flask import Blueprint, jsonify, request

from app import store
from app.models.purchase_order import PurchaseOrder
from app.models.transaction import Transaction

purchase_orders_bp = Blueprint("purchase_orders", __name__, url_prefix="/purchase-orders")


@purchase_orders_bp.route("", methods=["GET"])
def list_purchase_orders():
    return jsonify([po.to_dict() for po in store.purchase_orders.values()])


@purchase_orders_bp.route("", methods=["POST"])
def create_purchase_order():
    data = request.get_json()
    supplier = store.suppliers.get(data["supplier_id"])
    if supplier is None:
        return jsonify({"error": "Supplier not found"}), 404
    product = store.products.get(data["product_id"])
    if product is None:
        return jsonify({"error": "Product not found"}), 404

    po_id = store.next_id("purchase_order")
    po = PurchaseOrder(
        id=po_id,
        supplier_id=data["supplier_id"],
        product_id=data["product_id"],
        quantity_ordered=data["quantity_ordered"],
        status="pending",
    )
    store.purchase_orders[po_id] = po
    return jsonify(po.to_dict()), 201


@purchase_orders_bp.route("/<int:po_id>", methods=["GET"])
def get_purchase_order(po_id):
    po = store.purchase_orders.get(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found"}), 404
    return jsonify(po.to_dict())


@purchase_orders_bp.route("/<int:po_id>/receive", methods=["PUT"])
def receive_purchase_order(po_id):
    po = store.purchase_orders.get(po_id)
    if po is None:
        return jsonify({"error": "Purchase order not found"}), 404
    if po.status != "pending":
        return jsonify({"error": "Purchase order already processed"}), 400

    data = request.get_json(silent=True) or {}
    actual_qty = data.get("received_quantity", po.quantity_ordered)
    if not isinstance(actual_qty, int) or actual_qty < 0:
        return jsonify({"error": "received_quantity must be a non-negative integer"}), 400

    if actual_qty != po.quantity_ordered and not data.get("confirm", False):
        return jsonify({
            "error": "Incoming shipment quantity differs from expected PO quantity",
            "requires_confirmation": True,
            "expected_quantity": po.quantity_ordered,
            "received_quantity": actual_qty,
        }), 400

    po.status = data.get("status", "received" if actual_qty == po.quantity_ordered else "partially_received")
    po.received_date = date.today()
    po.received_quantity = actual_qty
    if "discrepancy_note" in data:
        po.discrepancy_note = data["discrepancy_note"]

    # Increment the product's quantity_on_hand by actual_qty
    store.products[po.product_id].quantity_on_hand += actual_qty

    transaction_id = store.next_id("transaction")
    transaction = Transaction(
        id=transaction_id,
        product_id=po.product_id,
        supplier_id=po.supplier_id,
        type="IN",
        quantity=actual_qty,
    )
    store.transactions[transaction_id] = transaction

    return jsonify(po.to_dict())