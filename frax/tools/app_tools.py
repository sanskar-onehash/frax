from __future__ import annotations

from typing import Any

import frappe

from frax.tools.registry import annotations_for, frax_tool


def register():
    return None


@frax_tool(
    name="frax_list_app_frax_tools",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List App Frax Tools"),
)
def list_app_frax_tools(app_name: str):
    """List dotted Python methods an installed app exposes through the frax_tools hook.

    Use this to discover app-declared extension tools. Listing is read-only; calling
    a declared tool is separate and may mutate data depending on the app method.

    Args:
        app_name: Installed app name.
    """
    return frappe.get_hooks("frax_tools", app_name=app_name)


@frax_tool(
    name="frax_call_app_tool",
    risk="destructive",
    requires_confirmation=True,
    annotations=annotations_for("destructive", open_world=True, title="Call App Frax Tool"),
)
def call_app_tool(app_name: str, tool: str, args: dict[str, Any] | None = None):
    """Call an app tool explicitly declared in that app's frax_tools hook.

    Destructive-risk delegation point. Frax verifies the dotted method is declared by the
    app and whitelisted, but the app method defines its own behavior and may mutate
    records, call integrations, send notifications, or have domain-specific side effects.
    Inspect the method source/docstring and ask for confirmation before calling.

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
