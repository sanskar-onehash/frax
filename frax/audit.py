from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe
from frappe.utils import add_days, now_datetime


SENSITIVE_KEYS = {
    "password",
    "api_key",
    "api_secret",
    "client_secret",
    "secret",
    "token",
    "filedata",
    "content_base64",
    "script",
    "report_script",
    "javascript",
}


def canonical_arguments(arguments: dict[str, Any]) -> str:
    cleaned = dict(arguments)
    return json.dumps(cleaned, sort_keys=True, separators=(",", ":"), default=str)


def arguments_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_arguments(arguments).encode()).hexdigest()


def target_from_arguments(arguments: dict[str, Any]) -> tuple[str | None, str | None]:
    doc = arguments.get("doc")
    if isinstance(doc, dict):
        return doc.get("doctype"), doc.get("name") or doc.get("docname")
    return (
        arguments.get("doctype") or arguments.get("source_doctype"),
        arguments.get("name")
        or arguments.get("docname")
        or arguments.get("old_name")
        or arguments.get("source_name"),
    )


def redacted(value: Any, key: str | None = None, depth: int = 0) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return "<redacted>"
    if depth > 3:
        return "<omitted>"
    if isinstance(value, dict):
        return {str(k): redacted(v, str(k), depth + 1) for k, v in list(value.items())[:30]}
    if isinstance(value, list):
        return [redacted(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, str) and len(value) > 256:
        return f"{value[:128]}…<{len(value)} chars>"
    return value


def log_tool_call(
    *,
    tool_name: str,
    category: str,
    risk: str,
    arguments: dict[str, Any],
    outcome: str,
    duration_ms: int,
    result: Any = None,
    error: Exception | None = None,
    correlation_id: str | None = None,
) -> None:
    try:
        if not frappe.db.exists("DocType", "Frax MCP Audit Log"):
            return
        doctype, name = target_from_arguments(arguments)
        affected = _affected_documents(result)
        frappe.get_doc(
            {
                "doctype": "Frax MCP Audit Log",
                "correlation_id": correlation_id,
                "actor": frappe.session.user or "Guest",
                "authentication_method": _authentication_method(),
                "tool_name": tool_name,
                "category": category,
                "risk": risk,
                "outcome": outcome,
                "duration_ms": duration_ms,
                "arguments_hash": arguments_hash(arguments),
                "arguments_preview": json.dumps(redacted(arguments), default=str)[:5000],
                "target_doctype": doctype,
                "target_name": name,
                "affected_documents": json.dumps(affected, default=str) if affected else None,
                "error_class": error.__class__.__name__ if error else None,
                "error_message": str(error)[:1000] if error else None,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="Frax MCP audit logging failed")


def _authentication_method() -> str:
    try:
        from frax.mcp import _request_auth_method

        return _request_auth_method()
    except Exception:
        return "unknown"


def _affected_documents(result: Any) -> list[dict[str, str]]:
    documents = []
    values = result if isinstance(result, list) else [result]
    for value in values:
        if hasattr(value, "as_dict"):
            value = value.as_dict()
        if not isinstance(value, dict):
            continue
        value = value.get("data", value)
        if isinstance(value, dict) and value.get("doctype") and value.get("name"):
            documents.append({"doctype": value["doctype"], "name": value["name"]})
    return documents[:50]


def delete_expired_audit_logs():
    settings = frappe.get_cached_doc("Frax MCP Settings")
    retention = max(30, int(settings.audit_retention_days or 90))
    cutoff = add_days(now_datetime(), -retention)
    for name in frappe.get_all(
        "Frax MCP Audit Log", filters={"creation": ("<", cutoff)}, pluck="name", limit=1000
    ):
        frappe.delete_doc("Frax MCP Audit Log", name, ignore_permissions=True, force=True)
