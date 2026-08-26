import frappe
from frappe import _
from frappe.model.document import Document


class FraxMCPSettings(Document):
    def validate(self):
        if self.enabled and not (self.oauth_enabled or self.api_token_enabled):
            frappe.throw(_("Enable at least one authentication method while MCP is enabled."))
