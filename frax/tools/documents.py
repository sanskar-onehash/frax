from __future__ import annotations

import base64
from difflib import get_close_matches
from typing import Any

import frappe
from frappe import _
from frappe.model import default_fields, get_permitted_fields

from frax.setup import get_settings_state
from frax.tools.registry import annotations_for, frax_tool


def register():
    return None


def _page_length(value: int | None) -> int:
    settings = get_settings_state()
    default = int(settings.default_page_length or 20)
    maximum = int(settings.maximum_page_length or 200)
    return min(maximum, max(1, int(value or default)))


def _fields(doctype: str, fields: list[str] | None) -> tuple[list[str], list[dict[str, Any]]]:
    meta = frappe.get_meta(doctype)
    permitted = set(get_permitted_fields(doctype, permission_type="read")) | set(default_fields)
    valid = set(meta.get_valid_columns()) | permitted
    if not fields:
        fields = ["name"] + [
            field.fieldname
            for field in meta.fields
            if field.in_list_view and field.fieldname in permitted
        ]
    invalid = []
    for field in fields:
        if field not in valid or field not in permitted:
            invalid.append(
                {
                    "field": field,
                    "suggestions": get_close_matches(field, sorted(permitted), n=3),
                }
            )
    return list(dict.fromkeys(fields)), invalid


def _count(doctype: str, filters):
    rows = frappe.get_list(
        doctype,
        filters=filters,
        fields=["count(name) as total_count"],
        limit_page_length=1,
    )
    return int((rows[0] if rows else {}).get("total_count") or 0)


@frax_tool(
    name="frax_count_documents",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Count Frappe Documents"),
)
def count_documents(doctype: str, filters: dict[str, Any] | list[Any] | None = None):
    """Count documents with the acting user's normal Frappe permissions."""
    return {"doctype": doctype, "count": _count(doctype, filters), "filters": filters or {}}


@frax_tool(
    name="frax_get_documents",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get Multiple Frappe Documents"),
)
def get_documents(
    doctype: str,
    names: list[str],
    fields: list[str] | None = None,
    include_children: bool = False,
):
    """Read up to 50 named documents in one permission-aware call."""
    if not names or len(names) > 50:
        frappe.throw(_("Provide between 1 and 50 document names."))
    requested_fields, invalid = _fields(doctype, fields)
    if invalid:
        return {"data": [], "meta": {"doctype": doctype}, "warnings": invalid, "links": {}}
    data = []
    for name in dict.fromkeys(names):
        doc = frappe.get_doc(doctype, name)
        doc.check_permission("read")
        values = doc.as_dict() if include_children else {field: doc.get(field) for field in requested_fields}
        values.setdefault("name", doc.name)
        values.setdefault("doctype", doc.doctype)
        data.append(values)
    return {
        "data": data,
        "meta": {"doctype": doctype, "requested": len(names), "returned": len(data)},
        "warnings": [],
        "links": {},
    }


@frax_tool(
    name="frax_search_link",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Search Link Values"),
)
def search_link(
    doctype: str,
    text: str,
    filters: dict[str, Any] | list[Any] | None = None,
    page_length: int = 10,
    reference_doctype: str | None = None,
):
    """Search link values through Frappe's native standard/custom link query behavior."""
    from frappe.desk.search import search_link as native_search_link

    return native_search_link(
        doctype=doctype,
        txt=text,
        filters=filters,
        page_length=min(_page_length(page_length), 50),
        reference_doctype=reference_doctype,
        ignore_user_permissions=False,
    )


@frax_tool(
    name="frax_list_attachments",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List Document Attachments"),
)
def list_attachments(doctype: str, name: str):
    """List native File records attached to one readable document."""
    frappe.get_doc(doctype, name).check_permission("read")
    return frappe.get_list(
        "File",
        filters={"attached_to_doctype": doctype, "attached_to_name": name},
        fields=["name", "file_name", "file_url", "is_private", "file_size", "modified"],
        order_by="modified desc",
        page_length=200,
    )


