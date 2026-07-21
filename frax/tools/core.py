from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from frax.tools.registry import annotations_for, frax_tool


def register():
    return None


@frax_tool(name="frax_list_documents", risk="read", annotations=annotations_for("read", idempotent=True))
def list_documents(
    doctype: str,
    fields: list[str] | None = None,
    filters: dict[str, Any] | list[Any] | None = None,
    order_by: str | None = None,
    limit_start: int | None = None,
    limit_page_length: int = 20,
):
    """List documents in a DocType using the current user's Frappe permissions.

    Args:
        doctype: DocType to query.
        fields: Field names to return. Defaults to name.
        filters: Frappe filters to apply.
        order_by: Optional order clause.
        limit_start: Offset for pagination.
        limit_page_length: Maximum number of records to return.
    """
    from frappe.client import get_list

    return get_list(
        doctype=doctype,
        fields=fields,
        filters=filters,
        order_by=order_by,
        limit_start=limit_start,
        limit_page_length=limit_page_length,
    )


@frax_tool(name="frax_get_document", risk="read", annotations=annotations_for("read", idempotent=True))
def get_document(doctype: str, name: str | None = None, filters: dict[str, Any] | None = None):
    """Get one document by name or filters using the current user's Frappe permissions.

    Args:
        doctype: DocType to load.
        name: Document name. Optional for Single doctypes or filter lookup.
        filters: Filters used when name is not provided.
    """
    from frappe.client import get

    return get(doctype=doctype, name=name, filters=filters)


@frax_tool(name="frax_get_value", risk="read", annotations=annotations_for("read", idempotent=True))
def get_value(doctype: str, fieldname: str | list[str], filters: str | dict[str, Any] | None = None):
    """Get one or more field values from a document.

    Args:
        doctype: DocType to query.
        fieldname: Field name or list of field names to return.
        filters: Document name or filters identifying the record.
    """
    from frappe.client import get_value

    return get_value(doctype=doctype, fieldname=fieldname, filters=filters)


@frax_tool(name="frax_create_document", risk="write", requires_confirmation=True)
def create_document(doc: dict[str, Any]):
    """Create a new Frappe document.

    Args:
        doc: Document payload including doctype and field values.
    """
    from frappe.client import insert

    return insert(doc=doc)


@frax_tool(name="frax_save_document", risk="write", requires_confirmation=True)
def save_document(doc: dict[str, Any]):
    """Save an existing Frappe document.

    Args:
        doc: Full document payload including doctype and name.
    """
    from frappe.client import save

    return save(doc=doc)


@frax_tool(name="frax_set_value", risk="write", requires_confirmation=True)
def set_value(doctype: str, name: str, fieldname: str | dict[str, Any], value: Any | None = None):
    """Set one or more fields on a document.

    Args:
        doctype: DocType of the document.
        name: Document name.
        fieldname: Field name or a dict of field values.
        value: Value to set when fieldname is a single field.
    """
    from frappe.client import set_value

    return set_value(doctype=doctype, name=name, fieldname=fieldname, value=value)


@frax_tool(name="frax_bulk_update_documents", risk="write", requires_confirmation=True)
def bulk_update_documents(docs: list[dict[str, Any]]):
    """Bulk update documents.

    Args:
        docs: List of documents. Each item must include doctype and docname.
    """
    import json

    from frappe.client import bulk_update

    return bulk_update(docs=json.dumps(docs))


@frax_tool(name="frax_delete_document", risk="destructive", requires_confirmation=True)
def delete_document(doctype: str, name: str):
    """Delete a document.

    Args:
        doctype: DocType of the document to delete.
        name: Document name to delete.
    """
    from frappe.client import delete

    return delete(doctype=doctype, name=name)


@frax_tool(name="frax_submit_document", risk="destructive", requires_confirmation=True)
def submit_document(doc: dict[str, Any]):
    """Submit a document.

    Args:
        doc: Full document payload including doctype and name.
    """
    from frappe.client import submit

    return submit(doc=doc)


@frax_tool(name="frax_cancel_document", risk="destructive", requires_confirmation=True)
def cancel_document(doctype: str, name: str):
    """Cancel a submitted document.

    Args:
        doctype: DocType of the document to cancel.
        name: Document name to cancel.
    """
    from frappe.client import cancel

    return cancel(doctype=doctype, name=name)


