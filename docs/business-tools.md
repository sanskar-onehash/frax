# Business tools

Business tools are enabled by default and appear only when the compatible business
application is installed. Administrators can disable the complete category in MCP
Settings. Every operation also uses the acting user's normal document permissions.

The first curated set provides:

- transaction-aware item defaults, price-list, tax, warehouse, and stock context;
- stock-ledger balance and optional valuation rate;
- customer or supplier account, address, currency, price-list, and payment-term context;
- fiscal-year and transaction-date exchange-rate context;
- native draft conversion for common selling, buying, delivery, and receipt flows;
- native draft Payment Entry creation from supported invoices and orders.

The conversion tool supports these native mappings:

- Quotation to Sales Order
- Sales Order to Delivery Note
- Sales Order to Sales Invoice
- Material Request to Purchase Order
- Purchase Order to Purchase Receipt
- Purchase Order to Purchase Invoice

These tools do not reproduce generic document CRUD. They call the installed business
application's own helpers and mapping methods so its validations, hooks, customizations,
and overrides remain active. Write tools insert unsubmitted drafts only; they never
submit, cancel, or bypass permissions. The response includes the created document and
its Desk URL for verification.

Generic document tools remain available for workflows that do not have a curated
business helper. Reporting and outstanding-balance workflows are documented separately
because they use the reporting tool category.
