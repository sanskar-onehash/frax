from __future__ import annotations

import json
import re
from difflib import get_close_matches
from typing import Any, Literal
from urllib.parse import quote

import frappe
from frappe import _
from frappe.model import get_permitted_fields

from frax.setup import get_settings_state
from frax.tools.registry import annotations_for, frax_tool


REPORTING_DOCTYPES = {"Report", "Dashboard Chart", "Number Card", "Workspace"}
STANDARD_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "docstatus"}
NON_DATA_FIELDS = {"Section Break", "Column Break", "Tab Break", "HTML", "Button"}
NUMERIC_FIELDS = {"Int", "Float", "Currency", "Percent", "Duration"}
IMMUTABLE_UPDATE_FIELDS = STANDARD_FIELDS | {
    "doctype",
    "is_standard",
    "standard",
    "module",
}


def register():
    return None


@frax_tool(
    name="frax_get_reporting_context",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="Get Reporting Context"),
)
def get_reporting_context(doctype: str):
    """Return permitted fields and existing native reporting surfaces for a DocType."""
    from frax.tools.context import get_native_ui_options

    _require_source_permission(doctype)
    meta = frappe.get_meta(doctype)
    permitted = set(get_permitted_fields(doctype, permission_type="read"))
    fields = [
        {
            "fieldname": field.fieldname,
            "label": field.label,
            "fieldtype": field.fieldtype,
            "options": field.options,
            "in_list_view": field.in_list_view,
            "in_standard_filter": field.in_standard_filter,
        }
        for field in meta.fields
        if field.fieldname in permitted and field.fieldtype not in NON_DATA_FIELDS
    ]
    return {
        "doctype": doctype,
        "fields": fields,
        "standard_fields": sorted(STANDARD_FIELDS.intersection(permitted)),
        "native_artifacts": get_native_ui_options(doctype),
        "surfaces": {
            "table": "Report Builder for fields, filters, grouping, and simple aggregates; Query or Script Report for approved advanced logic.",
            "kpi": "Number Card backed by a DocType, saved Report, or permitted method.",
            "chart": "Dashboard Chart backed by a DocType, saved Report, or installed chart source.",
            "navigation": "Workspace containing shortcuts, cards, charts, and links.",
        },
        "artifact_doctypes": sorted(REPORTING_DOCTYPES),
        "mutation_policy": "Only non-standard site records can be created or changed; source-backed artifacts are protected.",
    }


@frax_tool(
    name="frax_validate_reporting_artifact",
    risk="sensitive_read",
    annotations=annotations_for(
        "sensitive_read", idempotent=True, title="Validate Reporting Artifact"
    ),
)
def validate_reporting_artifact(doc: dict[str, Any]):
    """Validate a proposed Report, Chart, Card, or Workspace without saving it."""
    return _validate_reporting_artifact(doc)


@frax_tool(
    name="frax_save_reporting_artifact",
    risk="admin",
    requires_confirmation=True,
    roles=["System Manager", "Report Manager"],
    annotations=annotations_for(
        "admin", open_world=True, title="Save Reporting Artifact"
    ),
)
def save_reporting_artifact(doc: dict[str, Any], expected_modified: str | None = None):
    """Create or update a non-standard native reporting artifact after validation."""
    if not isinstance(doc, dict):
        frappe.throw(_("doc must be an object."))
    doctype = doc.get("doctype")
    if doctype not in REPORTING_DOCTYPES:
        frappe.throw(_("Unsupported reporting artifact: {0}").format(doctype))

    name = doc.get("name") or (doc.get("report_name") if doctype == "Report" else None)
    existing = (
        frappe.get_doc(doctype, name)
        if name and frappe.db.exists(doctype, name)
        else None
    )
    if existing:
        existing.check_permission("write")
        if _is_standard(existing):
            frappe.throw(
                _("Standard/source-backed reporting artifacts cannot be changed.")
            )
        if not expected_modified:
            frappe.throw(
                _("expected_modified is required when updating a reporting artifact.")
            )
        if str(existing.modified) != str(expected_modified):
            frappe.throw(
                _("Reporting artifact changed since it was inspected."),
                frappe.TimestampMismatchError,
            )
        candidate = existing.as_dict()
        candidate.update(_mutable_values(doc))
        candidate["doctype"] = doctype
        candidate["name"] = existing.name
    else:
        candidate = {
            key: value
            for key, value in doc.items()
            if key not in STANDARD_FIELDS - {"name"}
        }
        candidate.pop("name", None)
        _set_non_standard(candidate)

    validation = _validate_reporting_artifact(candidate)
    if not validation["valid"]:
        frappe.throw(
            _("Reporting artifact validation failed: {0}").format(
                json.dumps(validation["diagnostics"])
            )
        )

    if existing:
        existing.update(_mutable_values(doc))
        existing.save()
        saved = existing
        operation = "updated"
    else:
        saved = frappe.get_doc(candidate).insert()
        operation = "created"

    result = saved.as_dict()
    result["_validation"] = validation
    return {
        "data": result,
        "meta": {"operation": operation},
        "warnings": [
            item for item in validation["diagnostics"] if item["severity"] != "error"
        ],
        "links": {
            "document": frappe.utils.get_url_to_form(doctype, saved.name),
        },
    }


