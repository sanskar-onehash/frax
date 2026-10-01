from __future__ import annotations

from typing import Any, Literal

import frappe
from frappe import _

from frax.tools.registry import annotations_for, frax_tool


MAPPERS = {
    "quotation_to_sales_order": (
        "Quotation",
        "Sales Order",
        "erpnext.selling.doctype.quotation.quotation.make_sales_order",
    ),
    "sales_order_to_delivery_note": (
        "Sales Order",
        "Delivery Note",
        "erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
    ),
    "sales_order_to_sales_invoice": (
        "Sales Order",
        "Sales Invoice",
        "erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice",
    ),
    "material_request_to_purchase_order": (
        "Material Request",
        "Purchase Order",
        "erpnext.stock.doctype.material_request.material_request.make_purchase_order",
    ),
    "purchase_order_to_purchase_receipt": (
        "Purchase Order",
        "Purchase Receipt",
        "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
    ),
    "purchase_order_to_purchase_invoice": (
        "Purchase Order",
        "Purchase Invoice",
        "erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice",
    ),
}
ITEM_TRANSACTION_TYPES = {
    "Quotation",
    "Sales Order",
    "Delivery Note",
    "Sales Invoice",
    "POS Invoice",
    "Material Request",
    "Supplier Quotation",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
}
ITEM_DETAILS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "args": {
            "type": "object",
            "description": "Transaction context used by the platform's native item resolver.",
            "properties": {
                "item_code": {"type": "string"},
                "company": {"type": "string"},
                "doctype": {
                    "type": "string",
                    "enum": sorted(ITEM_TRANSACTION_TYPES),
                },
                "customer": {"type": ["string", "null"]},
                "supplier": {"type": ["string", "null"]},
                "warehouse": {"type": ["string", "null"]},
                "qty": {"type": ["number", "null"]},
                "uom": {"type": ["string", "null"]},
                "transaction_date": {"type": ["string", "null"]},
                "selling_price_list": {"type": ["string", "null"]},
                "buying_price_list": {"type": ["string", "null"]},
                "price_list_currency": {"type": ["string", "null"]},
                "conversion_rate": {"type": ["number", "null"]},
                "plc_conversion_rate": {"type": ["number", "null"]},
            },
            "required": ["item_code", "company", "doctype"],
            "additionalProperties": True,
        }
    },
    "required": ["args"],
    "additionalProperties": False,
}


def register():
    return None


def _as_dict(value):
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, dict):
        return value
    if isinstance(value, tuple):
        return list(value)
    return value


@frax_tool(
    name="frax_get_business_capabilities",
    risk="read",
    category="business",
    annotations=annotations_for(
        "read", idempotent=True, title="Get Business Capabilities"
    ),
)
def get_business_capabilities():
    """Describe installed business helpers and supported native draft mappings."""
    return {
        "installed": True,
        "mappings": [
            {"operation": key, "source": value[0], "target": value[1]}
            for key, value in MAPPERS.items()
        ],
        "helpers": [
            "item_details",
            "stock_balance",
            "party_details",
            "exchange_rate",
            "fiscal_year",
            "draft_payment_entry",
        ],
        "safety": "All helpers use the acting user's permissions. Mapping and payment tools create drafts only.",
    }


@frax_tool(
    name="frax_get_item_details",
    risk="read",
    category="business_stock",
    input_schema=ITEM_DETAILS_INPUT_SCHEMA,
    annotations=annotations_for("read", idempotent=True, title="Get Item Details"),
)
def get_item_details(args: dict[str, Any]):
    """Resolve native transaction-aware item defaults, pricing, tax, and stock values."""
    from erpnext.stock.get_item_details import (
        get_item_details as native_get_item_details,
    )

    if not isinstance(args, dict):
        frappe.throw(_("args must be an object."))
    item_code = args.get("item_code")
    company = args.get("company")
    transaction_doctype = args.get("doctype")
    if (
        not item_code
        or not company
        or transaction_doctype not in ITEM_TRANSACTION_TYPES
    ):
        frappe.throw(_("item_code, company, and a supported doctype are required."))
    frappe.get_doc("Item", item_code).check_permission("read")
    frappe.get_doc("Company", company).check_permission("read")
    for doctype, name in (
        ("Warehouse", args.get("warehouse")),
        ("Customer", args.get("customer")),
        ("Supplier", args.get("supplier")),
    ):
        if name:
            frappe.get_doc(doctype, name).check_permission("read")
    return _as_dict(native_get_item_details(frappe._dict(args)))


