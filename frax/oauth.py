import json

import frappe
from frappe.oauth import get_server_url
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response


MCP_METHOD = "frax.mcp.handle_mcp"
MCP_PATH = f"/api/method/{MCP_METHOD}"
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"
AUTHORIZATION_SERVER_PATH = "/.well-known/oauth-authorization-server"
AUTHORIZE_PATH = "/authorize"
TOKEN_PATH = "/token"


class OAuthCompatibilityPage(BaseRenderer):
    """Serve OAuth discovery routes missing from Frappe v15."""

    def can_render(self):
        if _frappe_has_oauth_metadata_routes():
            return False

        return _request_path() in {
            PROTECTED_RESOURCE_PATH,
            AUTHORIZATION_SERVER_PATH,
            AUTHORIZE_PATH,
            TOKEN_PATH,
        }

    def render(self):
        path = _request_path()

        if path == PROTECTED_RESOURCE_PATH:
            return _json_response(protected_resource_metadata())

        if path == AUTHORIZATION_SERVER_PATH:
            return _json_response(authorization_server_metadata())

        if path == AUTHORIZE_PATH:
            return _redirect_to(
                "/api/method/frappe.integrations.oauth2.authorize",
                frappe.local.request.query_string,
            )

        if path == TOKEN_PATH:
            return _redirect_to(
                "/api/method/frappe.integrations.oauth2.get_token",
                frappe.local.request.query_string,
            )

        return Response(status=404)


def after_request(response=None, request=None):
    if not response or not request:
        return

    compatibility_paths = set()
    if not _frappe_has_oauth_metadata_routes():
        compatibility_paths = {
            PROTECTED_RESOURCE_PATH,
            AUTHORIZATION_SERVER_PATH,
            AUTHORIZE_PATH,
            TOKEN_PATH,
        }

    if request.path in {MCP_PATH, *compatibility_paths}:
        _set_cors_headers(response)

    if (
        not _frappe_has_oauth_metadata_routes()
        and response.status_code in {401, 403}
        and request.path == MCP_PATH
    ):
        response.headers["WWW-Authenticate"] = (
            'Bearer resource_metadata="'
            f'{get_server_url()}{PROTECTED_RESOURCE_PATH}"'
        )


@frappe.whitelist(allow_guest=True, methods=["GET"])
def protected_resource():
    return protected_resource_metadata()


@frappe.whitelist(allow_guest=True, methods=["GET"])
def authorization_server():
    return authorization_server_metadata()


def protected_resource_metadata():
    server_url = get_server_url()
    return {
        "resource": f"{server_url}{MCP_PATH}",
        "authorization_servers": [server_url],
        "scopes_supported": ["all", "openid"],
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{server_url}{MCP_PATH}",
    }


def authorization_server_metadata():
    server_url = get_server_url()
    return {
        "issuer": server_url,
        "authorization_endpoint": f"{server_url}/api/method/frappe.integrations.oauth2.authorize",
        "token_endpoint": f"{server_url}/api/method/frappe.integrations.oauth2.get_token",
        "userinfo_endpoint": f"{server_url}/api/method/frappe.integrations.oauth2.openid_profile",
        "revocation_endpoint": f"{server_url}/api/method/frappe.integrations.oauth2.revoke_token",
        "introspection_endpoint": f"{server_url}/api/method/frappe.integrations.oauth2.introspect_token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "none",
        ],
        "scopes_supported": ["all", "openid"],
    }


def _request_path():
    return frappe.local.request.path.rstrip("/") or "/"


def _frappe_has_oauth_metadata_routes():
    version = getattr(frappe, "__version__", "0").split("-", 1)[0]
    try:
        major = int(version.split(".", 1)[0])
    except (TypeError, ValueError):
        return False

    return major >= 16


def _json_response(data):
    response = Response(
        json.dumps(data, separators=(",", ":")),
        content_type="application/json",
    )
    _set_cors_headers(response)
    return response


def _redirect_to(path, query_string):
    location = path
    if query_string:
        location = f"{path}?{frappe.safe_decode(query_string)}"

    response = Response(status=302)
    response.headers["Location"] = location
    response.headers["Cache-Control"] = "no-store"
    _set_cors_headers(response)
    return response


def _set_cors_headers(response):
    origin = frappe.get_request_header("Origin") or "*"
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Authorization, Content-Type, MCP-Protocol-Version, Mcp-Session-Id"
    )
    response.headers["Access-Control-Expose-Headers"] = (
        "WWW-Authenticate, MCP-Protocol-Version, Mcp-Session-Id"
    )
    response.headers["Access-Control-Max-Age"] = "86400"
