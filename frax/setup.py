from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import frappe
from frappe import _
from frappe.oauth import get_server_url
from frappe.utils.password import check_password


SETTINGS_DOCTYPE = "Frax MCP Settings"
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


def get_allowed_roles() -> list[str]:
    settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
    return list(
        dict.fromkeys(
            row.role for row in settings.get("allowed_roles") or [] if row.role
        )
    )


def has_mcp_access(user: str | None = None) -> bool:
    user = user or frappe.session.user
    if user in (None, "", "Guest"):
        return False
    if user == "Administrator":
        return True
    if frappe.db.get_value("User", user, "user_type") != "System User":
        return False
    allowed_roles = set(get_allowed_roles())
    return not allowed_roles or bool(allowed_roles.intersection(frappe.get_roles(user)))


def require_mcp_access():
    if not has_mcp_access():
        frappe.throw(
            _("Your account is not allowed to use this AI connection."),
            frappe.PermissionError,
        )


def require_settings_permission(permission_type="read"):
    if not frappe.has_permission(SETTINGS_DOCTYPE, ptype=permission_type):
        frappe.throw(
            _("You do not have {0} permission for MCP Settings.").format(
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


def site_url():
    try:
        return get_server_url().rstrip("/")
    except RuntimeError:
        return frappe.utils.get_url().rstrip("/")


def mcp_url():
    return f"{site_url()}/api/method/{MCP_METHOD}"


def _connection_snippets(server_name="frax"):
    url = mcp_url()
    return {
        "claude_code": f"claude mcp add --transport http {server_name} {url}",
        "codex_cli": f"codex mcp add {server_name} --url {url}",
        "api_token": (
            "Authorization: Bearer <KEY>:<SECRET>\n"
            "Use only when the client cannot complete the recommended OAuth flow."
        ),
    }


@frappe.whitelist(methods=["GET"])
def get_setup_context():
    require_mcp_access()
    from frax import __version__ as frax_version
    from frax import prompts
    from frax.branding import public_branding
    from frax.mcp import mcp
    from frax.tools import register_all_tools

    prompts.register()
    register_all_tools()
    settings = get_settings_state()
    branding = public_branding()
    user = frappe.get_doc("User", frappe.session.user)
    user_roles = frappe.get_roles()
    from frax.operations import has_operational_access

    return {
        "site_url": site_url(),
        "mcp_url": mcp_url(),
        "versions": {
            "service": frax_version,
            "platform": getattr(frappe, "__version__", "unknown"),
            "protocol_library": _package_version("frappe-mcp"),
        },
        "capabilities": {
            "protocol_version": "2025-03-26",
            "tools": len(mcp._tool_registry),
            "prompts": len(mcp._prompt_registry),
        },
        "settings": {key: settings.get(key) for key in DEFAULTS},
        "access": {
            "can_use": True,
            "allowed_roles": get_allowed_roles(),
            "user_roles": user_roles,
        },
        "operations": {
            "can_view": has_operational_access(frappe.session.user, user_roles)
        },
        "api_token": {"api_key_exists": bool(user.api_key)},
        "branding": branding,
        "snippets": _connection_snippets(branding["server_name"]),
        "docs": {
            "claude_code": "https://code.claude.com/docs/en/mcp",
            "codex": "https://developers.openai.com/codex/mcp",
        },
    }


def _package_version(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


@frappe.whitelist(methods=["POST"])
def generate_my_api_credentials(password: str, rotate=False):
    require_mcp_access()
    settings = get_settings_state()
    if not settings.enabled or not settings.api_token_enabled:
        frappe.throw(
            _("API token authentication is disabled for this MCP service."),
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
    require_mcp_access()
    require_current_password(password)
    user = frappe.get_doc("User", frappe.session.user)
    user.api_key = None
    user.api_secret = None
    user.save(ignore_permissions=True)
    return {"revoked": True}
