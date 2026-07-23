from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from frax.tools.registry import annotations_for, frax_tool


def register():
    return None


@frax_tool(
    name="frax_list_documents",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List Frappe Documents"),
)
def list_documents(
    doctype: str,
    fields: list[str] | None = None,
    filters: dict[str, Any] | list[Any] | None = None,
    order_by: str | None = None,
    limit_start: int | None = None,
    limit_page_length: int = 20,
):
    """List records from one DocType using the current user's Frappe permissions.

    Use for paginated discovery and light inspection. Request only the fields needed;
    call frax_get_doctype_context first when field names, child tables, permissions,
    workflows, or customizations are uncertain.

    Args:
        doctype: DocType to query. Must be an exact DocType name.
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


@frax_tool(
    name="frax_get_document",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get Frappe Document"),
)
def get_document(doctype: str, name: str | None = None, filters: dict[str, Any] | None = None):
    """Get one document by name or filters using the current user's Frappe permissions.

    Use after identifying the DocType and document name. For Singles, omit name.
    This returns record data and child rows; it does not explain controller hooks,
    scripts, workflows, or effective write safety by itself.

    Args:
        doctype: DocType to load.
        name: Document name. Optional for Single doctypes or filter lookup.
        filters: Filters used when name is not provided.
    """
    from frappe.client import get

    return get(doctype=doctype, name=name, filters=filters)


@frax_tool(
    name="frax_get_value",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get Frappe Field Value"),
)
def get_value(doctype: str, fieldname: str | list[str], filters: str | dict[str, Any] | None = None):
    """Get selected field values from one document.

    Use for token-efficient reads when the exact fieldnames are already known.
    Inspect DocType metadata first when fieldnames or field types are uncertain.

    Args:
        doctype: DocType to query.
        fieldname: Field name or list of field names to return.
        filters: Document name or filters identifying the record.
    """
    from frappe.client import get_value

    return get_value(doctype=doctype, fieldname=fieldname, filters=filters)


@frax_tool(
    name="frax_create_document",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", open_world=True, title="Create Frappe Document"),
)
def create_document(doc: dict[str, Any]):
    """Create a new Frappe document through normal Frappe insert behavior.

    Preflight: inspect target DocType metadata, mandatory fields, naming/autoname,
    permissions, workflows, Server Scripts, Client Scripts, hooks, and relevant settings
    when the insert is non-trivial or business-critical. Insert may trigger validations,
    hooks, notifications, jobs, integrations, and child-table behavior.

    Args:
        doc: Document payload including doctype and field values.
    """
    from frappe.client import insert

    return _json_safe(insert(doc=doc))


@frax_tool(
    name="frax_save_document",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", open_world=True, title="Save Frappe Document"),
)
def save_document(doc: dict[str, Any], merge: bool = False):
    """Save an existing Frappe document through normal Frappe save behavior.

    Preflight non-trivial saves with metadata, permissions, workflow state, scripts,
    hooks, changed fields, docstatus, and relevant settings. Save may trigger validation,
    versioning, notifications, jobs, integrations, and update-after-submit rules.

    Args:
        doc: Full document payload including doctype and name.
        merge: When true, load the latest document and apply only mutable payload
            fields before saving. Default false preserves native Frappe save semantics,
            including stale document checks.
    """
    from frappe.client import save

    if not merge:
        return save(doc=doc)

    doctype = doc.get("doctype")
    name = doc.get("name")

    if not doctype:
        frappe.throw(_("Document payload must include doctype"))
    if not name and not frappe.get_meta(doctype).issingle:
        frappe.throw(_("Document payload must include name"))

    meta = frappe.get_meta(doctype)
    current = frappe.get_doc(doctype, name) if not meta.issingle else frappe.get_doc(doctype)

    current.update(_get_mutable_patch(doc, current))
    current.save()
    return current.as_dict()


@frax_tool(
    name="frax_set_value",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", open_world=True, title="Set Frappe Field Value"),
)
def set_value(doctype: str, name: str, fieldname: str | dict[str, Any], value: Any | None = None):
    """Set one or more fields on a document.

    Use only when fieldnames and write safety are known. Prefer frax_save_document
    for changes that should preserve full document context. Preflight field permlevels,
    workflows, docstatus, allow_on_submit, scripts, and hooks for material changes.

    Args:
        doctype: DocType of the document.
        name: Document name.
        fieldname: Field name or a dict of field values.
        value: Value to set when fieldname is a single field.
    """
    from frappe.client import set_value

    return set_value(doctype=doctype, name=name, fieldname=fieldname, value=value)


@frax_tool(
    name="frax_bulk_update_documents",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", open_world=True, title="Bulk Update Frappe Documents"),
)
def bulk_update_documents(docs: list[dict[str, Any]]):
    """Bulk update documents through Frappe's client bulk update API.

    High-risk for business data. Preflight the DocType context, permissions,
    workflows, scripts, hooks, naming/status side effects, and idempotency. Use small
    batches and confirm the exact target set before calling.

    Args:
        docs: List of documents. Each item must include doctype and docname.
    """
    import json

    from frappe.client import bulk_update

    return bulk_update(docs=json.dumps(docs))


@frax_tool(
    name="frax_delete_document",
    risk="destructive",
    requires_confirmation=True,
    annotations=annotations_for("destructive", open_world=True, title="Delete Frappe Document"),
)
def delete_document(doctype: str, name: str):
    """Delete one document through normal Frappe delete behavior.

    Destructive. Preflight links, permissions, submitted state, workflows, hooks,
    Server Scripts, child rows, and downstream records. Prefer cancellation over
    deletion for submitted transaction records when Frappe semantics require it.

    Args:
        doctype: DocType of the document to delete.
        name: Document name to delete.
    """
    from frappe.client import delete
    from frappe.utils.global_search import delete_for_document

    doc = frappe.get_doc(doctype, name)
    result = delete(doctype=doctype, name=name)
    try:
        delete_for_document(doc)
    except Exception:
        frappe.clear_messages()

    return result


@frax_tool(
    name="frax_submit_document",
    risk="destructive",
    requires_confirmation=True,
    annotations=annotations_for("destructive", open_world=True, title="Submit Frappe Document"),
)
def submit_document(doc: dict[str, Any]):
    """Submit a submittable document through normal Frappe submit behavior.

    High-risk. Submitting can create ledger, stock, asset, accounting, workflow,
    notification, email, job, integration, and linked-document side effects. Inspect
    DocType context, workflow transitions, permissions, scripts, hooks, and settings first.

    Args:
        doc: Document identity payload including doctype and name. Additional fields
            are ignored; save edits first, then submit.
    """
    doctype = doc.get("doctype")
    name = doc.get("name")

    if not doctype:
        frappe.throw(_("Document payload must include doctype"))
    if not name:
        frappe.throw(_("Document payload must include name"))

    current = frappe.get_doc(doctype, name)
    current.submit()
    return current.as_dict()


@frax_tool(
    name="frax_cancel_document",
    risk="destructive",
    requires_confirmation=True,
    annotations=annotations_for("destructive", open_world=True, title="Cancel Frappe Document"),
)
def cancel_document(doctype: str, name: str):
    """Cancel a submitted document through normal Frappe cancel behavior.

    High-risk. Cancellation may reverse ledgers, stock, asset, accounting, workflow,
    notification, integration, and linked-document state. Inspect context and confirm
    the exact document before calling.

    Args:
        doctype: DocType of the document to cancel.
        name: Document name to cancel.
    """
    from frappe.client import cancel

    return cancel(doctype=doctype, name=name)


@frax_tool(
    name="frax_rename_document",
    risk="destructive",
    requires_confirmation=True,
    annotations=annotations_for("destructive", title="Rename Frappe Document"),
)
def rename_document(doctype: str, old_name: str, new_name: str, merge: bool = False):
    """Rename or merge a Frappe document.

    Destructive when merge is true and risky when linked records exist. Inspect naming
    rules, autoname behavior, links, permissions, and downstream references first.

    Args:
        doctype: DocType of the document to rename.
        old_name: Current document name.
        new_name: New document name.
        merge: Whether to merge into an existing document.
    """
    from frappe.client import rename_doc

    return rename_doc(doctype=doctype, old_name=old_name, new_name=new_name, merge=merge)


@frax_tool(
    name="frax_get_workflow_transitions",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get Workflow Transitions"),
)
def get_workflow_transitions(doc: dict[str, Any]):
    """List workflow actions currently available for a document and acting user.

    Use before changing workflow state. Prefer frax_apply_workflow over direct field
    edits when a workflow controls status or docstatus.

    Args:
        doc: Document payload including doctype and name.
    """
    from frappe.model.workflow import get_transitions, get_workflow_name

    doctype = doc.get("doctype")
    if not doctype:
        frappe.throw(_("Document payload must include doctype"))

    workflow_name = get_workflow_name(doctype)
    if not workflow_name:
        return {"transitions": [], "reason": "No active workflow configured"}

    return {"transitions": get_transitions(doc=doc, raise_exception=False)}


@frax_tool(
    name="frax_apply_workflow",
    risk="destructive",
    requires_confirmation=True,
    annotations=annotations_for("destructive", open_world=True, title="Apply Workflow Action"),
)
def apply_workflow(doc: dict[str, Any], action: str):
    """Apply one allowed Frappe workflow action to a document.

    Preflight available transitions, transition roles/conditions, state/docstatus effects,
    permissions, scripts, hooks, and notifications. Do not directly edit workflow state
    when this tool can apply the native transition.

    Args:
        doc: Document payload including doctype and name.
        action: Workflow action label to apply.
    """
    from frappe.model.workflow import apply_workflow

    return apply_workflow(doc=doc, action=action)


@frax_tool(
    name="frax_add_comment",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", title="Add Document Comment"),
)
def add_comment(doctype: str, name: str, text: str, comment_type: str = "Comment"):
    """Add a Comment record to a document after checking read permission.

    Use for timeline notes and operational comments. Comments may notify followers
    depending on site behavior.

    Args:
        doctype: DocType of the document.
        name: Document name.
        text: Comment text.
        comment_type: Frappe comment type.
    """
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    return doc.add_comment(comment_type=comment_type, text=text)


@frax_tool(
    name="frax_follow_document",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", title="Follow Document"),
)
def follow_document(doctype: str, name: str, following: bool = True):
    """Follow or unfollow a document for the current user.

    This changes the acting user's follow state and may affect notifications.

    Args:
        doctype: DocType of the document.
        name: Document name.
        following: True to follow, false to unfollow.
    """
    from frappe.desk.form.document_follow import update_follow

    return update_follow(doctype=doctype, doc_name=name, following=following)


@frax_tool(
    name="frax_attach_file",
    risk="write",
    requires_confirmation=True,
    annotations=annotations_for("write", open_world=True, title="Attach File"),
)
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
    """Attach a file to a document and optionally update a file field.

    Open-world write because it stores caller-provided file content. Confirm filename,
    privacy, target document, and target docfield before calling.

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


