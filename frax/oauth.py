import ipaddress
import json
import time
from urllib.parse import urlsplit

import frappe
from frappe.oauth import get_server_url
from frappe.rate_limiter import rate_limit
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

from frax.setup import get_settings_state


MCP_METHOD = "frax.mcp.handle_mcp"
MCP_PATH = f"/api/method/{MCP_METHOD}"
PROTECTED_RESOURCE_PATH = "/.well-known/oauth-protected-resource"
AUTHORIZATION_SERVER_PATH = "/.well-known/oauth-authorization-server"
AUTHORIZE_PATH = "/authorize"
TOKEN_PATH = "/token"
REGISTRATION_METHOD = "frax.oauth.register_client"
REGISTRATION_PATH = f"/api/method/{REGISTRATION_METHOD}"


class OAuthCompatibilityPage(BaseRenderer):
    """Serve OAuth discovery routes missing from Frappe v15."""

    def can_render(self):
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

    if request.path in {
        PROTECTED_RESOURCE_PATH,
        AUTHORIZATION_SERVER_PATH,
        MCP_PATH,
        AUTHORIZE_PATH,
        TOKEN_PATH,
        REGISTRATION_PATH,
    }:
        _set_cors_headers(response)

    if response.status_code in {401, 403} and request.path == MCP_PATH:
        response.headers["WWW-Authenticate"] = (
            f'Bearer resource_metadata="{get_server_url()}{PROTECTED_RESOURCE_PATH}"'
        )

    if request.path.startswith("/api/method/frax.setup."):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"


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
        "registration_endpoint": f"{server_url}{REGISTRATION_PATH}",
        "userinfo_endpoint": f"{server_url}/api/method/frappe.integrations.oauth2.openid_profile",
        "revocation_endpoint": f"{server_url}/api/method/frappe.integrations.oauth2.revoke_token",
        "introspection_endpoint": f"{server_url}/api/method/frappe.integrations.oauth2.introspect_token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
        "scopes_supported": ["all", "openid"],
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=60 * 60)
def register_client():
    """Register an OAuth client using the RFC 7591 metadata shape."""
    settings = get_settings_state()
    if not settings.enabled or not settings.oauth_enabled:
        return _registration_error(
            "access_denied", "OAuth registration is disabled", 403
        )

    data = frappe.request.get_json(silent=True)
    try:
        metadata = _validate_client_metadata(data)
    except ValueError as error:
        return _registration_error("invalid_client_metadata", str(error), 400)

    client = frappe.get_doc(
        {
            "doctype": "OAuth Client",
            "app_name": metadata["client_name"],
            "scopes": metadata["scope"],
            "redirect_uris": "\n".join(metadata["redirect_uris"]),
            "default_redirect_uri": metadata["redirect_uris"][0],
            "grant_type": "Authorization Code",
            "response_type": "Code",
            "skip_authorization": 0,
            "client_secret": frappe.generate_hash(length=32),
        }
    ).insert(ignore_permissions=True)

    response_data = {
        "client_id": client.client_id,
        "client_id_issued_at": int(time.time()),
        "client_secret_expires_at": 0,
        **metadata,
    }
    response_data["client_secret"] = client.client_secret
    return _json_response(response_data, status=201)


def _validate_client_metadata(data):
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")

    redirects = data.get("redirect_uris")
    if not isinstance(redirects, list) or not redirects:
        raise ValueError("redirect_uris must contain at least one URI")
    if len(redirects) > 10 or any(not isinstance(uri, str) for uri in redirects):
        raise ValueError("redirect_uris must contain at most 10 URI strings")
    if len(set(redirects)) != len(redirects):
        raise ValueError("redirect_uris must not contain duplicates")
    if any(not _is_secure_redirect_uri(uri) for uri in redirects):
        raise ValueError("redirect_uris must use HTTPS or HTTP on a loopback host")

    grant_types = data.get("grant_types") or ["authorization_code"]
    if not isinstance(grant_types, list) or not set(grant_types).issubset(
        {"authorization_code", "refresh_token"}
    ):
        raise ValueError(
            "only authorization_code and refresh_token grants are supported"
        )
    response_types = data.get("response_types") or ["code"]
    if response_types != ["code"]:
        raise ValueError("only the code response type is supported")

    auth_method = data.get("token_endpoint_auth_method") or "client_secret_basic"
    if auth_method not in {"none", "client_secret_basic", "client_secret_post"}:
        raise ValueError("unsupported token_endpoint_auth_method")
    # Frappe v15 requires client authentication at its token endpoint. Accept a
    # public-client registration request, then transparently issue credentials.
    if auth_method == "none":
        auth_method = "client_secret_basic"

    requested_scopes = (data.get("scope") or "all openid").split()
    if not requested_scopes or not set(requested_scopes).issubset({"all", "openid"}):
        raise ValueError("only all and openid scopes are supported")

    client_name = str(data.get("client_name") or "MCP Client").strip()
    if not client_name or len(client_name) > 140:
        raise ValueError("client_name must be between 1 and 140 characters")

    return {
        "client_name": client_name,
        "redirect_uris": redirects,
        "token_endpoint_auth_method": auth_method,
        "grant_types": grant_types,
        "response_types": response_types,
        "scope": " ".join(dict.fromkeys(requested_scopes)),
    }


def _is_secure_redirect_uri(uri):
    try:
        parsed = urlsplit(uri)
        if parsed.fragment or parsed.username or parsed.password or not parsed.hostname:
            return False
        if parsed.scheme == "https":
            return True
        if parsed.scheme != "http":
            return False
        if parsed.hostname.lower() == "localhost":
            return True
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except (ValueError, TypeError):
        return False


def _request_path():
    request = getattr(frappe.local, "request", None)
    path = getattr(request, "path", "")
    return path.rstrip("/") or "/"


def _json_response(data, status=200):
    response = Response(
        json.dumps(data, separators=(",", ":")),
        status=status,
        content_type="application/json",
    )
    _set_cors_headers(response)
    return response


def _registration_error(error, description, status):
    return _json_response(
        {"error": error, "error_description": description}, status=status
    )


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
        "Authorization, Content-Type, MCP-Protocol-Version, Mcp-Session-Id, X-Frappe-CSRF-Token"
    )
    response.headers["Access-Control-Expose-Headers"] = (
        "WWW-Authenticate, MCP-Protocol-Version, Mcp-Session-Id"
    )
    response.headers["Access-Control-Max-Age"] = "86400"
