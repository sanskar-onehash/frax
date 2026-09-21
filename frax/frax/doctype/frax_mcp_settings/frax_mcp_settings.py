import frappe
from frappe import _
from frappe.model.document import Document


class FraxMCPSettings(Document):
    def validate(self):
        from frax.setup import DEFAULTS

        if self.enabled and not (self.oauth_enabled or self.api_token_enabled):
            frappe.throw(_("Enable at least one authentication method while MCP is enabled."))

        self.default_page_length = self._bounded(
            "default_page_length",
            self.default_page_length or DEFAULTS["default_page_length"],
            1,
            200,
        )
        self.maximum_page_length = self._bounded(
            "maximum_page_length",
            self.maximum_page_length or DEFAULTS["maximum_page_length"],
            self.default_page_length,
            1000,
        )
        self.maximum_download_bytes = self._bounded(
            "maximum_download_bytes",
            self.maximum_download_bytes or DEFAULTS["maximum_download_bytes"],
            1024,
            50 * 1024 * 1024,
        )
        self.audit_retention_days = self._bounded(
            "audit_retention_days",
            self.audit_retention_days or DEFAULTS["audit_retention_days"],
            30,
            3650,
        )

    @staticmethod
    def _bounded(fieldname, value, minimum, maximum):
        value = int(value or 0)
        if not minimum <= value <= maximum:
            frappe.throw(
                _("{0} must be between {1} and {2}.").format(
                    frappe.unscrub(fieldname), minimum, maximum
                )
            )
        return value
