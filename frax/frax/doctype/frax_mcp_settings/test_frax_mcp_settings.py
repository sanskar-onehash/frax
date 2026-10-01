from unittest.mock import patch

import frappe
from frappe.exceptions import SessionStopped
from frappe.tests.utils import FrappeTestCase

from frax import mcp as mcp_module
from frax import setup


class TestFraxMCPSettings(FrappeTestCase):
    def setUp(self):
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user(self.previous_user)

    def test_default_settings_enable_all_capability_categories(self):
        settings = frappe.get_single("Frax MCP Settings")
        self.assertEqual(settings.enabled, 1)
        self.assertEqual(settings.oauth_enabled, 1)
        self.assertEqual(settings.api_token_enabled, 1)
        state = setup.get_settings_state()
        self.assertTrue(state.enable_core_tools)
        self.assertTrue(state.enable_context_tools)
        self.assertTrue(state.enable_customization_tools)
        self.assertTrue(state.enable_reporting_tools)
        self.assertTrue(state.enable_business_tools)

    def test_enabled_service_requires_authentication_method(self):
        settings = frappe.get_single("Frax MCP Settings")
        settings.enabled = 1
        settings.oauth_enabled = 0
        settings.api_token_enabled = 0
        self.assertRaises(frappe.ValidationError, settings.validate)

    def test_empty_allowed_roles_permits_any_system_user(self):
        with (
            patch("frax.setup.get_allowed_roles", return_value=[]),
            patch("frax.setup.frappe.db.get_value", return_value="System User"),
        ):
            self.assertTrue(setup.has_mcp_access("developer@example.com"))

    def test_selected_roles_require_one_matching_role(self):
        with (
            patch("frax.setup.get_allowed_roles", return_value=["Accounts User"]),
            patch("frax.setup.frappe.db.get_value", return_value="System User"),
            patch("frax.setup.frappe.get_roles", return_value=["Accounts User"]),
        ):
            self.assertTrue(setup.has_mcp_access("accountant@example.com"))

        with (
            patch("frax.setup.get_allowed_roles", return_value=["Accounts User"]),
            patch("frax.setup.frappe.db.get_value", return_value="System User"),
            patch("frax.setup.frappe.get_roles", return_value=["Sales User"]),
        ):
            self.assertFalse(setup.has_mcp_access("seller@example.com"))

    def test_guest_and_website_users_cannot_connect(self):
        self.assertFalse(setup.has_mcp_access("Guest"))
        with patch("frax.setup.frappe.db.get_value", return_value="Website User"):
            self.assertFalse(setup.has_mcp_access("customer@example.com"))

    def test_administrator_is_always_allowed(self):
        with patch("frax.setup.get_allowed_roles", return_value=["Unavailable Role"]):
            self.assertTrue(setup.has_mcp_access("Administrator"))

    def test_setup_context_contains_no_manual_oauth_configuration(self):
        context = setup.get_setup_context()
        serialized = frappe.as_json(context).lower()
        for private_field in (
            "client_id",
            "client_secret",
            "redirect_uris",
            "callback_port",
            "api_secret",
        ):
            self.assertNotIn(private_field, serialized)

    def test_connection_commands_only_require_the_endpoint(self):
        with patch(
            "frax.setup.mcp_url",
            return_value="https://onehash.example/api/method/frax.mcp.handle_mcp",
        ):
            snippets = setup._connection_snippets()
        self.assertEqual(
            snippets["codex_cli"],
            "codex mcp add frax --url "
            "https://onehash.example/api/method/frax.mcp.handle_mcp",
        )
        self.assertEqual(
            snippets["claude_code"],
            "claude mcp add --transport http frax "
            "https://onehash.example/api/method/frax.mcp.handle_mcp",
        )

    def test_runtime_master_switch_returns_service_unavailable(self):
        state = frappe._dict({"enabled": 0, "oauth_enabled": 1, "api_token_enabled": 1})
        with patch("frax.mcp.get_settings_state", return_value=state):
            self.assertRaises(SessionStopped, mcp_module.handle_mcp)

    def test_runtime_authentication_switches_are_enforced(self):
        oauth_off = frappe._dict(
            {"enabled": 1, "oauth_enabled": 0, "api_token_enabled": 1}
        )
        with (
            patch("frax.mcp.get_settings_state", return_value=oauth_off),
            patch("frax.mcp.require_mcp_access"),
            patch("frax.mcp._request_auth_method", return_value="oauth"),
        ):
            self.assertRaises(frappe.PermissionError, mcp_module.handle_mcp)

        api_off = frappe._dict(
            {"enabled": 1, "oauth_enabled": 1, "api_token_enabled": 0}
        )
        with (
            patch("frax.mcp.get_settings_state", return_value=api_off),
            patch("frax.mcp.require_mcp_access"),
            patch("frax.mcp._request_auth_method", return_value="api_token"),
        ):
            self.assertRaises(frappe.PermissionError, mcp_module.handle_mcp)

    def test_runtime_requires_mcp_access(self):
        state = frappe._dict({"enabled": 1, "oauth_enabled": 1, "api_token_enabled": 1})
        with (
            patch("frax.mcp.get_settings_state", return_value=state),
            patch("frax.mcp.require_mcp_access", side_effect=frappe.PermissionError),
        ):
            self.assertRaises(frappe.PermissionError, mcp_module.handle_mcp)

    def test_api_credentials_only_change_current_user(self):
        user = frappe.get_doc("User", "Administrator")
        previous_key = user.api_key
        previous_secret = user.get_password("api_secret", raise_exception=False)
        try:
            user.api_key = None
            user.api_secret = None
            user.save(ignore_permissions=True)
            with patch("frax.setup.require_current_password"):
                credentials = setup.generate_my_api_credentials("test-password")
            user.reload()
            self.assertEqual(user.api_key, credentials["api_key"])
            self.assertEqual(user.get_password("api_secret"), credentials["api_secret"])
            with patch("frax.setup.require_current_password"):
                setup.revoke_my_api_credentials("test-password")
            user.reload()
            self.assertFalse(user.api_key)
            self.assertFalse(user.get_password("api_secret", raise_exception=False))
        finally:
            user.api_key = previous_key
            user.api_secret = previous_secret
            user.save(ignore_permissions=True)
