from datetime import date


class PurchaseOrder:
    def __init__(
        self,
        id,
        supplier_id,
        product_id,
        quantity_ordered,
        status="pending",
        created_date=None,
        received_date=None,
        received_quantity=None,
        discrepancy_note=None,
    ):
        self.id = id
        self.supplier_id = supplier_id
        self.product_id = product_id
        self.quantity_ordered = quantity_ordered
        self.status = status
        self.created_date = created_date or date.today()
        self.received_date = received_date
        self.received_quantity = received_quantity
        self.discrepancy_note = discrepancy_note

    def to_dict(self):
        data = {
            "id": self.id,
            "supplier_id": self.supplier_id,
            "product_id": self.product_id,
            "quantity_ordered": self.quantity_ordered,
            "status": self.status,
            "created_date": self.created_date.isoformat(),
            "received_date": self.received_date.isoformat() if self.received_date else None,
        }
        if self.received_quantity is not None:
            data["received_quantity"] = self.received_quantity
        if self.discrepancy_note is not None:
            data["discrepancy_note"] = self.discrepancy_note
        return data
