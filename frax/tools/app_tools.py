from __future__ import annotations

from typing import Any

import frappe

from frax.tools.registry import frax_tool


def register():
    return None


@frax_tool(name="frax_list_app_frax_tools", risk="read")
def list_app_frax_tools(app_name: str):
    """List executable tools declared by an app through the frax_tools hook.

    Args:
        app_name: Installed app name.
    """
    return frappe.get_hooks("frax_tools", app_name=app_name)


@frax_tool(name="frax_call_app_tool", risk="write", requires_confirmation=True)
def call_app_tool(app_name: str, tool: str, args: dict[str, Any] | None = None):
    """Call an app tool explicitly declared in the app's frax_tools hook.

    Args:
        app_name: Installed app that declares the tool.
        tool: Dotted Python path declared in frax_tools.
        args: Keyword arguments to pass to the tool.
    """
    app_hooks = frappe.get_hooks("frax_tools", app_name=app_name)

    if tool not in app_hooks:
        frappe.throw("Tool not found in the app.")

    fn = frappe.get_attr(tool)
    frappe.is_whitelisted(fn)
    return fn(**(args or {}))
