from __future__ import annotations

import base64
import hashlib
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urlsplit, urlunsplit

import frappe
from frappe import _
from frappe.oauth import get_server_url
from frappe.permissions import SYSTEM_USER_ROLE
from frappe.utils.password import check_password


SETTINGS_DOCTYPE = "Frax MCP Settings"
SETUP_PAGE = "frax-setup"
MCP_METHOD = "frax.mcp.handle_mcp"
DEFAULTS = {
    "enabled": True,
    "oauth_enabled": True,
    "api_token_enabled": True,
    "enable_core_tools": True,
    "enable_context_tools": True,
    "enable_customization_tools": True,
    "enable_reporting_tools": True,
    "enable_business_tools": True,
    "default_page_length": 20,
    "maximum_page_length": 200,
    "maximum_download_bytes": 10 * 1024 * 1024,
    "audit_retention_days": 90,
}
CLIENTS = {
    "claude": {
        "label": "Claude",
        "app_name": "Frax MCP — Claude",
        "default_port": 8765,
    },
    "codex": {
        "label": "Codex",
        "app_name": "Frax MCP — Codex",
        "default_port": 8766,
    },
}


def get_settings_state():
    settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
    return frappe._dict(
        {
            fieldname: (
                settings.get(fieldname)
                if settings.get(fieldname) not in (None, "")
                else default
            )
            for fieldname, default in DEFAULTS.items()
        }
    )


def has_setup_access() -> bool:
    if frappe.session.user in (None, "", "Guest"):
        return False
    return bool(frappe.get_doc("Page", SETUP_PAGE).is_permitted())


def require_setup_access():
    if not has_setup_access():
        frappe.throw(
            _("You do not have permission to use Frax Setup."), frappe.PermissionError
        )


def require_settings_permission(permission_type="read"):
    if not frappe.has_permission(SETTINGS_DOCTYPE, ptype=permission_type):
        frappe.throw(
            _("You do not have {0} permission for Frax MCP Settings.").format(
                permission_type
            ),
            frappe.PermissionError,
        )


def require_current_password(password: str):
    if frappe.session.user in (None, "", "Guest"):
        frappe.throw(_("Please sign in first."), frappe.AuthenticationError)
    if not password:
        frappe.throw(
            _("Your current password is required."), frappe.AuthenticationError
        )
    check_password(frappe.session.user, password)


def mcp_url():
    return f"{get_server_url().rstrip('/')}/api/method/{MCP_METHOD}"


def codex_callback_id(url: str):
    parts = urlsplit(url)
    canonical = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    digest = hashlib.sha256(canonical.encode()).digest()[:9]
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def callback_uris(integration: str, callback_port: int):
    if integration == "claude":
        return [
            f"http://localhost:{callback_port}/callback",
            "https://claude.ai/api/mcp/auth_callback",
            "https://claude.com/api/mcp/auth_callback",
        ]
    if integration == "codex":
        callback_id = codex_callback_id(mcp_url())
        return [f"http://127.0.0.1:{callback_port}/callback/{callback_id}"]
    frappe.throw(_("Unsupported MCP integration: {0}").format(integration))


def _validated_callback_port(integration, callback_port):
    if integration not in CLIENTS:
        frappe.throw(_("Unsupported MCP integration: {0}").format(integration))
    port = int(callback_port or CLIENTS[integration]["default_port"])
    if not 1024 <= port <= 65535:
        frappe.throw(_("Local callback port must be between 1024 and 65535."))
    return port


def _validated_local_callback_port(callback_port):
    if not callback_port:
        return None
    port = int(callback_port)
    if not 1024 <= port <= 65535:
        frappe.throw(_("Local callback port must be between 1024 and 65535."))
    return port


def _client_name(client_name, default=None):
    name = (client_name or default or "").strip()
    if not name:
        frappe.throw(_("Enter a client name."))
    return name


def _connection(integration):
    name = frappe.db.get_value(
        "Frax MCP Connection",
        {"user": frappe.session.user, "client_type": integration},
        "name",
    )
    if not name:
        name = frappe.db.get_value(
            "Frax MCP Connection",
            {"user": frappe.session.user, "integration": CLIENTS[integration]["label"]},
            "name",
        )
    return frappe.get_doc("Frax MCP Connection", name) if name else None