@frax_tool(
    name="frax_get_document_relationships",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get Document Relationships"),
)
def get_document_relationships(doctype: str, name: str):
    """Return Frappe's permission-filtered Linked With records for one document."""
    from frappe.desk.form.linked_with import get as get_linked_documents

    frappe.get_doc(doctype, name).check_permission("read")
    linked = get_linked_documents(doctype, name)
    return {
        "data": linked,
        "meta": {
            "doctype": doctype,
            "name": name,
            "linked_doctypes": len(linked),
            "linked_documents": sum(len(rows) for rows in linked.values()),
        },
        "warnings": [],
        "links": {"document": frappe.utils.get_url_to_form(doctype, name)},
    }


@frax_tool(
    name="frax_download_attachment",
    risk="sensitive_read",
    requires_confirmation=True,
    annotations=annotations_for("sensitive_read", idempotent=True, title="Download Attachment"),
)
def download_attachment(file_name: str, doctype: str, name: str):
    """Return a bounded attachment as base64 after verifying its exact parent and permissions."""
    frappe.get_doc(doctype, name).check_permission("read")
    file_doc = frappe.get_doc("File", file_name)
    if file_doc.attached_to_doctype != doctype or file_doc.attached_to_name != name:
        frappe.throw(_("File attachment target does not match."), frappe.PermissionError)
    content = file_doc.get_content()
    if isinstance(content, str):
        content = content.encode()
    maximum = int(get_settings_state().maximum_download_bytes or 10 * 1024 * 1024)
    if len(content) > maximum:
        frappe.throw(_("File exceeds the configured MCP download limit."))
    return {
        "data": {
            "file_name": file_doc.file_name,
            "mime_type": file_doc.get("file_type") or "application/octet-stream",
            "size": len(content),
            "content_base64": base64.b64encode(content).decode(),
        },
        "meta": {"private": bool(file_doc.is_private)},
        "warnings": [],
        "links": {},
    }


@frax_tool(
    name="frax_render_document_pdf",
    risk="sensitive_read",
    requires_confirmation=True,
    annotations=annotations_for("sensitive_read", idempotent=True, title="Render Document PDF"),
)
def render_document_pdf(
    doctype: str,
    name: str,
    print_format: str | None = None,
    no_letterhead: bool = False,
    language: str | None = None,
):
    """Render a readable document through Frappe's native Print Format pipeline."""
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("print")
    content = frappe.get_print(
        doctype,
        name,
        print_format,
        doc=doc,
        as_pdf=True,
        no_letterhead=int(no_letterhead),
        language=language,
    )
    maximum = int(get_settings_state().maximum_download_bytes or 10 * 1024 * 1024)
    if len(content) > maximum:
        frappe.throw(_("PDF exceeds the configured MCP download limit."))
    return {
        "data": {
            "file_name": f"{name.replace('/', '-')}.pdf",
            "mime_type": "application/pdf",
            "size": len(content),
            "content_base64": base64.b64encode(content).decode(),
        },
        "meta": {"doctype": doctype, "name": name, "print_format": print_format},
        "warnings": [],
        "links": {"document": frappe.utils.get_url_to_form(doctype, name)},
    }


@frax_tool(
    name="frax_assign_document",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", title="Assign Document"),
)
def assign_document(
    doctype: str,
    name: str,
    users: list[str],
    description: str | None = None,
    due_date: str | None = None,
    priority: str = "Medium",
):
    """Create native Frappe assignments and notifications for a document."""
    from frappe.desk.form.assign_to import add

    return add(
        {
            "doctype": doctype,
            "name": name,
            "assign_to": users,
            "description": description,
            "date": due_date,
            "priority": priority,
        }
    )


@frax_tool(
    name="frax_unassign_document",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", title="Unassign Document"),
)
def unassign_document(doctype: str, name: str, user: str):
    """Remove one user's native Frappe assignment from a document."""
    from frappe.desk.form.assign_to import remove

    return remove(doctype, name, user)


@frax_tool(
    name="frax_set_document_tag",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", title="Add or Remove Document Tag"),
)
def set_document_tag(doctype: str, name: str, tag: str, add: bool = True):
    """Add or remove a native Frappe tag after checking document permission."""
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("write")
    if add:
        doc.add_tag(tag)
    else:
        doc.remove_tag(tag)
    return {"doctype": doctype, "name": name, "tag": tag, "added": add}
