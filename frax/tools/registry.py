from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from inspect import signature
from difflib import get_close_matches
from time import monotonic
from typing import Any, Literal, TypedDict

from frappe_mcp.server.tools import ToolAnnotations

from frax.mcp import mcp

Risk = Literal["read", "sensitive_read", "write", "destructive", "admin"]


class ToolPolicy(TypedDict):
    risk: Risk
    requires_confirmation: bool
    roles: list[str] | None
    category: str


tool_policies: dict[str, ToolPolicy] = {}

CATEGORY_SETTINGS = {
    "core": "enable_core_tools",
    "context": "enable_context_tools",
    "customization": "enable_customization_tools",
    "reporting": "enable_reporting_tools",
    "erpnext": "enable_business_tools",
}


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
    category: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        resolved_category = category or _category_from_module(fn.__module__)
        tool_policies[name] = {
            "risk": risk,
            "requires_confirmation": requires_confirmation,
            "roles": roles,
            "category": resolved_category,
        }

        @wraps(fn)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            import frappe

            _validate_arguments(fn, kwargs)
            _require_category(resolved_category)
            if roles:
                if frappe.session.user != "Administrator" and not any(
                    role in frappe.get_roles() for role in roles
                ):
                    frappe.throw(
                        f"Tool {name} requires one of these roles: {', '.join(roles)}.",
                        frappe.PermissionError,
                    )
            started = monotonic()
            error = None
            result = None
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as exc:
                error = exc
                raise
            finally:
                from frax.audit import log_tool_call

                log_tool_call(
                    tool_name=name,
                    category=resolved_category,
                    risk=risk,
                    arguments=kwargs,
                    outcome="error" if error else "success",
                    duration_ms=round((monotonic() - started) * 1000),
                    result=result,
                    error=error,
                )

        return mcp.tool(
            name=name,
            input_schema=input_schema,
            annotations=annotations or annotations_for(risk),
        )(guarded)

    return decorator


def get_tool_policies() -> dict[str, ToolPolicy]:
    return tool_policies.copy()


def enabled_categories() -> set[str]:
    from frax.setup import get_settings_state

    settings = get_settings_state()
    categories = {
        category
        for category, fieldname in CATEGORY_SETTINGS.items()
        if settings.get(fieldname)
    }
    if "erpnext" in categories:
        categories.update(
            {"erpnext_selling", "erpnext_buying", "erpnext_stock", "erpnext_accounts"}
        )
    return categories


def tool_is_available(tool_name: str) -> bool:
    policy = tool_policies.get(tool_name)
    if not policy:
        return True
    category = policy["category"]
    if category not in enabled_categories():
        return False
    if category == "erpnext" or category.startswith("erpnext_"):
        import frappe

        return "erpnext" in frappe.get_installed_apps()
    return True


def _require_category(category: str):
    import frappe

    if category not in enabled_categories():
        frappe.throw(f"Frax MCP tool category '{category}' is disabled.", frappe.PermissionError)
    if (category == "erpnext" or category.startswith("erpnext_")) and "erpnext" not in frappe.get_installed_apps():
        frappe.throw("ERPNext is not installed on this site.", frappe.DoesNotExistError)


def _validate_arguments(fn: Callable[..., Any], arguments: dict[str, Any]):
    import frappe

    parameters = signature(fn).parameters
    if any(parameter.kind == parameter.VAR_KEYWORD for parameter in parameters.values()):
        return
    unknown = sorted(set(arguments) - set(parameters))
    if not unknown:
        return
    details = []
    for key in unknown:
        matches = get_close_matches(key, parameters, n=1)
        details.append(f"{key} (use {matches[0]})" if matches else key)
    frappe.throw(
        "Unexpected tool argument(s): " + ", ".join(details),
        frappe.ValidationError,
    )


def _category_from_module(module: str) -> str:
    leaf = module.rsplit(".", 1)[-1]
    return {
        "context": "context",
        "capabilities": "context",
        "customizations": "customization",
        "reporting": "reporting",
        "scripting": "customization",
        "erpnext": "erpnext",
    }.get(leaf, "core")
