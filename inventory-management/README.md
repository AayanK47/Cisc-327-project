# Inventory Management System (IMS)

A small Flask REST API for tracking products, suppliers, and stock transactions.
Data is stored **in memory** (plain Python objects, no database) and is reset
every time the app restarts — this project is meant to run before you've
covered databases.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

The API runs at `http://127.0.0.1:5000`.

## Web UI

Open `http://127.0.0.1:5000/` in a browser for a basic HTML front end (plain
forms and tables, no JavaScript) to add/delete products and suppliers, and
record stock transactions:

| Page | Path |
|---|---|
| Home | `/` |
| Products | `/ui/products` |
| Suppliers | `/ui/suppliers` |
| Transactions | `/ui/transactions` |

This UI is separate from the JSON API below — it's there so you can see the
app working without a REST client, and calls the same in-memory store.

## Entities

- **Product**: `id, name, sku, unit_price, quantity_on_hand, reorder_level, category, unit_of_measure, locations`
- **Supplier**: `id, name, contact_email`
- **Transaction**: `id, product_id, supplier_id, type (IN/OUT), quantity, transaction_date`
- **PurchaseOrder**: `id, supplier_id, product_id, quantity_ordered, status, created_date, received_date, received_quantity, discrepancy_note`

## JSON API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/products` | List/search products (optional `?name=`, `?sku=`, `?category=`, `?supplier=`) |
| POST | `/products` | Create a product (supports `category`, `unit_of_measure`, up to 3 `locations`) |
| GET | `/products/low-stock` | List products at or below their `reorder_level` |
| GET | `/products/<id>` | Get one product |
| PUT | `/products/<id>` | Update a product |
| DELETE | `/products/<id>` | Delete a product |
| GET | `/products/<id>/stock-level` | Current quantity on hand |
| POST | `/products/<id>/reconcile` | Reconcile stock with `physical_count` and mandatory `reason` |
| GET | `/products/reconciliations` | List all inventory reconciliation adjustment records |
| GET | `/suppliers` | List all suppliers |
| POST | `/suppliers` | Create a supplier |
| GET | `/suppliers/<id>` | Get one supplier |
| PUT | `/suppliers/<id>` | Update a supplier |
| DELETE | `/suppliers/<id>` | Delete a supplier |
| GET | `/suppliers/<id>/products` | List products received from a supplier |
| POST | `/transactions` | Record a stock movement (`product_id`, `type`: IN/OUT, `quantity`, optional `supplier_id`, `confirm`) |
| GET | `/transactions?product_id=&supplier_id=` | Look up transactions by product or supplier |
| GET | `/purchase-orders` | List all purchase orders |
| POST | `/purchase-orders` | Create a purchase order |
| GET | `/purchase-orders/<id>` | Get one purchase order |
| PUT | `/purchase-orders/<id>/receive` | Receive a purchase order (optional `received_quantity`, `discrepancy_note`, `status`, `confirm`) |

## Tests

```bash
pytest
```
