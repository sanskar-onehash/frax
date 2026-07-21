from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypedDict

from frappe_mcp.server.tools import ToolAnnotations

from frax.mcp import mcp

Risk = Literal["read", "write", "destructive", "admin"]


class ToolPolicy(TypedDict):
    risk: Risk
    requires_confirmation: bool
    roles: list[str] | None


tool_policies: dict[str, ToolPolicy] = {}


def annotations_for(risk: Risk, *, idempotent: bool = False, open_world: bool = False) -> ToolAnnotations:
    return {
        "readOnlyHint": risk == "read",
        "destructiveHint": risk == "destructive",
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
        return mcp.tool(
            name=name,
            input_schema=input_schema,
            annotations=annotations or annotations_for(risk),
        )(fn)

    return decorator


def get_tool_policies() -> dict[str, ToolPolicy]:
    return tool_policies.copy()