@frax_tool(name="frax_rename_document", risk="destructive", requires_confirmation=True)
def rename_document(doctype: str, old_name: str, new_name: str, merge: bool = False):
    """Rename a document.

    Args:
        doctype: DocType of the document to rename.
        old_name: Current document name.
        new_name: New document name.
        merge: Whether to merge into an existing document.
    """
    from frappe.client import rename_doc

    return rename_doc(doctype=doctype, old_name=old_name, new_name=new_name, merge=merge)


@frax_tool(name="frax_get_workflow_transitions", risk="read", annotations=annotations_for("read", idempotent=True))
def get_workflow_transitions(doc: dict[str, Any]):
    """List workflow transitions available for a document.

    Args:
        doc: Document payload including doctype and name.
    """
    from frappe.model.workflow import get_transitions

    return get_transitions(doc=doc)


@frax_tool(name="frax_apply_workflow", risk="write", requires_confirmation=True)
def apply_workflow(doc: dict[str, Any], action: str):
    """Apply a workflow action to a document.

    Args:
        doc: Document payload including doctype and name.
        action: Workflow action label to apply.
    """
    from frappe.model.workflow import apply_workflow

    return apply_workflow(doc=doc, action=action)


@frax_tool(name="frax_add_comment", risk="write", requires_confirmation=True)
def add_comment(doctype: str, name: str, text: str, comment_type: str = "Comment"):
    """Add a comment to a document.

    Args:
        doctype: DocType of the document.
        name: Document name.
        text: Comment text.
        comment_type: Frappe comment type.
    """
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    return doc.add_comment(comment_type=comment_type, text=text)


@frax_tool(name="frax_follow_document", risk="write", requires_confirmation=True)
def follow_document(doctype: str, name: str, following: bool = True):
    """Follow or unfollow a document for the current user.

    Args:
        doctype: DocType of the document.
        name: Document name.
        following: True to follow, false to unfollow.
    """
    from frappe.desk.form.document_follow import update_follow

    return update_follow(doctype=doctype, doc_name=name, following=following)


@frax_tool(name="frax_attach_file", risk="write", requires_confirmation=True, annotations=annotations_for("write", open_world=True))
def attach_file(
    filename: str,
    filedata: str,
    doctype: str,
    docname: str,
    folder: str | None = None,
    decode_base64: bool = False,
    is_private: bool | None = None,
    docfield: str | None = None,
):
    """Attach a file to a document.

    Args:
        filename: File name.
        filedata: File content accepted by Frappe's attach_file API.
        doctype: Target DocType.
        docname: Target document name.
        folder: Optional target folder.
        decode_base64: Whether filedata should be base64 decoded.
        is_private: Whether the file should be private.
        docfield: Optional file field to update with the file URL.
    """
    from frappe.client import attach_file

    return attach_file(
        filename=filename,
        filedata=filedata,
        doctype=doctype,
        docname=docname,
        folder=folder,
        decode_base64=decode_base64,
        is_private=is_private,
        docfield=docfield,
    )


@frax_tool(name="frax_search", risk="read", annotations=annotations_for("read", idempotent=True))
def search(text: str, start: int = 0, limit: int = 20, doctype: str = ""):
    """Search globally across readable documents.

    Args:
        text: Search phrase.
        start: Offset for pagination.
        limit: Maximum number of results.
        doctype: Optional DocType to restrict search.
    """
    from frappe.utils.global_search import search

    return search(text=text, start=start, limit=limit, doctype=doctype)


@frax_tool(name="frax_get_document_meta", risk="read", annotations=annotations_for("read", idempotent=True))
def get_document_meta(doctype: str):
    """Get DocType metadata for a document type.

    Args:
        doctype: DocType to inspect.
    """
    meta = frappe.get_meta(doctype)
    if not frappe.has_permission("DocType", "read", doctype):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    return meta.as_dict()


@frax_tool(name="frax_get_document_permissions", risk="read", annotations=annotations_for("read", idempotent=True))
def get_document_permissions(doctype: str, name: str):
    """Get evaluated permissions for a document.

    Args:
        doctype: DocType of the document.
        name: Document name.
    """
    from frappe.client import get_doc_permissions

    return get_doc_permissions(doctype=doctype, docname=name)


@frax_tool(name="frax_get_versions", risk="read", annotations=annotations_for("read", idempotent=True))
def get_versions():
    """Get versions of installed Frappe apps."""
    from frappe.utils.change_log import get_versions

    return get_versions()
