import frappe
from frappe import _
from frappe.model.document import Document


class FraxMCPConnection(Document):
    def validate(self):
        if not self.user or not self.integration:
            return
        duplicate = frappe.db.exists(
            "Frax MCP Connection",
            {"user": self.user, "integration": self.integration, "name": ("!=", self.name)},
        )
        if duplicate:
            frappe.throw(_("Only one Frax MCP connection is allowed per user and integration."))
