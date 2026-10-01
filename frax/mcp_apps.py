from __future__ import annotations

import json

import frappe
from werkzeug import Response

from frax.branding import get_branding


APP_MIME_TYPE = "text/html;profile=mcp-app"
MAX_STRUCTURED_CONTENT_BYTES = 2 * 1024 * 1024
APP_RESOURCES = {
    "ui://frax/document-list.html": {
        "label": "Document List",
        "description": "Sortable document and query results.",
        "mode": "table",
    },
    "ui://frax/document-detail.html": {
        "label": "Document Detail",
        "description": "Readable document details and child rows.",
        "mode": "detail",
    },
    "ui://frax/report.html": {
        "label": "Report",
        "description": "Report columns, rows, totals, and summaries.",
        "mode": "report",
    },
}
TOOL_RESOURCES = {
    "frax_list_documents": "ui://frax/document-list.html",
    "frax_get_documents": "ui://frax/document-list.html",
    "frax_get_document": "ui://frax/document-detail.html",
    "frax_run_report": "ui://frax/report.html",
    "frax_preview_report_builder": "ui://frax/report.html",
}


def handle_resource_request(request_payload: dict):
    """Serve self-contained MCP App resources through the authenticated endpoint."""
    if not isinstance(request_payload, dict):
        return None
    method = request_payload.get("method")
    if method not in {"resources/list", "resources/templates/list", "resources/read"}:
        return None

    request_id = request_payload.get("id")
    if method == "resources/list":
        branding = get_branding()
        resources = [
            {
                "uri": uri,
                "name": f"{branding.display_title} {config['label']}",
                "description": config["description"],
                "mimeType": APP_MIME_TYPE,
                "_meta": _resource_meta(),
            }
            for uri, config in APP_RESOURCES.items()
        ]
        return _jsonrpc(request_id, {"resources": resources})
    if method == "resources/templates/list":
        return _jsonrpc(request_id, {"resourceTemplates": []})

    params = request_payload.get("params")
    if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
        return _jsonrpc_error(request_id, -32602, "A resource URI is required")
    uri = params["uri"]
    config = APP_RESOURCES.get(uri)
    if not config:
        return _jsonrpc_error(request_id, -32002, "Resource not found")

    path = frappe.get_app_path("frax", "public", "mcp_apps", "viewer.html")
    with open(path, encoding="utf-8") as file:
        html = file.read()
    branding = get_branding()
    html = html.replace("__FRAX_VIEW_MODE__", config["mode"])
    html = html.replace("__FRAX_APP_NAME__", _json_for_html(branding.display_title))
    return _jsonrpc(
        request_id,
        {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": APP_MIME_TYPE,
                    "text": html,
                    "_meta": _resource_meta(),
                }
            ]
        },
    )


def augment_response(response, request_payload: dict):
    """Add optional MCP Apps metadata without changing the text-only contract."""
    try:
        payload = json.loads(response.get_data(as_text=True))
        method = request_payload.get("method")
        if method == "initialize" and isinstance(payload.get("result"), dict):
            capabilities = payload["result"].setdefault("capabilities", {})
            capabilities.setdefault("resources", {}).setdefault("listChanged", False)
            capabilities.setdefault("extensions", {})["io.modelcontextprotocol/ui"] = {
                "mimeTypes": [APP_MIME_TYPE]
            }
        elif method == "tools/list":
            for tool in payload.get("result", {}).get("tools", []):
                uri = TOOL_RESOURCES.get(tool.get("name"))
                if uri:
                    tool["_meta"] = {
                        **(tool.get("_meta") or {}),
                        "ui": {"resourceUri": uri, "visibility": ["model"]},
                        # Compatibility with hosts implementing the pre-GA shape.
                        "ui/resourceUri": uri,
                    }
        elif method == "tools/call":
            result = payload.get("result")
            if (
                isinstance(result, dict)
                and not result.get("isError")
                and "structuredContent" not in result
            ):
                structured = _structured_content(result.get("content"))
                if structured is not None:
                    result["structuredContent"] = structured
        response.set_data(json.dumps(payload, separators=(",", ":"), default=str))
    except Exception:
        frappe.log_error(title="MCP Apps response augmentation failed")
    return response


def _structured_content(content):
    if not isinstance(content, list):
        return None
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if item.get("type") != "text" or not isinstance(text, str):
            continue
        if len(text.encode("utf-8")) > MAX_STRUCTURED_CONTENT_BYTES:
            continue
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"data": parsed}
    return None


def _resource_meta():
    return {
        "ui": {
            "csp": {
                "connectDomains": [],
                "resourceDomains": [],
                "frameDomains": [],
                "baseUriDomains": [],
            },
            "prefersBorder": True,
        }
    }


def _json_for_html(value):
    """Encode a value for a script literal without permitting tag termination."""
    return (
        json.dumps(value)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _jsonrpc(request_id, result):
    return Response(
        json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}),
        content_type="application/json",
    )


def _jsonrpc_error(request_id, code, message):
    return Response(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            }
        ),
        content_type="application/json",
    )
