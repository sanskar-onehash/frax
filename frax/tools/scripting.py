from __future__ import annotations

import ast
import warnings
from typing import Any

from RestrictedPython import compile_restricted
from frappe.utils.safe_exec import FrappeTransformer, get_safe_globals, is_safe_exec_enabled

from frax.tools.registry import annotations_for, frax_tool


def register():
    return None


SCRIPT_LOCALS = {
    "DocType Event": {"doc"},
    "Permission Query": {"user", "conditions"},
    "API": set(),
    "Scheduler Event": set(),
    "Script Report": {"filters", "data", "result", "columns", "chart", "report_summary"},
}


@frax_tool(
    name="frax_get_server_script_context",
    risk="sensitive_read",
    roles=["System Manager", "Script Manager"],
    annotations=annotations_for("sensitive_read", idempotent=True, title="Get Server Script Runtime Context"),
)
def get_server_script_context(script_type: str = "DocType Event"):
    """Return the live restricted runtime surface for the installed Frappe version."""
    safe = get_safe_globals()
    frappe_namespace = safe.get("frappe") or {}
    database_namespace = frappe_namespace.get("db") or {}
    return {
        "server_scripts_enabled": bool(is_safe_exec_enabled()),
        "script_type": script_type,
        "locals": sorted(SCRIPT_LOCALS.get(script_type, set())),
        "top_level_globals": sorted(key for key in safe if not str(key).startswith("_")),
        "frappe_methods": sorted(key for key in frappe_namespace if not str(key).startswith("_")),
        "database_methods": sorted(key for key in database_namespace if not str(key).startswith("_")),
        "commit_rollback_available": script_type != "DocType Event",
        "notes": [
            "RestrictedPython is not normal Python; imports and private attributes are unavailable.",
            "Compilation validation does not execute the script.",
            "Direct database writes bypass document controller behavior and are reported as warnings.",
        ],
    }


@frax_tool(
    name="frax_validate_server_script",
    risk="sensitive_read",
    roles=["System Manager", "Script Manager"],
    annotations=annotations_for("sensitive_read", idempotent=True, title="Validate Server Script"),
)
def validate_server_script(
    script: str,
    script_type: str = "DocType Event",
    doctype_event: str | None = None,
    reference_doctype: str | None = None,
):
    """Compile proposed Server Script code and return warnings without executing or blocking it."""
    diagnostics: list[dict[str, Any]] = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            compile_restricted(script or "", filename="<frax-validation>", policy=FrappeTransformer)
        diagnostics.extend(
            {"severity": "warning", "code": "compiler_warning", "message": str(item.message)}
            for item in caught
        )
        compilable = True
    except Exception as exc:
        compilable = False
        diagnostics.append(
            {
                "severity": "error",
                "code": "restricted_compilation_error",
                "message": str(exc),
            }
        )

    diagnostics.extend(_static_diagnostics(script or "", script_type))
    return {
        "compilable": compilable,
        "server_scripts_enabled": bool(is_safe_exec_enabled()),
        "script_type": script_type,
        "doctype_event": doctype_event,
        "reference_doctype": reference_doctype,
        "diagnostics": _dedupe(diagnostics),
        "blocking": False,
        "executed": False,
    }


def validate_script_payload(values: dict[str, Any], current=None):
    script = values.get("script")
    if script is None and current is not None:
        script = current.get("script")
    script_type = values.get("script_type") or (current and current.get("script_type")) or "DocType Event"
    return validate_server_script(
        script=script or "",
        script_type=script_type,
        doctype_event=values.get("doctype_event") or (current and current.get("doctype_event")),
        reference_doctype=values.get("reference_doctype") or (current and current.get("reference_doctype")),
    )


def _static_diagnostics(script: str, script_type: str):
    diagnostics = []
    try:
        tree = ast.parse(script)
    except SyntaxError:
        return diagnostics
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            diagnostics.append(_diagnostic("error", "imports_unavailable", node, "Imports are unavailable in Server Scripts."))
        elif isinstance(node, ast.AugAssign):
            diagnostics.append(_diagnostic("warning", "augmented_assignment", node, "Augmented assignment can require unavailable RestrictedPython inplace guards; prefer explicit assignment."))
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            diagnostics.append(_diagnostic("error", "private_attribute", node, "Private and underscore attributes are unavailable."))
        elif isinstance(node, ast.Call):
            path = _call_path(node.func)
            if path in {"frappe.db.commit", "frappe.db.rollback", "frappe.db.add_index"} and script_type == "DocType Event":
                diagnostics.append(_diagnostic("error", "transaction_unavailable", node, f"{path} is removed from DocType Event scripts."))
            if path in {"frappe.db.set_value", "doc.db_set"}:
                diagnostics.append(_diagnostic("warning", "direct_database_write", node, f"{path} bypasses some normal document lifecycle behavior."))
                if any(keyword.arg == "update_modified" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False for keyword in node.keywords):
                    diagnostics.append(_diagnostic("warning", "modified_timestamp_bypass", node, "update_modified=False suppresses the normal modified timestamp and audit signal."))
            if path in {"doc.save", "doc.insert"} and script_type == "DocType Event":
                diagnostics.append(_diagnostic("warning", "recursive_document_write", node, f"{path} inside a document event can recursively trigger the same script."))
    return diagnostics


def _diagnostic(severity, code, node, message):
    return {"severity": severity, "code": code, "line": getattr(node, "lineno", None), "message": message}


def _call_path(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _dedupe(diagnostics):
    seen = set()
    result = []
    for diagnostic in diagnostics:
        key = (diagnostic.get("code"), diagnostic.get("line"), diagnostic.get("message"))
        if key not in seen:
            seen.add(key)
            result.append(diagnostic)
    return result