@frax_tool(
    name="frax_preview_report_builder",
    risk="read",
    annotations=annotations_for(
        "read", idempotent=True, title="Preview Report Builder Query"
    ),
)
def preview_report_builder(
    doctype: str,
    fields: list[str],
    filters: dict[str, Any] | list[Any] | None = None,
    group_by: str | None = None,
    aggregate: Literal["count", "sum", "avg"] | None = None,
    aggregate_field: str | None = None,
    order_by: str | None = None,
    offset: int = 0,
    page_length: int | None = None,
):
    """Preview a bounded permission-aware Report Builder-shaped query."""
    _require_source_permission(doctype)
    permitted = set(get_permitted_fields(doctype, permission_type="read"))
    requested = list(dict.fromkeys(fields or ["name"]))
    checked = (
        requested
        + ([group_by] if group_by else [])
        + ([aggregate_field] if aggregate_field else [])
    )
    invalid = [field for field in checked if field and field not in permitted]
    invalid.extend(_invalid_filter_fields(filters, permitted, doctype))
    parsed_order = _validated_order_by(order_by, permitted)
    if invalid:
        return _invalid_fields_result(invalid, permitted)

    query_fields = requested
    if group_by:
        if not aggregate:
            frappe.throw(_("aggregate is required with group_by."))
        aggregate_field = aggregate_field or "name"
        if aggregate != "count":
            aggregate_meta = frappe.get_meta(doctype).get_field(aggregate_field)
            if not aggregate_meta or aggregate_meta.fieldtype not in NUMERIC_FIELDS:
                frappe.throw(_("sum and avg require a numeric aggregate_field."))
        query_fields = [group_by, f"{aggregate}({aggregate_field}) as value"]

    start, length = _page(offset, page_length)
    rows = frappe.get_list(
        doctype,
        fields=query_fields,
        filters=filters,
        group_by=group_by,
        order_by=parsed_order,
        limit_start=start,
        limit_page_length=length + 1,
    )
    has_more = len(rows) > length
    rows = rows[:length]
    return {
        "data": rows,
        "meta": {
            "doctype": doctype,
            "group_by": group_by,
            "aggregate": aggregate,
            "offset": start,
            "page_length": length,
            "returned": len(rows),
            "has_more": has_more,
        },
        "warnings": (
            [{"code": "result_truncated", "message": "More rows are available."}]
            if has_more
            else []
        ),
        "links": {},
    }


@frax_tool(
    name="frax_run_report",
    risk="sensitive_read",
    annotations=annotations_for("sensitive_read", idempotent=True, title="Run Report"),
)
def run_report(
    report_name: str,
    filters: dict[str, Any] | None = None,
    offset: int = 0,
    page_length: int | None = None,
):
    """Run a saved report using its native roles and reference-DocType permissions."""
    from frappe.desk.query_report import run as run_query_report

    if filters is not None and not isinstance(filters, dict):
        frappe.throw(_("filters must be an object."))
    report = frappe.get_doc("Report", report_name)
    report.check_permission("read")
    if report.disabled:
        frappe.throw(_("This report is disabled."), frappe.PermissionError)
    if not report.is_permitted() or not frappe.has_permission(
        report.ref_doctype, "report"
    ):
        frappe.throw(_("Not permitted to run this report."), frappe.PermissionError)

    start, length = _page(offset, page_length)
    if report.report_type == "Report Builder":
        columns, rows = report.get_data(
            filters=filters or {},
            limit=start + length + 1,
            user=frappe.session.user,
            as_dict=True,
        )
        rows = list(rows)[start : start + length + 1]
        result = {
            "columns": [_column_dict(column) for column in columns],
            "chart": None,
            "report_summary": None,
            "execution_time": 0,
        }
    else:
        result = run_query_report(
            report_name,
            filters=filters or {},
            user=frappe.session.user,
            ignore_prepared_report=False,
        )
        rows = list(result.get("result") or [])[start : start + length + 1]

    has_more = len(rows) > length
    rows = rows[:length]
    return {
        "data": rows,
        "meta": {
            "report_name": report_name,
            "report_type": report.report_type,
            "offset": start,
            "page_length": length,
            "returned": len(rows),
            "has_more": has_more,
            "execution_time": result.get("execution_time", 0),
            "prepared_report": bool(result.get("prepared_report")),
            "columns": result.get("columns") or [],
            "chart": result.get("chart"),
            "report_summary": result.get("report_summary"),
        },
        "warnings": (
            [{"code": "result_truncated", "message": "More rows are available."}]
            if has_more
            else []
        ),
        "links": {
            "report": f"{frappe.utils.get_url()}/app/query-report/{quote(report_name, safe='')}"
        },
    }


