import frappe
from frappe.auth import validate_api_key_secret


def validate_mcp_bearer_api_key():
    """Allow Codex MCP bearer-token config to carry Frappe API key credentials."""
    if frappe.session.user not in ("", "Guest"):
        return

    if frappe.request.path != "/api/method/frax.mcp.handle_mcp":
        return

    authorization_header = frappe.get_request_header("Authorization", "").split(" ", 1)
    if len(authorization_header) != 2:
        return

    auth_type, auth_token = authorization_header
    if auth_type.lower() != "bearer" or ":" not in auth_token:
        return

    api_key, api_secret = auth_token.split(":", 1)
    validate_api_key_secret(api_key, api_secret)
