from __future__ import annotations

from typing import Any

import frappe

from frax.tools.registry import annotations_for, frax_tool


def register():
    return None


@frax_tool(
    name="frax_get_doctype_context",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get DocType Context"),
)
def get_doctype_context(doctype: str, include_fields: bool = True, field_limit: int = 120):
    """Get compact preflight context for one DocType.

    Use before non-trivial reads/writes. Summarizes merged metadata, core flags,
    fields, customizations, scripts, workflows, naming, permissions, and native UI
    signals without returning full script code or raw business records.

    Args:
        doctype: Exact DocType name to inspect.
        include_fields: Include compact merged field metadata.
        field_limit: Maximum number of fields to return when include_fields is true.
    """
    meta = frappe.get_meta(doctype)
    if not frappe.has_permission("DocType", "read", doctype):
        frappe.throw("Not permitted", frappe.PermissionError)

    fields = []
    if include_fields:
        for field in meta.fields[: max(0, field_limit)]:
            fields.append(
                {
                    "fieldname": field.fieldname,
                    "label": field.label,
                    "fieldtype": field.fieldtype,
                    "options": field.options,
                    "reqd": field.reqd,
                    "read_only": field.read_only,
                    "hidden": field.hidden,
                    "permlevel": field.permlevel,
                    "in_list_view": field.in_list_view,
                    "in_standard_filter": field.in_standard_filter,
                    "depends_on": field.depends_on,
                    "mandatory_depends_on": field.mandatory_depends_on,
                    "allow_on_submit": field.allow_on_submit,
                }
            )

    customization_filters = {"dt": doctype}
    custom_docperm_filters = {"parent": doctype}
    workflow_filters = {"document_type": doctype}
    script_filters = {"dt": doctype}

    return {
        "doctype": doctype,
        "flags": {
            "custom": meta.custom,
            "istable": meta.istable,
            "issingle": meta.issingle,
            "is_submittable": meta.is_submittable,
            "allow_rename": meta.allow_rename,
            "is_tree": getattr(meta, "is_tree", 0),
            "is_virtual": getattr(meta, "is_virtual", 0),
            "track_changes": meta.track_changes,
            "track_seen": meta.track_seen,
            "track_views": meta.track_views,
        },
        "naming": {
            "autoname": meta.autoname,
            "title_field": meta.title_field,
        },
        "permissions": {
            "can_read_doctype": frappe.has_permission("DocType", "read", doctype),
            "docperm_rows": len(meta.permissions or []),
            "permlevels": sorted({perm.permlevel for perm in meta.permissions or []}),
        },
        "fields": fields,
        "field_count": len(meta.fields),
        "field_limit_applied": include_fields and len(meta.fields) > field_limit,
        "child_tables": [
            {
                "fieldname": field.fieldname,
                "label": field.label,
                "options": field.options,
                "reqd": field.reqd,
            }
            for field in meta.get_table_fields()
        ],
        "customizations": {
            "custom_fields": _safe_list(
                "Custom Field",
                filters=customization_filters,
                fields=["name", "fieldname", "label", "fieldtype", "insert_after", "modified"],
            ),
            "property_setters": _safe_list(
                "Property Setter",
                filters={"doc_type": doctype},
                fields=["name", "field_name", "property", "property_type", "modified"],
            ),
            "custom_docperm_count": _safe_count("Custom DocPerm", custom_docperm_filters),
        },
        "behavior": {
            "workflows": _safe_list(
                "Workflow",
                filters=workflow_filters,
                fields=["name", "is_active", "workflow_state_field", "modified"],
            ),
            "active_workflow_count": _safe_count(
                "Workflow",
                {"document_type": doctype, "is_active": 1},
            ),
            "client_scripts": _safe_list(
                "Client Script",
                filters=script_filters,
                fields=["name", "view", "enabled", "modified"],
            ),
            "server_scripts": _safe_list(
                "Server Script",
                filters={"reference_doctype": doctype},
                fields=["name", "script_type", "doctype_event", "event_frequency", "disabled", "modified"],
            ),
            "notifications": _safe_list(
                "Notification",
                filters={"document_type": doctype},
                fields=["name", "enabled", "event", "channel", "modified"],
            ),
            "naming_rules": _safe_list(
                "Document Naming Rule",
                filters={"document_type": doctype},
                fields=["name", "disabled", "priority", "prefix", "modified"],
            ),
        },
        "native_ui": _native_ui_summary(doctype),
    }


@frax_tool(
    name="frax_get_native_ui_options",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get Native UI Options"),
)
def get_native_ui_options(doctype: str):
    """List native Frappe UI/reporting/output records related to one DocType.

    Use before creating dashboards, tables, KPIs, navigation, intake forms, prints,
    or notifications. Prefer existing native records where they fit. Email Templates
    are usually reached through Notifications or explicit template names, not directly
    by DocType.

    Args:
        doctype: Exact reference DocType/process DocType to inspect.
    """
    return {"doctype": doctype, **_native_ui_summary(doctype)}


def _native_ui_summary(doctype: str) -> dict[str, Any]:
    return {
        "reports": _safe_list(
            "Report",
            filters={"ref_doctype": doctype},
            fields=["name", "module", "report_type", "is_standard", "disabled", "modified"],
        ),
        "dashboard_charts": _safe_list(
            "Dashboard Chart",
            filters={"document_type": doctype},
            fields=["name", "chart_type", "source", "is_public", "is_standard", "modified"],
        ),
        "number_cards": _safe_list(
            "Number Card",
            filters={"document_type": doctype},
            fields=["name", "type", "is_public", "is_standard", "modified"],
        ),
        "web_forms": _safe_list(
            "Web Form",
            filters={"doc_type": doctype},
            fields=["name", "published", "login_required", "modified"],
        ),
        "print_formats": _safe_list(
            "Print Format",
            filters={"doc_type": doctype},
            fields=["name", "print_format_type", "standard", "disabled", "modified"],
        ),
        "notifications": _safe_list(
            "Notification",
            filters={"document_type": doctype},
            fields=["name", "enabled", "event", "channel", "modified"],
        ),
    }


def _safe_count(doctype: str, filters: dict[str, Any] | None = None) -> int | dict[str, Any]:
    try:
        return frappe.db.count(doctype, filters=filters)
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


def _safe_list(
    doctype: str,
    *,
    filters: dict[str, Any] | None = None,
    fields: list[str] | None = None,
    limit_page_length: int = 50,
) -> list[dict[str, Any]] | dict[str, Any]:
    try:
        return frappe.get_list(
            doctype,
            filters=filters,
            fields=fields or ["name", "modified"],
            limit_page_length=limit_page_length,
            order_by="modified desc",
        )
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
