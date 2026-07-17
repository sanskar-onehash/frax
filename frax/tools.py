import frappe
from inspect import getdoc
from frappe_mcp import MCP
from frappe_mcp.server.tools import get_tool


def register_tools(mcp: MCP):
    register_frappe_tools(mcp)


def register_frappe_tools(mcp: MCP):

    for whitelisted in frappe.whitelisted:
        if not whitelisted.__module__.startswith("frappe."):
            continue

        # Skip if no docstring
        if getdoc(whitelisted) is None:
            continue

        mcp.add_tool(get_tool(whitelisted))
