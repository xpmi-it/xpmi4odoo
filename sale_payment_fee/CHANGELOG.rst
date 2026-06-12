Changelog
=========

18.0.1.0.0 (2024-01-01)
~~~~~~~~~~~~~~~~~~~~~~~~

* [ADD] Initial release
* Add ``collection_fee_product_id`` field on ``account.payment.term``
* Auto-add/update/remove collection fee line on sale order when payment term changes
* Fee line quantity equals the number of installments in the payment term
* On invoicing, collection fee line quantity is set to 1
