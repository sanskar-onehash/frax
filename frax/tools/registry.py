from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from difflib import get_close_matches
from functools import wraps
from inspect import Parameter, signature
from time import monotonic
from types import UnionType
from typing import Any, Literal, TypedDict, Union, get_args, get_origin, get_type_hints

from frappe_mcp.server.tools import ToolAnnotations, get_tool
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

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
    "business": "enable_business_tools",
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
        resolved_schema = _resolve_input_schema(fn, input_schema)
        tool_policies[name] = {
            "risk": risk,
            "requires_confirmation": requires_confirmation,
            "roles": roles,
            "category": resolved_category,
        }

        @wraps(fn)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            import frappe

            _validate_arguments(fn, kwargs, resolved_schema)
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
            input_schema=resolved_schema,
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
    if "business" in categories:
        categories.update(
            {
                "business_selling",
                "business_buying",
                "business_stock",
                "business_accounts",
            }
        )
    return categories


def tool_is_available(tool_name: str) -> bool:
    policy = tool_policies.get(tool_name)
    if not policy:
        return True
    category = policy["category"]
    if category not in enabled_categories():
        return False
    if category == "business" or category.startswith("business_"):
        import frappe

        return "erpnext" in frappe.get_installed_apps()
    return True


def _require_category(category: str):
    import frappe

    if category not in enabled_categories():
        frappe.throw(
            f"Frax MCP tool category '{category}' is disabled.", frappe.PermissionError
        )
    if (
        category == "business" or category.startswith("business_")
    ) and "erpnext" not in frappe.get_installed_apps():
        frappe.throw(
            "The business application is not installed on this site.",
            frappe.DoesNotExistError,
        )


def _resolve_input_schema(
    fn: Callable[..., Any], input_schema: dict[str, Any] | None = None
) -> dict[str, Any]:
    schema = deepcopy(get_tool(fn, {"input_schema": input_schema})["input_schema"])
    parameters = signature(fn).parameters
    if not any(
        parameter.kind == Parameter.VAR_KEYWORD for parameter in parameters.values()
    ):
        schema.setdefault("additionalProperties", False)

    try:
        type_hints = get_type_hints(fn)
    except (NameError, TypeError):
        type_hints = {}
    properties = schema.get("properties", {})
    for key, annotation in type_hints.items():
        if key in properties:
            properties[key] = _add_literal_constraints(properties[key], annotation)
    return schema


def _add_literal_constraints(schema: dict[str, Any], annotation: Any) -> dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is Literal:
        constrained = deepcopy(schema)
        constrained["enum"] = list(args)
        return constrained
    if origin in (Union, UnionType):
        alternatives = schema.get("anyOf")
        if isinstance(alternatives, list) and len(alternatives) == len(args):
            constrained = deepcopy(schema)
            constrained["anyOf"] = [
                _add_literal_constraints(item, arg)
                for item, arg in zip(alternatives, args, strict=True)
            ]
            return constrained
    if origin is list and args and isinstance(schema.get("items"), dict):
        constrained = deepcopy(schema)
        constrained["items"] = _add_literal_constraints(schema["items"], args[0])
        return constrained
    if (
        origin is dict
        and len(args) == 2
        and isinstance(schema.get("additionalProperties"), dict)
    ):
        constrained = deepcopy(schema)
        constrained["additionalProperties"] = _add_literal_constraints(
            schema["additionalProperties"], args[1]
        )
        return constrained
    return schema


def _validate_arguments(
    fn: Callable[..., Any],
    arguments: dict[str, Any],
    input_schema: dict[str, Any] | None = None,
):
    import frappe

    parameters = signature(fn).parameters
    if not any(
        parameter.kind == Parameter.VAR_KEYWORD for parameter in parameters.values()
    ):
        unknown = sorted(set(arguments) - set(parameters))
        if unknown:
            details = []
            for key in unknown:
                matches = get_close_matches(key, parameters, n=1)
                details.append(f"{key} (use {matches[0]})" if matches else key)
            frappe.throw(
                "Unexpected tool argument(s): " + ", ".join(details),
                frappe.ValidationError,
            )

    schema = input_schema or _resolve_input_schema(fn)
    error = best_match(Draft202012Validator(schema).iter_errors(arguments))
    if not error:
        return
    location = ".".join(str(part) for part in error.absolute_path)
    subject = f"argument '{location}'" if location else "tool arguments"
    frappe.throw(
        f"Invalid {subject}: {error.message}",
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
        "erpnext": "business",
    }.get(leaf, "core")
