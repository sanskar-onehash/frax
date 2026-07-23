from __future__ import annotations

from typing import Any

import frappe

from frax.tools.registry import annotations_for, frax_tool


def register():
    return None


@frax_tool(
    name="frax_list_client_scripts",
    risk="sensitive_read",
    roles=["System Manager"],
    annotations=annotations_for("sensitive_read", idempotent=True, title="List Client Scripts"),
)
def list_client_scripts(doctype: str | None = None, enabled: bool | None = None):
    """List Client Script records without returning script code.

    Sensitive read for System Manager because Client Scripts can expose business logic,
    UI assumptions, role checks, and RPC calls. Use before changing form/list behavior.

    Args:
        doctype: Optional target DocType filter.
        enabled: Optional enabled flag filter.
    """
    filters = {}
    if doctype:
        filters["dt"] = doctype
    if enabled is not None:
        filters["enabled"] = int(enabled)

    return frappe.get_all(
        "Client Script",
        filters=filters,
        fields=["name", "dt", "view", "enabled", "modified"],
        order_by="modified desc",
    )


@frax_tool(
    name="frax_get_client_script",
    risk="sensitive_read",
    requires_confirmation=True,
    roles=["System Manager"],
    annotations=annotations_for("sensitive_read", idempotent=True, title="Get Client Script"),
)
def get_client_script(name: str):
    """Get one Client Script document including script code.

    Sensitive read for System Manager. Prefer list/summaries first; retrieve full code
    only when needed to debug or modify exact client-side behavior.

    Args:
        name: Client Script name.
    """
    return frappe.get_doc("Client Script", name).as_dict()


@frax_tool(
    name="frax_create_client_script",
    risk="admin",
    requires_confirmation=True,
    roles=["System Manager"],
    annotations=annotations_for("admin", title="Create Client Script"),
)
def create_client_script(doc: dict[str, Any]):
    """Create a Client Script document.

    Admin write. Prefer app JS for durable product behavior. Before creating, inspect
    DocType metadata, existing Client Scripts, Server Scripts, workflows, permissions,
    and settings so UI behavior does not conflict with server-side rules.

    Args:
        doc: Client Script fields. doctype is optional and will be set to Client Script.
    """
    doc = {**doc, "doctype": "Client Script"}
    return frappe.get_doc(doc).insert().as_dict()


@frax_tool(
    name="frax_update_client_script",
    risk="admin",
    requires_confirmation=True,
    roles=["System Manager"],
    annotations=annotations_for("admin", title="Update Client Script"),
)
def update_client_script(name: str, values: dict[str, Any]):
    """Update a Client Script document.

    Admin write. Inspect current code and related server-side behavior first. Client
    Scripts are UI behavior, not enforcement.

    Args:
        name: Client Script name.
        values: Field values to update.
    """
    doc = frappe.get_doc("Client Script", name)
    doc.update(values)
    doc.save()
    return doc.as_dict()


@frax_tool(
    name="frax_disable_client_script",
    risk="admin",
    requires_confirmation=True,
    roles=["System Manager"],
    annotations=annotations_for("admin", title="Disable Client Script"),
)
def disable_client_script(name: str):
    """Disable a Client Script document.

    Admin write. Confirm dependent form/list behavior and server-side enforcement before disabling.

    Args:
        name: Client Script name.
    """
    doc = frappe.get_doc("Client Script", name)
    doc.enabled = 0
    doc.save()
    return doc.as_dict()


@frax_tool(
    name="frax_list_server_scripts",
    risk="sensitive_read",
    roles=["System Manager"],
    annotations=annotations_for("sensitive_read", idempotent=True, title="List Server Scripts"),
)
def list_server_scripts(script_type: str | None = None, disabled: bool | None = None):
    """List Server Script records without returning script code.

    Sensitive read for System Manager. Server Scripts can alter permissions, workflows,
    API behavior, jobs, document events, integrations, and naming/status logic.

    Args:
        script_type: Optional script type filter.
        disabled: Optional disabled flag filter.
    """
    filters = {}
    if script_type:
        filters["script_type"] = script_type
    if disabled is not None:
        filters["disabled"] = int(disabled)

    return frappe.get_all(
        "Server Script",
        filters=filters,
        fields=["name", "script_type", "reference_doctype", "disabled", "modified"],
        order_by="modified desc",
    )