def _connection_by_label(integration):
    name = frappe.db.get_value(
        "Frax MCP Connection",
        {"user": frappe.session.user, "integration": integration},
        "name",
    )
    return frappe.get_doc("Frax MCP Connection", name) if name else None


def _client_status(integration):
    config = CLIENTS[integration]
    connection = _connection(integration)
    name = connection.oauth_client if connection else None
    exists = bool(name and frappe.db.exists("OAuth Client", name))
    callback_port = _validated_callback_port(
        integration, connection.callback_port if connection else config["default_port"]
    )
    expected = callback_uris(integration, callback_port)
    ready = False
    if exists:
        client = frappe.get_doc("OAuth Client", name)
        ready = (
            client.app_name == config["app_name"]
            and client.user == frappe.session.user
            and client.grant_type == "Authorization Code"
            and client.response_type == "Code"
            and client.scopes == "all openid"
            and not client.skip_authorization
            and [line for line in (client.redirect_uris or "").splitlines() if line]
            == expected
            and client.default_redirect_uri == expected[0]
            and {row.role for row in client.allowed_roles} == {SYSTEM_USER_ROLE}
        )
    return {
        "integration": integration,
        "label": config["label"],
        "client_id": name if exists else None,
        "exists": exists,
        "ready": ready,
        "callback_uris": expected,
        "callback_port": callback_port,
        "secret_available": exists,
    }


def _user_connections():
    connections = []
    for row in frappe.get_all(
        "Frax MCP Connection",
        filters={"user": frappe.session.user},
        fields=["integration", "client_type", "oauth_client"],
        order_by="creation asc",
    ):
        client = (
            frappe.get_doc("OAuth Client", row.oauth_client)
            if row.oauth_client and frappe.db.exists("OAuth Client", row.oauth_client)
            else None
        )
        connections.append(
            {
                "integration": row.integration,
                "client_type": row.client_type or "other",
                "client_id": row.oauth_client if client and client.user == frappe.session.user else None,
            }
        )
    return connections


def _oauth_snippets(clients):
    url = mcp_url()
    claude = clients["claude"]
    codex = clients["codex"]
    return {
        "claude_code": (
            "claude mcp add --transport http "
            f"--client-id {claude['client_id'] or '<CLIENT_ID>'} --client-secret "
            f"--callback-port {claude['callback_port']} frax {url}"
        ),
        "codex_cli": (
            "# ~/.codex/config.toml\n"
            f"mcp_oauth_callback_port = {codex['callback_port']}\n\n"
            f"codex mcp add frax --url {url} "
            f"--oauth-client-id {codex['client_id'] or '<CLIENT_ID>'}"
        ),
        "api_token": (
            "export FRAX_MCP_TOKEN='<API_KEY>:<API_SECRET>'\n"
            "# Add the server as Streamable HTTP and use FRAX_MCP_TOKEN as its bearer token."
        ),
    }


@frappe.whitelist(methods=["GET"])
def get_setup_context():
    require_setup_access()
    from frax import __version__ as frax_version
    from frax import prompts
    from frax.mcp import mcp
    from frax.tools import register_all_tools

    prompts.register()
    register_all_tools()
    settings = get_settings_state()
    clients = {key: _client_status(key) for key in CLIENTS}
    user = frappe.get_doc("User", frappe.session.user)
    return {
        "site_url": get_server_url(),
        "mcp_url": mcp_url(),
        "versions": {
            "frax": frax_version,
            "frappe": getattr(frappe, "__version__", "unknown"),
            "mcp_library": _package_version("frappe-mcp"),
        },
        "capabilities": {
            "protocol_version": "2025-03-26",
            "tools": len(mcp._tool_registry),
            "prompts": len(mcp._prompt_registry),
        },
        "settings": {key: settings.get(key) for key in DEFAULTS},
        "access": {"can_use": True, "roles": frappe.get_roles()},
        "oauth_clients": clients,
        "clients": _user_connections(),
        "api_token": {"api_key_exists": bool(user.api_key)},
        "snippets": _oauth_snippets(clients),
        "docs": {
            "claude_code": "https://code.claude.com/docs/en/mcp",
            "claude_connectors": "https://support.anthropic.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers",
            "codex": "https://developers.openai.com/codex/mcp",
        },
    }


