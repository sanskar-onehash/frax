from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from frax.tools import erpnext as business_tools
from frax.tools import registry


class TestBusinessTools(TestCase):
    def test_public_tool_identifiers_are_business_named_and_non_generic(self):
        expected = {
            "frax_get_business_capabilities",
            "frax_get_item_details",
            "frax_get_stock_balance",
            "frax_get_party_details",
            "frax_get_accounting_context",
            "frax_create_mapped_draft",
            "frax_create_payment_entry_draft",
        }
        policies = registry.get_tool_policies()

        self.assertTrue(expected.issubset(policies))
        self.assertFalse(any("erpnext" in name for name in expected))
        self.assertNotIn("frax_get_document", expected)
        self.assertNotIn("frax_save_document", expected)

    def test_business_capabilities_describe_only_native_helpers(self):
        result = business_tools.get_business_capabilities.__wrapped__()

        self.assertTrue(result["installed"])
        self.assertIn("item_details", result["helpers"])
        self.assertIn("draft_payment_entry", result["helpers"])
        self.assertEqual(len(result["mappings"]), len(business_tools.MAPPERS))

    def test_business_categories_are_enabled_together(self):
        settings = frappe._dict(
            {
                "enable_core_tools": 0,
                "enable_context_tools": 0,
                "enable_customization_tools": 0,
                "enable_reporting_tools": 0,
                "enable_business_tools": 1,
            }
        )
        with patch("frax.setup.get_settings_state", return_value=settings):
            enabled = registry.enabled_categories()

        self.assertTrue(
            {
                "business",
                "business_selling",
                "business_buying",
                "business_stock",
                "business_accounts",
            }.issubset(enabled)
        )

    def test_business_tools_are_hidden_without_the_owning_application(self):
        settings = frappe._dict(
            {
                "enable_core_tools": 0,
                "enable_context_tools": 0,
                "enable_customization_tools": 0,
                "enable_reporting_tools": 0,
                "enable_business_tools": 1,
            }
        )
        with (
            patch("frax.setup.get_settings_state", return_value=settings),
            patch("frappe.get_installed_apps", return_value=["frappe", "frax"]),
        ):
            self.assertFalse(registry.tool_is_available("frax_get_stock_balance"))

    def test_mapping_uses_native_mapper_and_inserts_only_a_draft(self):
        source = Mock()
        mapped = Mock()
        mapped.name = "SO-0001"
        mapped.doctype = "Sales Order"
        mapped.docstatus = 0
        mapped.is_new.return_value = True
        mapped.flags = SimpleNamespace(ignore_permissions=None)
        mapped.as_dict.return_value = {
            "doctype": "Sales Order",
            "name": mapped.name,
            "docstatus": 0,
        }
        mapper = Mock(return_value=mapped)

        with (
            patch.object(business_tools.frappe, "get_doc", return_value=source),
            patch.object(business_tools.frappe, "has_permission", return_value=True),
            patch.object(business_tools, "_resolved_mapper", return_value=mapper),
            patch.object(
                business_tools.frappe.utils,
                "get_url_to_form",
                return_value="/app/sales-order/SO-0001",
            ),
        ):
            result = business_tools.map_document.__wrapped__(
                "quotation_to_sales_order", "QTN-0001"
            )

        source.check_permission.assert_called_once_with("read")
        mapper.assert_called_once_with("QTN-0001")
        mapped.insert.assert_called_once_with()
        self.assertFalse(mapped.flags.ignore_permissions)
        self.assertEqual(result["meta"]["docstatus"], 0)

    def test_payment_helper_inserts_an_unsubmitted_document(self):
        source = Mock()
        entry = Mock()
        entry.name = "ACC-PAY-0001"
        entry.doctype = "Payment Entry"
        entry.docstatus = 0
        entry.is_new.return_value = True
        entry.flags = SimpleNamespace(ignore_permissions=None)
        entry.as_dict.return_value = {
            "doctype": "Payment Entry",
            "name": entry.name,
            "docstatus": 0,
        }
        native_get_payment_entry = Mock(return_value=entry)

        with (
            patch.object(business_tools.frappe, "get_doc", return_value=source),
            patch.object(business_tools.frappe, "has_permission", return_value=True),
            patch(
                "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry",
                native_get_payment_entry,
            ),
            patch.object(
                business_tools.frappe.utils,
                "get_url_to_form",
                return_value="/app/payment-entry/ACC-PAY-0001",
            ),
        ):
            result = business_tools.create_payment_entry_draft.__wrapped__(
                "Sales Invoice", "SINV-0001"
            )

        source.check_permission.assert_called_once_with("read")
        native_get_payment_entry.assert_called_once_with(
            "Sales Invoice",
            "SINV-0001",
            party_amount=None,
            bank_account=None,
            bank_amount=None,
            reference_date=None,
        )
        entry.insert.assert_called_once_with()
        self.assertFalse(entry.flags.ignore_permissions)
        self.assertEqual(result["meta"]["docstatus"], 0)