def _validate_reporting_artifact(doc):
    if not isinstance(doc, dict):
        frappe.throw(_("doc must be an object."))
    doc = dict(doc)
    doctype = doc.get("doctype")
    if doctype not in REPORTING_DOCTYPES:
        frappe.throw(_("Unsupported reporting artifact: {0}").format(doctype))

    diagnostics = _metadata_diagnostics(doc)
    if _is_standard(doc):
        diagnostics.append(
            {
                "severity": "error",
                "code": "standard_artifact",
                "message": "Only non-standard site reporting artifacts can be managed.",
            }
        )
    if doctype == "Report":
        diagnostics.extend(_report_diagnostics(doc))
    diagnostics.extend(_artifact_diagnostics(doc))
    diagnostics.extend(_json_diagnostics(doc))
    return {
        "valid": not any(item["severity"] == "error" for item in diagnostics),
        "doctype": doctype,
        "diagnostics": diagnostics,
        "executed": False,
        "saved": False,
    }


def _metadata_diagnostics(doc):
    meta = frappe.get_meta(doc["doctype"])
    diagnostics = []
    for field in meta.fields:
        if field.reqd and not doc.get(field.fieldname) and not field.default:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "required_field",
                    "field": field.fieldname,
                    "message": f"{field.label or field.fieldname} is required.",
                }
            )
    valid = set(meta.get_valid_columns()) | {"doctype", "name"}
    for field in (key for key in doc if key not in valid and not key.startswith("_")):
        diagnostics.append(
            {
                "severity": "warning",
                "code": "unknown_field",
                "field": field,
                "message": "The platform may ignore this field.",
            }
        )
    return diagnostics


def _report_diagnostics(doc):
    diagnostics = []
    report_type = doc.get("report_type")
    if report_type not in {
        "Report Builder",
        "Query Report",
        "Script Report",
        "Custom Report",
    }:
        diagnostics.append(
            {
                "severity": "error",
                "code": "unsupported_report_type",
                "message": "Choose a supported report type.",
            }
        )
        return diagnostics

    if report_type == "Query Report":
        query = (doc.get("query") or "").strip()
        if not query:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "missing_query",
                    "message": "Query Report requires a query.",
                }
            )
        else:
            try:
                from frappe.utils.safe_exec import check_safe_sql_query

                check_safe_sql_query(query)
            except Exception as exc:
                diagnostics.append(
                    {
                        "severity": "error",
                        "code": "unsafe_query",
                        "message": str(exc),
                    }
                )
            if re.search(r"\binto\s+(outfile|dumpfile)\b", query, flags=re.IGNORECASE):
                diagnostics.append(
                    {
                        "severity": "error",
                        "code": "file_output_query",
                        "message": "SQL file-output constructs are forbidden.",
                    }
                )
        diagnostics.append(
            {
                "severity": "warning",
                "code": "query_report_permissions",
                "message": "Review report roles carefully because SQL reports do not automatically apply document-level permissions.",
            }
        )
    elif report_type == "Script Report":
        from frax.tools.scripting import validate_server_script

        validation = validate_server_script.__wrapped__(
            doc.get("report_script") or "", script_type="Script Report"
        )
        diagnostics.extend(validation["diagnostics"])
    elif report_type == "Custom Report" and not doc.get("reference_report"):
        diagnostics.append(
            {
                "severity": "error",
                "code": "missing_reference_report",
                "message": "Custom Report requires reference_report.",
            }
        )
    if report_type in {"Query Report", "Script Report"} and not doc.get("roles"):
        diagnostics.append(
            {
                "severity": "error",
                "code": "missing_report_roles",
                "message": "Query and Script Reports require explicit allowed roles.",
            }
        )
    return diagnostics