@frax_tool(
    name="frax_search",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Search Frappe"),
)
def search(
    text: str,
    start: int = 0,
    limit: int = 20,
    doctype: str = "",
    exact_match: bool = True,
    verify_results: bool = False,
):
    """Search globally across documents readable by the current user.

    Use for discovery when the DocType or document name is unknown. Results may be
    broad; narrow by DocType and pagination where possible. Frappe global search
    indexing is refreshed asynchronously, so recent creates/deletes may not appear
    immediately. Use exact get/list tools, or verify_results=True, when confirming
    current document existence.

    Args:
        text: Search phrase.
        start: Offset for pagination.
        limit: Maximum number of results.
        doctype: Optional DocType to restrict search.
        exact_match: Prepend exact document-name matches for ID-like searches.
        verify_results: Drop global-search hits whose backing document no longer
            exists or is not readable. Disabled by default to preserve Frappe search
            behavior for broad discovery.
    """
    from frappe.utils.global_search import search

    limit = max(0, limit)
    exact_results = (
        _find_exact_search_results(text=text, doctype=doctype, limit=limit)
        if exact_match and _should_exact_scan(text, doctype)
        else []
    )
    fuzzy_results = search(text=text, start=start, limit=limit, doctype=doctype)

    return _dedupe_search_results([*exact_results, *fuzzy_results], verify_exists=verify_results)[:limit]


