import frappe_mcp


mcp = frappe_mcp.MCP(name="frax")


@mcp.register()
def handle_mcp():
    from frax.tools import register_all_tools

    register_all_tools()
