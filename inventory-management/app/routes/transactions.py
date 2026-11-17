from flask import Blueprint, jsonify, request

from app import store
from app.models.transaction import Transaction
from notification_service import LOW_STOCK_RECIPIENT, LOW_STOCK_SUBJECT, send_notification

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@transactions_bp.route("", methods=["GET"])
def list_transactions():
    results = list(store.transactions.values())
    product_id = request.args.get("product_id", type=int)
    supplier_id = request.args.get("supplier_id", type=int)
    if product_id is not None:
        results = [t for t in results if t.product_id == product_id]
    if supplier_id is not None:
        results = [t for t in results if t.supplier_id == supplier_id]
    return jsonify([t.to_dict() for t in results])


@transactions_bp.route("", methods=["POST"])
def create_transaction():
    data = request.get_json()
    product = store.products.get(data["product_id"])
    if product is None:
        return jsonify({"error": "Product not found"}), 404

    quantity = data["quantity"]
    if not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "quantity must be a positive integer"}), 400

    tx_type = data["type"]
    previous_quantity = product.quantity_on_hand

    if tx_type == "IN":
        product.quantity_on_hand += quantity
    elif tx_type == "OUT":
        if quantity > product.quantity_on_hand and not data.get("confirm", False):
            return jsonify({
                "error": "Outgoing quantity exceeds available stock on hand",
                "requires_confirmation": True,
                "quantity_on_hand": product.quantity_on_hand,
                "requested_quantity": quantity,
            }), 400
        product.quantity_on_hand -= quantity
    else:
        return jsonify({"error": "type must be IN or OUT"}), 400

    transaction_id = store.next_id("transaction")
    transaction = Transaction(
        id=transaction_id,
        product_id=data["product_id"],
        supplier_id=data.get("supplier_id"),
        type=tx_type,
        quantity=quantity,
    )
    store.transactions[transaction_id] = transaction
    result = transaction.to_dict()
    reorder_level = product.reorder_level

    if (
        tx_type == "OUT"
        and isinstance(reorder_level, (int, float))
        and previous_quantity >= reorder_level > product.quantity_on_hand
    ):
        message = (
            f"{product.name} inventory has dropped to "
            f"{product.quantity_on_hand} units. "
            f"The minimum threshold is {reorder_level} units."
        )
        result["notification_sent"] = send_notification(
            LOW_STOCK_RECIPIENT, LOW_STOCK_SUBJECT, message
        )

    return jsonify(result), 201