@frax_tool(
    name="frax_get_document_meta",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get DocType Metadata"),
)
def get_document_meta(doctype: str):
    """Get merged DocType metadata for a DocType.

    Includes standard metadata plus Custom Fields and Property Setters as returned
    by Frappe get_meta. Use before reads/writes when fields, child tables, Singles,
    virtual/tree/submittable flags, naming, or permissions are uncertain.

    Args:
        doctype: DocType to inspect.
    """
    meta = frappe.get_meta(doctype)
    if not frappe.has_permission("DocType", "read", doctype):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    return meta.as_dict()


@frax_tool(
    name="frax_get_document_permissions",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get Document Permissions"),
)
def get_document_permissions(doctype: str, name: str):
    """Get evaluated permissions for one document and the current user.

    Use before writes and when access behavior is unclear. For full permission debugging,
    also inspect Custom DocPerm, User Permissions, shares, workflows, and permission scripts.

    Args:
        doctype: DocType of the document.
        name: Document name.
    """
    from frappe.client import get_doc_permissions

    return get_doc_permissions(doctype=doctype, docname=name)


@frax_tool(
    name="frax_get_versions",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get App Versions"),
)
def get_versions():
    """Get versions of installed Frappe apps for version-aware behavior checks."""
    from frappe.utils.change_log import get_versions

    return get_versions()


