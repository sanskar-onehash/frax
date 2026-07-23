from werkzeug import Response

import frappe
import frappe_mcp

from frax.context import OPERATOR_CONTEXT

mcp = frappe_mcp.MCP(name="frax", instructions=OPERATOR_CONTEXT)


@frappe.whitelist(methods=["POST"])
def handle_mcp():
    from frax import prompts
    from frax.tools import register_all_tools

    prompts.register()
    register_all_tools()
    return mcp.handle(frappe.request, Response())
