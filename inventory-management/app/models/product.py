# app/models/product.py
class Product:
    def __init__(
        self,
        id,
        name,
        sku,
        unit_price=0.0,
        quantity_on_hand=0,
        reorder_level=0,
        category="Uncategorized",
        unit_of_measure="each",
        locations=None,
    ):
        self.id = id
        self.name = name
        self.sku = sku
        self.unit_price = unit_price
        self.quantity_on_hand = quantity_on_hand
        self.reorder_level = reorder_level
        self.category = category
        self.unit_of_measure = unit_of_measure
        self.locations = locations if locations is not None else []

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sku": self.sku,
            "unit_price": self.unit_price,
            "quantity_on_hand": self.quantity_on_hand,
            "reorder_level": self.reorder_level,
            "category": self.category,
            "unit_of_measure": self.unit_of_measure,
            "locations": self.locations,
        }