@frax_tool(
    name="frax_get_script_risk_summary",
    risk="sensitive_read",
    roles=["System Manager"],
    annotations=annotations_for("sensitive_read", idempotent=True, title="Get Script Risk Summary"),
)
def get_script_risk_summary(doctype: str | None = None, include_client_scripts: bool = True, include_server_scripts: bool = True):
    """Summarize Client Script and Server Script risk signals without returning code.

    Sensitive read for System Manager. Use before retrieving full scripts or changing
    DocType behavior. Returns names, trigger surfaces, enabled/disabled state, and
    heuristic risk signals such as mutation, external calls, permission bypass, RPC,
    naming/status, amount math, and restricted-Python caveats.

    Args:
        doctype: Optional target DocType. Checks Client Script dt and Server Script reference_doctype.
        include_client_scripts: Include Client Script summaries.
        include_server_scripts: Include Server Script summaries.
    """
    result: dict[str, Any] = {"doctype": doctype, "client_scripts": [], "server_scripts": []}

    if include_client_scripts:
        filters = {"dt": doctype} if doctype else {}
        for row in frappe.get_all(
            "Client Script",
            filters=filters,
            fields=["name", "dt", "view", "enabled", "script", "modified"],
            order_by="modified desc",
        ):
            script = row.pop("script") or ""
            result["client_scripts"].append(
                {
                    **row,
                    "risk_signals": _classify_client_script(script),
                }
            )

    if include_server_scripts:
        filters = {"reference_doctype": doctype} if doctype else {}
        for row in frappe.get_all(
            "Server Script",
            filters=filters,
            fields=[
                "name",
                "script_type",
                "reference_doctype",
                "doctype_event",
                "event_frequency",
                "disabled",
                "script",
                "modified",
            ],
            order_by="modified desc",
        ):
            script = row.pop("script") or ""
            result["server_scripts"].append(
                {
                    **row,
                    "risk_signals": _classify_server_script(script),
                    "restricted_python": True,
                }
            )

    return result


@frax_tool(
    name="frax_get_server_script",
    risk="sensitive_read",
    requires_confirmation=True,
    roles=["System Manager"],
    annotations=annotations_for("sensitive_read", idempotent=True, title="Get Server Script"),
)
def get_server_script(name: str):
    """Get one Server Script document including restricted Python code.

    Sensitive read for System Manager. Prefer list/summaries first; retrieve full code
    only when needed. Use frax_frappe_restricted_scripting before proposing changes.

    Args:
        name: Server Script name.
    """
    return frappe.get_doc("Server Script", name).as_dict()


@frax_tool(
    name="frax_create_server_script",
    risk="admin",
    requires_confirmation=True,
    roles=["System Manager"],
    annotations=annotations_for("admin", open_world=True, title="Create Server Script"),
)
def create_server_script(doc: dict[str, Any]):
    """Create a Server Script document.

    High-risk admin write. Server Scripts run restricted Python and may affect document
    events, scheduler, permission queries, API routes, or whitelisted endpoint behavior.
    Check settings, metadata, workflows, existing scripts/hooks, and restricted syntax first.

    Args:
        doc: Server Script fields. doctype is optional and will be set to Server Script.
    """
    doc = {**doc, "doctype": "Server Script"}
    return frappe.get_doc(doc).insert().as_dict()


@frax_tool(
    name="frax_update_server_script",
    risk="admin",
    requires_confirmation=True,
    roles=["System Manager"],
    annotations=annotations_for("admin", open_world=True, title="Update Server Script"),
)
def update_server_script(name: str, values: dict[str, Any]):
    """Update a Server Script document.

    High-risk admin write. Inspect current code, trigger type, target DocType, permissions,
    workflows, hooks, settings, and restricted Python constraints before updating.

    Args:
        name: Server Script name.
        values: Field values to update.
    """
    doc = frappe.get_doc("Server Script", name)
    doc.update(values)
    doc.save()
    return doc.as_dict()


@frax_tool(
    name="frax_disable_server_script",
    risk="admin",
    requires_confirmation=True,
    roles=["System Manager"],
    annotations=annotations_for("admin", title="Disable Server Script"),
)
def disable_server_script(name: str):
    """Disable a Server Script document.

    High-risk admin write. Confirm what document events, permission queries, API routes,
    scheduled jobs, integrations, or naming/status behavior depend on it.

    Args:
        name: Server Script name.
    """
    doc = frappe.get_doc("Server Script", name)
    doc.disabled = 1
    doc.save()
    return doc.as_dict()


def _classify_client_script(script: str) -> list[str]:
    lowered = script.lower()
    signals = []
    checks = {
        "rpc_call": ("frappe.call", "frappe.xcall", "frappe.db.get_value"),
        "field_mutation": ("set_value", "frm.set_value", "frappe.model.set_value"),
        "role_or_user_logic": ("has_role", "frappe.user", "user_roles", "session.user"),
        "workflow_or_status": ("workflow", "status", "docstatus"),
        "validation": ("frappe.throw", "frappe.validated", "validate"),
        "navigation_or_route": ("set_route", "route_options"),
    }
    for signal, needles in checks.items():
        if any(needle in lowered for needle in needles):
            signals.append(signal)
    return signals


def _classify_server_script(script: str) -> list[str]:
    lowered = script.lower()
    signals = []
    checks = {
        "record_mutation": (".insert(", ".save(", ".submit(", ".cancel(", "set_value", "delete_doc", "rename_doc"),
        "external_call": ("make_get_request", "make_post_request", "make_put_request", "make_patch_request", "make_delete_request"),
        "email_or_notification": ("sendmail", "notification", "email queue", "attach_print"),
        "permission_or_visibility": ("conditions", "permission", "ignore_permissions", "has_permission"),
        "workflow_or_status": ("workflow", "status", "docstatus"),
        "naming": ("autoname", "naming", "series", "rename_doc"),
        "amount_math": ("amount", "rate", "total", "percent", "discount", "concession", "tax"),
        "background_job": ("enqueue", "scheduled", "scheduler"),
        "restricted_python_caveat": ("import ", ".format(", ".format_map(", "+=", "-="),
    }
    for signal, needles in checks.items():
        if any(needle in lowered for needle in needles):
            signals.append(signal)
    return signals