def _package_version(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


@frappe.whitelist(methods=["POST"])
def configure_oauth_clients(
    password: str,
    claude_callback_port=None,
    codex_callback_port=None,
    integration=None,
    client_name=None,
):
    require_setup_access()
    settings = get_settings_state()
    if not settings.enabled or not settings.oauth_enabled:
        frappe.throw(
            _("OAuth authentication is disabled for Frax MCP."), frappe.PermissionError
        )
    require_current_password(password)
    created = []
    repaired = []
    one_time_secrets = {}

    if integration and integration not in CLIENTS:
        frappe.throw(_("Unsupported MCP integration: {0}").format(integration))
    integrations = [integration] if integration else CLIENTS
    for integration, config in ((key, CLIENTS[key]) for key in integrations):
        name_label = _client_name(
            client_name if integration else None, config["label"]
        )
        connection = _connection_by_label(name_label)
        if connection and connection.client_type and connection.client_type != integration:
            frappe.throw(_("A client with this name already exists for another type."))
        name = connection.oauth_client if connection else None
        client = (
            frappe.get_doc("OAuth Client", name)
            if name and frappe.db.exists("OAuth Client", name)
            else None
        )
        if client and client.user != frappe.session.user:
            frappe.throw(
                _("This OAuth client is not owned by the current user."),
                frappe.PermissionError,
            )
        if not client:
            client = frappe.new_doc("OAuth Client")
            created.append(integration)
        else:
            repaired.append(integration)

        requested_port = (
            claude_callback_port if integration == "claude" else codex_callback_port
        )
        if not requested_port and connection:
            requested_port = connection.callback_port
        port = _validated_callback_port(
            integration,
            requested_port,
        )
        redirects = callback_uris(integration, port)
        client.update(
            {
                "app_name": f"Frax MCP — {name_label}",
                "user": frappe.session.user,
                "grant_type": "Authorization Code",
                "response_type": "Code",
                "scopes": "all openid",
                "skip_authorization": 0,
                "redirect_uris": "\n".join(redirects),
                "default_redirect_uri": redirects[0],
            }
        )
        client.set("allowed_roles", [{"role": SYSTEM_USER_ROLE}])
        if client.is_new():
            client.insert(ignore_permissions=True)
            one_time_secrets[integration] = client.client_secret
        else:
            client.save(ignore_permissions=True)
        if not connection:
            connection = frappe.new_doc("Frax MCP Connection")
            connection.user = frappe.session.user
            connection.integration = name_label
        connection.client_type = integration
        connection.oauth_client = client.name
        connection.callback_port = port
        connection.save(ignore_permissions=True)
    return {
        "created": created,
        "repaired": repaired,
        "client_secrets": one_time_secrets,
        "context": get_setup_context() if has_setup_access() else None,
    }


@frappe.whitelist(methods=["POST"])
def reveal_claude_client_secret(password: str):
    require_setup_access()
    require_current_password(password)
    connection = _connection("claude")
    name = connection.oauth_client if connection else None
    if not name or not frappe.db.exists("OAuth Client", name):
        frappe.throw(_("The managed Claude OAuth client has not been configured."))
    client = frappe.get_doc("OAuth Client", name)
    if client.user != frappe.session.user:
        frappe.throw(
            _("This OAuth client is not owned by the current user."),
            frappe.PermissionError,
        )
    return {"client_id": name, "client_secret": client.client_secret}


@frappe.whitelist(methods=["POST"])
def rotate_oauth_secret(integration: str, password: str):
    require_setup_access()
    require_current_password(password)
    connection = (
        _connection(integration)
        if integration in CLIENTS
        else _connection_by_label(integration)
    )
    name = connection.oauth_client if connection else None
    if not name or not frappe.db.exists("OAuth Client", name):
        frappe.throw(_("Configure the managed OAuth client first."))
    secret = frappe.generate_hash(length=32)
    client = frappe.get_doc("OAuth Client", name)
    if client.user != frappe.session.user:
        frappe.throw(
            _("This OAuth client is not owned by the current user."),
            frappe.PermissionError,
        )
    client.client_secret = secret
    client.save(ignore_permissions=True)
    return {"client_id": name, "client_secret": secret}


@frappe.whitelist(methods=["POST"])
def configure_custom_oauth_client(
    integration: str, redirect_uris: str, password: str, callback_port=None
):
    """Create a user-owned OAuth client for any MCP application with known callbacks."""
    require_setup_access()
    settings = get_settings_state()
    if not settings.enabled or not settings.oauth_enabled:
        frappe.throw(
            _("OAuth authentication is disabled for Frax MCP."), frappe.PermissionError
        )
    require_current_password(password)
    integration = _client_name(integration)
    redirects = [
        uri.strip() for uri in (redirect_uris or "").splitlines() if uri.strip()
    ]
    if not integration or integration.lower() in {"claude", "codex"}:
        frappe.throw(_("Choose a descriptive name other than Claude or Codex."))
    if not redirects or any(
        urlsplit(uri).scheme not in {"https", "http"} for uri in redirects
    ):
        frappe.throw(_("Enter one valid HTTP(S) redirect URI per line."))
    connection = _connection_by_label(integration)
    if connection and connection.client_type and connection.client_type != "other":
        frappe.throw(_("A client with this name already exists for another type."))
    name = connection.oauth_client if connection else None
    client = (
        frappe.get_doc("OAuth Client", name)
        if name and frappe.db.exists("OAuth Client", name)
        else None
    )
    if client and client.user != frappe.session.user:
        frappe.throw(
            _("This OAuth client is not owned by the current user."),
            frappe.PermissionError,
        )
    if not client:
        client = frappe.new_doc("OAuth Client")
    client.update(
        {
            "app_name": f"Frax MCP — {integration}",
            "user": frappe.session.user,
            "grant_type": "Authorization Code",
            "response_type": "Code",
            "scopes": "all openid",
            "skip_authorization": 0,
            "redirect_uris": "\n".join(redirects),
            "default_redirect_uri": redirects[0],
        }
    )
    client.set("allowed_roles", [{"role": SYSTEM_USER_ROLE}])
    created = client.is_new()
    if created:
        client.insert(ignore_permissions=True)
    else:
        client.save(ignore_permissions=True)
    if not connection:
        connection = frappe.new_doc("Frax MCP Connection")
        connection.user = frappe.session.user
        connection.integration = integration
    connection.oauth_client = client.name
    connection.client_type = "other"
    connection.callback_port = _validated_local_callback_port(callback_port)
    connection.save(ignore_permissions=True)
    return {
        "created": created,
        "client_id": client.name,
        "client_secret": client.client_secret,
    }


@frappe.whitelist(methods=["POST"])
def generate_my_api_credentials(password: str, rotate=False):
    require_setup_access()
    settings = get_settings_state()
    if not settings.enabled or not settings.api_token_enabled:
        frappe.throw(
            _("API token authentication is disabled for Frax MCP."),
            frappe.PermissionError,
        )
    require_current_password(password)
    user = frappe.get_doc("User", frappe.session.user)
    if user.api_key and not frappe.parse_json(rotate):
        frappe.throw(
            _("An API key already exists. Confirm rotation to replace its secret.")
        )
    if not user.api_key:
        user.api_key = frappe.generate_hash(length=15)
    secret = frappe.generate_hash(length=32)
    user.api_secret = secret
    user.save(ignore_permissions=True)
    return {
        "api_key": user.api_key,
        "api_secret": secret,
        "bearer_token": f"Bearer {user.api_key}:{secret}",
    }


@frappe.whitelist(methods=["POST"])
def revoke_my_api_credentials(password: str):
    require_setup_access()
    require_current_password(password)
    user = frappe.get_doc("User", frappe.session.user)
    user.api_key = None
    user.api_secret = None
    user.save(ignore_permissions=True)
    return {"revoked": True}
