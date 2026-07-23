from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, Literal, TypedDict

from frappe_mcp.server.tools import ToolAnnotations

from frax.mcp import mcp

Risk = Literal["read", "sensitive_read", "write", "destructive", "admin"]


class ToolPolicy(TypedDict):
    risk: Risk
    requires_confirmation: bool
    roles: list[str] | None


tool_policies: dict[str, ToolPolicy] = {}


def annotations_for(
    risk: Risk,
    *,
    idempotent: bool = False,
    open_world: bool = False,
    title: str | None = None,
) -> ToolAnnotations:
    return {
        "title": title,
        "readOnlyHint": risk in ("read", "sensitive_read"),
        "destructiveHint": risk in ("destructive", "admin"),
        "idempotentHint": idempotent,
        "openWorldHint": open_world,
    }


def frax_tool(
    *,
    name: str,
    risk: Risk,
    requires_confirmation: bool = False,
    roles: list[str] | None = None,
    annotations: ToolAnnotations | None = None,
    input_schema: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_policies[name] = {
            "risk": risk,
            "requires_confirmation": requires_confirmation,
            "roles": roles,
        }

        @wraps(fn)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            if roles:
                import frappe

                if frappe.session.user != "Administrator" and not any(frappe.has_role(role) for role in roles):
                    frappe.throw(
                        f"Tool {name} requires one of these roles: {', '.join(roles)}.",
                        frappe.PermissionError,
                    )
            return fn(*args, **kwargs)

        return mcp.tool(
            name=name,
            input_schema=input_schema,
            annotations=annotations or annotations_for(risk),
        )(guarded)

    return decorator


def get_tool_policies() -> dict[str, ToolPolicy]:
    return tool_policies.copy()
