import json

from werkzeug import Response

import frappe
import frappe_mcp
from frappe import _
from frappe.exceptions import SessionStopped

from frax.context import OPERATOR_CONTEXT
from frax.setup import get_settings_state, require_mcp_access

mcp = frappe_mcp.MCP(name="frax", instructions=OPERATOR_CONTEXT)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle_mcp():
    from frax.branding import brand_mcp_response, branded_operator_context, get_branding
    from frax import prompts
    from frax.tools import register_all_tools

    settings = get_settings_state()
    branding = get_branding()
    if not settings.enabled:
        frappe.throw(
            _("{0} connection service is currently disabled.").format(
                branding.product_name
            ),
            SessionStopped,
        )

    require_mcp_access()
    auth_method = _request_auth_method()
    if auth_method == "oauth" and not settings.oauth_enabled:
        frappe.throw(
            _("OAuth authentication is disabled for this connection service."),
            frappe.PermissionError,
        )
    if auth_method == "api_token" and not settings.api_token_enabled:
        frappe.throw(
            _("API token authentication is disabled for this connection service."),
            frappe.PermissionError,
        )

    prompts.register()
    register_all_tools()
    mcp._instructions = branded_operator_context(OPERATOR_CONTEXT)
    request_payload = frappe.request.get_json(silent=True) or {}
    from frax.mcp_apps import augment_response, handle_resource_request

    resource_response = handle_resource_request(request_payload)
    if resource_response is not None:
        return resource_response
    response = mcp.handle(frappe.request, Response())
    response = augment_response(_filter_tools_response(response), request_payload)
    return brand_mcp_response(response, request_payload)


def _request_auth_method():
    authorization = frappe.get_request_header("Authorization", "").split(" ", 1)
    if len(authorization) != 2:
        return "session"

    scheme, token = authorization
    if scheme.lower() in {"bearer", "token"} and ":" in token:
        return "api_token"
    if scheme.lower() == "bearer":
        return "oauth"
    return "session"


def _filter_tools_response(response):
    """Apply per-site visibility after frappe-mcp builds tools/list.

    Runtime guards enforce the same policy for tools/call, so a stale client cannot
    invoke a disabled or unavailable category.
    """
    try:
        payload = json.loads(response.get_data(as_text=True))
        tools = payload.get("result", {}).get("tools")
        if not isinstance(tools, list):
            return response
        from frax.tools.registry import tool_is_available

        payload["result"]["tools"] = [
            tool for tool in tools if tool_is_available(tool.get("name", ""))
        ]
        response.set_data(json.dumps(payload, separators=(",", ":")))
    except Exception:
        frappe.log_error(title="Frax tools/list filtering failed")
    return response
