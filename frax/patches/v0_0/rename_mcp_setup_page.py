import frappe


def execute():
    frappe.delete_doc_if_exists("Page", "mcp-setup", force=True)