_SYSTEM_FIELDS = {
    "doctype",
    "name",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "docstatus",
    "idx",
}

_CLIENT_ONLY_FIELDS = {
    "__islocal",
    "__last_sync_on",
    "__onload",
    "__unsaved",
    "_assign",
    "_comments",
    "_liked_by",
    "_seen",
    "_user_tags",
}


def _get_mutable_patch(payload: dict[str, Any], current) -> dict[str, Any]:
    patch = {}
    table_fields = {field.fieldname for field in current.meta.get_table_fields()}
    valid_fields = set(current.meta.get_valid_columns()) | table_fields

    for fieldname, value in payload.items():
        if fieldname in _SYSTEM_FIELDS or fieldname in _CLIENT_ONLY_FIELDS or fieldname.startswith("_"):
            continue
        if fieldname not in valid_fields:
            continue
        if fieldname in table_fields:
            cleaned_rows = [_strip_child_system_fields(row) for row in value or []]
            if cleaned_rows != [_strip_child_system_fields(row.as_dict()) for row in current.get(fieldname, [])]:
                patch[fieldname] = cleaned_rows
            continue
        if current.get(fieldname) != value:
            patch[fieldname] = value

    return patch


def _strip_child_system_fields(row: dict[str, Any]) -> dict[str, Any]:
    child_system_fields = _SYSTEM_FIELDS - {"name"}
    return {
        key: value
        for key, value in row.items()
        if key not in child_system_fields
        and key not in {"parent", "parentfield", "parenttype"}
        and key not in _CLIENT_ONLY_FIELDS
        and not key.startswith("_")
    }


def _should_exact_scan(text: str, doctype: str = "") -> bool:
    text = (text or "").strip()
    return bool(doctype) or bool(text and not any(char.isspace() for char in text))


def _find_exact_search_results(text: str, doctype: str = "", limit: int = 20) -> list[dict[str, Any]]:
    text = (text or "").strip()
    if not text or limit <= 0:
        return []

    if doctype:
        return _exact_result_for_doctype(doctype, text)

    results = []
    readable_doctypes = frappe.get_user().get_can_read()
    for candidate_doctype in readable_doctypes:
        if len(results) >= limit:
            break
        try:
            meta = frappe.get_meta(candidate_doctype)
            if meta.issingle or meta.istable or getattr(meta, "is_virtual", 0):
                continue
            results.extend(_exact_result_for_doctype(candidate_doctype, text))
        except Exception:
            frappe.clear_messages()

    return results


def _exact_result_for_doctype(doctype: str, text: str) -> list[dict[str, Any]]:
    try:
        if not frappe.has_permission(doctype, "read"):
            return []
        meta = frappe.get_meta(doctype)
        if meta.issingle or meta.istable or getattr(meta, "is_virtual", 0):
            return []
        if not frappe.db.table_exists(doctype):
            return []
        if not frappe.db.exists(doctype, text):
            return []

        doc = frappe.get_doc(doctype, text)
        doc.check_permission("read")
        return [
            {
                "doctype": doctype,
                "name": doc.name,
                "title": doc.get_title(),
                "content": doc.get_title(),
                "rank": 9999,
                "match_type": "exact_name",
            }
        ]
    except Exception:
        frappe.clear_messages()
        return []


def _dedupe_search_results(results: list[Any], verify_exists: bool = False) -> list[Any]:
    deduped = []
    seen = set()
    for result in results:
        key = (result.get("doctype"), result.get("name"))
        if key in seen:
            continue
        if verify_exists and not _search_result_exists(result):
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _search_result_exists(result: Any) -> bool:
    doctype = result.get("doctype")
    name = result.get("name")
    if not doctype or not name:
        return False

    try:
        meta = frappe.get_meta(doctype)
        if meta.issingle:
            return frappe.has_permission(doctype, "read")
        if meta.istable or getattr(meta, "is_virtual", 0):
            return False
        if not frappe.db.table_exists(doctype):
            return False
        if not frappe.db.exists(doctype, name):
            return False
        frappe.get_doc(doctype, name).check_permission("read")
        return True
    except Exception:
        frappe.clear_messages()
        return False


def _json_safe(value: Any) -> Any:
    import json

    from frappe.utils.response import json_handler

    return json.loads(json.dumps(value, default=json_handler))
