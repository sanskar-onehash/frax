from werkzeug import Response

import frappe
import frappe_mcp


mcp = frappe_mcp.MCP(name="frax")


@frappe.whitelist(methods=["POST"])
def handle_mcp():
    from frax.tools import register_all_tools

    register_all_tools()
    return mcp.handle(frappe.request, Response())
