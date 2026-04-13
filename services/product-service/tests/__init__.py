"""
product-service test package.

pytest discovers this package automatically.  The shared-memory SQLite URI
(``file:productmem?mode=memory&cache=shared``) and the module-level ``_keeper``
connection are defined in test_product.py so the in-memory database stays alive
for the full test session.
"""