@frax_tool(
    name="frax_get_stock_balance",
    risk="sensitive_read",
    category="business_stock",
    annotations=annotations_for(
        "sensitive_read", idempotent=True, title="Get Stock Balance"
    ),
)
def get_stock_balance(
    item_code: str,
    warehouse: str,
    posting_date: str | None = None,
    posting_time: str | None = None,
    with_valuation_rate: bool = False,
):
    """Return the native stock-ledger balance for one readable Item and Warehouse."""
    from erpnext.stock.utils import get_stock_balance as native_get_stock_balance

    frappe.get_doc("Item", item_code).check_permission("read")
    frappe.get_doc("Warehouse", warehouse).check_permission("read")
    value = native_get_stock_balance(
        item_code,
        warehouse,
        posting_date=posting_date,
        posting_time=posting_time,
        with_valuation_rate=with_valuation_rate,
    )
    return {"item_code": item_code, "warehouse": warehouse, "balance": _as_dict(value)}


@frax_tool(
    name="frax_get_party_details",
    risk="sensitive_read",
    category="business_accounts",
    annotations=annotations_for(
        "sensitive_read", idempotent=True, title="Get Party Details"
    ),
)
def get_party_details(
    party: str,
    party_type: Literal["Customer", "Supplier"] = "Customer",
    company: str | None = None,
    posting_date: str | None = None,
    currency: str | None = None,
    price_list: str | None = None,
    transaction_doctype: str | None = None,
):
    """Resolve native party accounts, addresses, currency, price list, and payment terms."""
    from erpnext.accounts.party import get_party_details as native_get_party_details

    frappe.get_doc(party_type, party).check_permission("read")
    value = native_get_party_details(
        party=party,
        party_type=party_type,
        company=company,
        posting_date=posting_date,
        currency=currency,
        price_list=price_list,
        doctype=transaction_doctype,
        ignore_permissions=False,
    )
    return _as_dict(value)


@frax_tool(
    name="frax_get_accounting_context",
    risk="read",
    category="business_accounts",
    annotations=annotations_for(
        "read", idempotent=True, title="Get Accounting Context"
    ),
)
def get_accounting_context(
    company: str,
    date: str,
    from_currency: str | None = None,
    to_currency: str | None = None,
):
    """Resolve the fiscal year and, when requested, the transaction-date exchange rate."""
    from erpnext.accounts.utils import get_fiscal_year
    from erpnext.setup.utils import get_exchange_rate

    frappe.get_doc("Company", company).check_permission("read")
    if bool(from_currency) != bool(to_currency):
        frappe.throw(
            _("Provide both from_currency and to_currency for exchange rates.")
        )
    fiscal_year = get_fiscal_year(date, company=company, as_dict=True)
    result = {"company": company, "date": date, "fiscal_year": _as_dict(fiscal_year)}
    if from_currency and to_currency:
        result["exchange_rate"] = get_exchange_rate(from_currency, to_currency, date)
        result["from_currency"] = from_currency
        result["to_currency"] = to_currency
    return result


