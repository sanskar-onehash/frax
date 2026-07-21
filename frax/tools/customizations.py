from __future__ import annotations

from typing import Any

import frappe

from frax.tools.registry import frax_tool


def register():
    return None


@frax_tool(name="frax_list_client_scripts", risk="admin", requires_confirmation=True, roles=["System Manager"])
def list_client_scripts(doctype: str | None = None, enabled: bool | None = None):
    """List Client Script records.

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


@frax_tool(name="frax_get_client_script", risk="admin", requires_confirmation=True, roles=["System Manager"])
def get_client_script(name: str):
    """Get a Client Script document.

    Args:
        name: Client Script name.
    """
    return frappe.get_doc("Client Script", name).as_dict()


@frax_tool(name="frax_create_client_script", risk="admin", requires_confirmation=True, roles=["System Manager"])
def create_client_script(doc: dict[str, Any]):
    """Create a Client Script document.

    Args:
        doc: Client Script fields. doctype is optional and will be set to Client Script.
    """
    doc = {**doc, "doctype": "Client Script"}
    return frappe.get_doc(doc).insert().as_dict()


@frax_tool(name="frax_update_client_script", risk="admin", requires_confirmation=True, roles=["System Manager"])
def update_client_script(name: str, values: dict[str, Any]):
    """Update a Client Script document.

    Args:
        name: Client Script name.
        values: Field values to update.
    """
    doc = frappe.get_doc("Client Script", name)
    doc.update(values)
    doc.save()
    return doc.as_dict()


@frax_tool(name="frax_disable_client_script", risk="admin", requires_confirmation=True, roles=["System Manager"])
def disable_client_script(name: str):
    """Disable a Client Script document.

    Args:
        name: Client Script name.
    """
    doc = frappe.get_doc("Client Script", name)
    doc.enabled = 0
    doc.save()
    return doc.as_dict()


@frax_tool(name="frax_list_server_scripts", risk="admin", requires_confirmation=True, roles=["System Manager"])
def list_server_scripts(script_type: str | None = None, disabled: bool | None = None):
    """List Server Script records.

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


@frax_tool(name="frax_get_server_script", risk="admin", requires_confirmation=True, roles=["System Manager"])
def get_server_script(name: str):
    """Get a Server Script document.

    Args:
        name: Server Script name.
    """
    return frappe.get_doc("Server Script", name).as_dict()


@frax_tool(name="frax_create_server_script", risk="admin", requires_confirmation=True, roles=["System Manager"])
def create_server_script(doc: dict[str, Any]):
    """Create a Server Script document.

    Args:
        doc: Server Script fields. doctype is optional and will be set to Server Script.
    """
    doc = {**doc, "doctype": "Server Script"}
    return frappe.get_doc(doc).insert().as_dict()


@frax_tool(name="frax_update_server_script", risk="admin", requires_confirmation=True, roles=["System Manager"])
def update_server_script(name: str, values: dict[str, Any]):
    """Update a Server Script document.

    Args:
        name: Server Script name.
        values: Field values to update.
    """
    doc = frappe.get_doc("Server Script", name)
    doc.update(values)
    doc.save()
    return doc.as_dict()


@frax_tool(name="frax_disable_server_script", risk="admin", requires_confirmation=True, roles=["System Manager"])
def disable_server_script(name: str):
    """Disable a Server Script document.

    Args:
        name: Server Script name.
    """
    doc = frappe.get_doc("Server Script", name)
    doc.disabled = 1
    doc.save()
    return doc.as_dict()
