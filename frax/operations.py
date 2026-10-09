from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import frappe
from frappe import _
from frappe.utils import add_days, now_datetime

from frax.setup import DEFAULTS, get_allowed_roles, get_settings_state


AUDIT_DOCTYPE = "Frax MCP Audit Log"
MAX_WINDOW_DAYS = 30
SUMMARY_LIMIT = 10


def require_operational_access():
    user = frappe.session.user
    if user == "Administrator":
        return
    if user in (None, "", "Guest") or "System Manager" not in frappe.get_roles():
        frappe.throw(
            _("System Manager access is required for operational diagnostics."),
            frappe.PermissionError,
        )


@frappe.whitelist(methods=["GET"])
def get_operational_health(days=7):
    require_operational_access()
    return _operational_health(_window_days(days))


@frappe.whitelist(methods=["GET"])
def get_diagnostic_export(days=7):
    require_operational_access()
    days = _window_days(days)
    settings = get_settings_state()
    allowed_roles = get_allowed_roles()
    from frax import __version__ as frax_version

    return {
        "schema_version": 1,
        "generated_at": str(now_datetime()),
        "versions": {
            "service": frax_version,
            "platform": getattr(frappe, "__version__", "unknown"),
            "protocol_library": _package_version("frappe-mcp"),
        },
        "service": {
            key: settings.get(key)
            for key in DEFAULTS
            if key not in {"audit_retention_days"}
        }
        | {
            "audit_retention_days": settings.audit_retention_days,
            "allowed_roles_configured": bool(allowed_roles),
            "allowed_role_count": len(allowed_roles),
            "business_application_installed": "erpnext" in frappe.get_installed_apps(),
        },
        "health": _operational_health(days),
        "redaction": {
            "arguments": "excluded",
            "actors": "excluded",
            "document_identifiers": "excluded",
            "error_messages": "excluded",
            "secrets": "excluded",
        },
    }


def _operational_health(days: int) -> dict:
    ended_at = now_datetime()
    started_at = add_days(ended_at, -days)
    window = {
        "days": days,
        "from": str(started_at),
        "to": str(ended_at),
    }
    if not frappe.db.exists("DocType", AUDIT_DOCTYPE):
        return {
            "available": False,
            "window": window,
            "totals": _empty_totals(),
            "categories": [],
            "slow_tools": [],
            "failures": [],
        }

    filters = {"creation": (">=", started_at)}
    outcomes = frappe.get_all(
        AUDIT_DOCTYPE,
        filters=filters,
        fields=["outcome", "count(name) as calls"],
        group_by="outcome",
    )
    latency = frappe.get_all(
        AUDIT_DOCTYPE,
        filters=filters,
        fields=[
            "count(name) as calls",
            "avg(duration_ms) as average_ms",
            "max(duration_ms) as maximum_ms",
        ],
        limit_page_length=1,
    )
    tools = frappe.get_all(
        AUDIT_DOCTYPE,
        filters=filters,
        fields=[
            "tool_name",
            "count(name) as calls",
            "avg(duration_ms) as average_ms",
            "max(duration_ms) as maximum_ms",
        ],
        group_by="tool_name",
        order_by="average_ms desc",
        limit_page_length=SUMMARY_LIMIT,
    )
    categories = frappe.get_all(
        AUDIT_DOCTYPE,
        filters=filters,
        fields=["category", "count(name) as calls"],
        group_by="category",
        order_by="calls desc",
        limit_page_length=SUMMARY_LIMIT,
    )
    failures = frappe.get_all(
        AUDIT_DOCTYPE,
        filters={**filters, "outcome": "error"},
        fields=[
            "tool_name",
            "error_class",
            "count(name) as calls",
            "max(creation) as last_seen",
        ],
        group_by="tool_name, error_class",
        order_by="calls desc",
        limit_page_length=SUMMARY_LIMIT,
    )
    return {
        "available": True,
        "window": window,
        "totals": _totals(outcomes, latency[0] if latency else {}),
        "categories": [
            {
                "category": row.get("category") or "uncategorized",
                "calls": _int(row.get("calls")),
            }
            for row in categories
        ],
        "slow_tools": [
            {
                "tool": row.get("tool_name") or "unknown",
                "calls": _int(row.get("calls")),
                "average_ms": _number(row.get("average_ms")),
                "maximum_ms": _number(row.get("maximum_ms")),
            }
            for row in tools
        ],
        "failures": [
            {
                "tool": row.get("tool_name") or "unknown",
                "error_class": row.get("error_class") or "UnknownError",
                "calls": _int(row.get("calls")),
                "last_seen": str(row.get("last_seen") or ""),
            }
            for row in failures
        ],
    }


def _totals(outcomes, latency) -> dict:
    outcome_counts = {
        row.get("outcome") or "unknown": _int(row.get("calls")) for row in outcomes
    }
    calls = sum(outcome_counts.values())
    successful = outcome_counts.get("success", 0)
    errors = outcome_counts.get("error", 0)
    return {
        "calls": calls,
        "successful": successful,
        "errors": errors,
        "success_rate_percent": round(successful * 100 / calls, 1) if calls else 0,
        "average_duration_ms": _number(latency.get("average_ms")),
        "maximum_duration_ms": _number(latency.get("maximum_ms")),
    }


def _empty_totals():
    return {
        "calls": 0,
        "successful": 0,
        "errors": 0,
        "success_rate_percent": 0,
        "average_duration_ms": 0,
        "maximum_duration_ms": 0,
    }


def _window_days(value) -> int:
    try:
        return min(MAX_WINDOW_DAYS, max(1, int(value)))
    except (TypeError, ValueError):
        return 7


def _int(value) -> int:
    return int(value or 0)


def _number(value) -> float | int:
    number = round(float(value or 0), 1)
    return int(number) if number.is_integer() else number


def _package_version(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"
