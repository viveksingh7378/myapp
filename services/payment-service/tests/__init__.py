"""
payment-service test package.

pytest discovers this package automatically.  The shared-memory SQLite URI
(``file:paymentmem?mode=memory&cache=shared``) and the module-level ``_keeper``
connection are defined in test_payment.py so the in-memory database stays alive
for the full test session.
"""