@frax_tool(
    name="frax_create_mapped_draft",
    risk="write",
    requires_confirmation=True,
    category="business",
    annotations=annotations_for("write", open_world=True, title="Create Mapped Draft"),
)
def map_document(
    operation: Literal[
        "quotation_to_sales_order",
        "sales_order_to_delivery_note",
        "sales_order_to_sales_invoice",
        "material_request_to_purchase_order",
        "purchase_order_to_purchase_receipt",
        "purchase_order_to_purchase_invoice",
    ],
    source_name: str,
    selected_children: dict[str, list[str]] | None = None,
):
    """Use the native business mapper and insert the resulting target as a draft.

    ``selected_children`` maps each source child-table fieldname to selected row
    names, matching the native mapped-document UI contract.
    """
    if operation not in MAPPERS:
        frappe.throw(_("Unsupported business mapping operation."))
    if selected_children and any(
        not isinstance(fieldname, str)
        or not isinstance(names, list)
        or any(not isinstance(name, str) for name in names)
        for fieldname, names in selected_children.items()
    ):
        frappe.throw(_("selected_children must map table fields to row-name lists."))
    source_doctype, target_doctype, method = MAPPERS[operation]
    frappe.get_doc(source_doctype, source_name).check_permission("read")
    if not frappe.has_permission(target_doctype, "create"):
        frappe.throw(
            _("Not permitted to create {0}.").format(target_doctype),
            frappe.PermissionError,
        )

    mapper = _resolved_mapper(method)
    if selected_children:
        if operation == "material_request_to_purchase_order":
            rows = [row for names in selected_children.values() for row in names]
            mapped = mapper(source_name, args={"filtered_children": rows})
        else:
            previous = getattr(frappe.flags, "selected_children", None)
            frappe.flags.selected_children = selected_children
            try:
                mapped = mapper(source_name)
            finally:
                frappe.flags.selected_children = previous
    else:
        mapped = mapper(source_name)
    if (
        mapped.doctype != target_doctype
        or not mapped.is_new()
        or int(mapped.docstatus or 0) != 0
    ):
        frappe.throw(_("The native mapper did not return the expected new draft."))
    mapped.flags.ignore_permissions = False
    mapped.insert()
    return {
        "data": mapped.as_dict(),
        "meta": {"operation": operation, "docstatus": mapped.docstatus},
        "warnings": [],
        "links": {
            "document": frappe.utils.get_url_to_form(target_doctype, mapped.name)
        },
    }


def _resolved_mapper(method: str):
    for override in reversed(
        frappe.get_hooks("override_whitelisted_methods", {}).get(method, [])
    ):
        method = override
        break
    mapper = frappe.get_attr(method)
    if mapper not in frappe.whitelisted:
        frappe.throw(
            _("Configured business mapping method is not available."),
            frappe.PermissionError,
        )
    return mapper


@frax_tool(
    name="frax_create_payment_entry_draft",
    risk="write",
    requires_confirmation=True,
    category="business_accounts",
    annotations=annotations_for(
        "write", open_world=True, title="Create Payment Entry Draft"
    ),
)
def create_payment_entry_draft(
    reference_doctype: Literal[
        "Sales Invoice", "Purchase Invoice", "Sales Order", "Purchase Order"
    ],
    reference_name: str,
    bank_account: str | None = None,
    party_amount: float | None = None,
    bank_amount: float | None = None,
    reference_date: str | None = None,
):
    """Generate and insert a native Payment Entry as an unsubmitted draft."""
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    frappe.get_doc(reference_doctype, reference_name).check_permission("read")
    if not frappe.has_permission("Payment Entry", "create"):
        frappe.throw(
            _("Not permitted to create Payment Entry."), frappe.PermissionError
        )
    entry = get_payment_entry(
        reference_doctype,
        reference_name,
        party_amount=party_amount,
        bank_account=bank_account,
        bank_amount=bank_amount,
        reference_date=reference_date,
        ignore_permissions=False,
    )
    if (
        entry.doctype != "Payment Entry"
        or not entry.is_new()
        or int(entry.docstatus or 0) != 0
    ):
        frappe.throw(_("The native payment helper did not return a new draft."))
    entry.flags.ignore_permissions = False
    entry.insert()
    return {
        "data": entry.as_dict(),
        "meta": {
            "docstatus": entry.docstatus,
            "source": [reference_doctype, reference_name],
        },
        "warnings": [],
        "links": {
            "document": frappe.utils.get_url_to_form("Payment Entry", entry.name)
        },
    }