def _json_diagnostics(doc):
    diagnostics = []
    for fieldname in (
        "json",
        "filters_json",
        "dynamic_filters_json",
        "custom_options",
        "content",
    ):
        value = doc.get(fieldname)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            json.loads(value)
        except (TypeError, ValueError) as exc:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "invalid_json",
                    "field": fieldname,
                    "message": str(exc),
                }
            )
    return diagnostics


def _artifact_diagnostics(doc):
    diagnostics = []
    doctype = doc["doctype"]
    required = []
    if doctype == "Dashboard Chart":
        chart_type = doc.get("chart_type")
        required.append("chart_type")
        if chart_type == "Custom":
            required.append("source")
        elif chart_type == "Report":
            required.append("report_name")
        elif chart_type:
            required.append("document_type")
    elif doctype == "Number Card":
        card_type = doc.get("type")
        required.append("type")
        if card_type == "Document Type":
            required.extend(("document_type", "function"))
        elif card_type == "Report":
            required.extend(("report_name", "report_field", "report_function"))
        elif card_type == "Custom":
            required.append("method")
    elif doctype == "Workspace":
        content = doc.get("content")
        if not content:
            required.append("content")
        else:
            try:
                if not isinstance(json.loads(content), list):
                    raise ValueError("Workspace content must be a JSON list.")
            except (TypeError, ValueError) as exc:
                diagnostics.append(
                    {
                        "severity": "error",
                        "code": "invalid_workspace_content",
                        "field": "content",
                        "message": str(exc),
                    }
                )

    for fieldname in required:
        if not doc.get(fieldname):
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "conditional_required_field",
                    "field": fieldname,
                    "message": f"{fieldname} is required for this configuration.",
                }
            )
    return diagnostics


def _require_source_permission(doctype):
    if not (
        frappe.has_permission(doctype, "read")
        or frappe.has_permission(doctype, "report")
    ):
        frappe.throw(
            _("Not permitted to inspect this DocType."), frappe.PermissionError
        )


def _invalid_filter_fields(filters, permitted, doctype):
    if not filters:
        return []
    fields = []

    def collect(value):
        if isinstance(value, dict):
            fields.extend(str(field).split(".")[-1] for field in value)
            return
        if not isinstance(value, (list, tuple)):
            return
        if len(value) >= 4 and value[0] == doctype and isinstance(value[1], str):
            fields.append(value[1])
            return
        if len(value) >= 3 and isinstance(value[0], str):
            fields.append(value[0].split(".")[-1])
            return
        for item in value:
            collect(item)

    collect(filters)
    return sorted({field for field in fields if field not in permitted})


def _validated_order_by(order_by, permitted):
    if not order_by:
        return None
    match = re.fullmatch(r"\s*([A-Za-z0-9_]+)\s*(asc|desc)?\s*", order_by, re.I)
    if not match or match.group(1) not in permitted:
        frappe.throw(_("order_by must use one permitted field and optional asc/desc."))
    return f"{match.group(1)} {(match.group(2) or 'asc').lower()}"


def _invalid_fields_result(invalid, permitted):
    return {
        "data": [],
        "meta": {"query_executed": False},
        "warnings": [
            {
                "code": "invalid_fields",
                "fields": [
                    {
                        "field": field,
                        "suggestions": get_close_matches(field, sorted(permitted), n=3),
                    }
                    for field in sorted(set(invalid))
                ],
            }
        ],
        "links": {},
    }


def _page(offset, page_length):
    settings = get_settings_state()
    maximum = int(settings.maximum_page_length or 200)
    default = int(settings.default_page_length or 20)
    return max(0, int(offset or 0)), min(max(1, int(page_length or default)), maximum)


def _is_standard(doc):
    return doc.get("is_standard") in ("Yes", 1, True) or doc.get("standard") in (
        "Yes",
        1,
        True,
    )


def _set_non_standard(doc):
    meta = frappe.get_meta(doc["doctype"])
    if meta.has_field("is_standard"):
        doc["is_standard"] = "No" if doc["doctype"] == "Report" else 0
    if meta.has_field("standard"):
        doc["standard"] = "No"


def _mutable_values(doc):
    return {
        key: value for key, value in doc.items() if key not in IMMUTABLE_UPDATE_FIELDS
    }


def _column_dict(column):
    if hasattr(column, "as_dict"):
        return column.as_dict()
    if isinstance(column, dict):
        return column
    return {"label": str(column), "fieldname": str(column), "fieldtype": "Data"}
