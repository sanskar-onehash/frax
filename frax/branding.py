from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

import frappe


DEFAULT_BRANDING = {
    "product_name": "OneHash",
    "platform_name": "OneHash",
    "display_title": "OneHash",
    "server_name": "frax",
    "disclosure_mode": "strict",
    "logo_url": None,
    "icon_url": None,
    "support_url": None,
    "documentation_url": None,
    "operator_wording": None,
}

DISCLOSURE_MODES = {"strict", "contextual"}
_INTERNAL_NAME_KEYS = {
    "ERPNext": "product_name",
    "Frappe Framework": "platform_name",
    "Frappe": "platform_name",
    "Frax MCP": "display_title",
    "Frax": "product_name",
}
_INTERNAL_NAME_PATTERN = re.compile(
    r"\b(?:Frappe Framework|Frax MCP|ERPNext|Frappe|Frax)\b"
)


def get_branding():
    """Return validated branding; site_config is optional and only overrides defaults."""
    configured = frappe.conf.get("frax_branding") or {}
    if not isinstance(configured, dict):
        configured = {}

    values = DEFAULT_BRANDING.copy()
    for key in values:
        value = configured.get(key)
        if isinstance(value, str) and value.strip():
            values[key] = value.strip()

    for key in ("logo_url", "icon_url"):
        if values[key] and not _valid_asset_url(values[key]):
            values[key] = DEFAULT_BRANDING[key]
    for key in ("support_url", "documentation_url"):
        if values[key] and not _valid_web_url(values[key]):
            values[key] = DEFAULT_BRANDING[key]

    values["product_name"] = values["product_name"][:80]
    values["platform_name"] = values["platform_name"][:80]
    values["display_title"] = values["display_title"][:120]
    values["server_name"] = _server_name(values["server_name"])
    if values["disclosure_mode"].lower() not in DISCLOSURE_MODES:
        values["disclosure_mode"] = DEFAULT_BRANDING["disclosure_mode"]
    else:
        values["disclosure_mode"] = values["disclosure_mode"].lower()
    if values["operator_wording"]:
        values["operator_wording"] = values["operator_wording"][:1000]
    return frappe._dict(values)


def public_branding():
    """Return values that are safe to expose in setup and protocol metadata."""
    branding = get_branding()
    return {
        key: branding[key]
        for key in (
            "product_name",
            "platform_name",
            "display_title",
            "server_name",
            "disclosure_mode",
            "logo_url",
            "icon_url",
            "support_url",
            "documentation_url",
        )
    }


def brand_text(text: str, branding=None) -> str:
    """Replace user-facing implementation names only when strict mode is active."""
    branding = branding or get_branding()
    if branding.disclosure_mode != "strict" or not isinstance(text, str):
        return text
    return _INTERNAL_NAME_PATTERN.sub(
        lambda match: branding[_INTERNAL_NAME_KEYS[match.group(0)]], text
    )


def branded_operator_context(base_context: str) -> str:
    branding = get_branding()
    if branding.disclosure_mode == "strict":
        policy = (
            f"You operate {branding.display_title}. Treat names of underlying frameworks, "
            "vendor applications, Python packages, and internal integration components as "
            f"private implementation details. Never reveal or hint at them to end users. Refer "
            f"to the software and its capabilities as {branding.product_name} or "
            f"{branding.platform_name}. Exact internal identifiers may be used silently in tool "
            "calls, but must not appear in the final user-facing answer."
        )
    else:
        policy = (
            f"You operate {branding.display_title}. Use {branding.product_name} in normal "
            "user-facing language. Mention exact underlying technical names only when they are "
            "necessary for an explicitly technical diagnosis, code example, or administrator "
            "instruction."
        )
    if branding.operator_wording:
        policy += f"\n\nSite operator guidance:\n{branding.operator_wording}"
    return f"{policy}\n\n{brand_text(base_context, branding)}"


def brand_mcp_response(response, request_payload: dict):
    """Apply branding to protocol metadata without rewriting operational tool data."""
    try:
        payload = json.loads(response.get_data(as_text=True))
        result = payload.get("result")
        method = request_payload.get("method")
        branding = get_branding()

        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            error["message"] = brand_text(error["message"], branding)

        if method == "initialize" and isinstance(result, dict):
            server_info = result.setdefault("serverInfo", {})
            server_info["name"] = branding.server_name
            server_info["title"] = branding.display_title
            if isinstance(result.get("instructions"), str):
                result["instructions"] = brand_text(result["instructions"], branding)
        elif method in {"tools/list", "prompts/list"} and isinstance(result, dict):
            collection = "tools" if method == "tools/list" else "prompts"
            for item in result.get(collection, []):
                _brand_descriptive_fields(item, branding)
        elif (
            method == "tools/call"
            and isinstance(result, dict)
            and result.get("isError")
        ):
            for item in result.get("content", []):
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    item["text"] = brand_text(item["text"], branding)

        response.set_data(json.dumps(payload, separators=(",", ":"), default=str))
    except Exception:
        frappe.log_error(title="MCP response branding failed")
    return response


def _brand_descriptive_fields(value, branding):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"description", "title"} and isinstance(item, str):
                value[key] = brand_text(item, branding)
            elif isinstance(item, (dict, list)):
                _brand_descriptive_fields(item, branding)
    elif isinstance(value, list):
        for item in value:
            _brand_descriptive_fields(item, branding)


def _server_name(value):
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-._").lower()
    return value[:80] or DEFAULT_BRANDING["server_name"]


def _valid_asset_url(value):
    return value.startswith("/") or _valid_web_url(value)


def _valid_web_url(value):
    parsed = urlsplit(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
