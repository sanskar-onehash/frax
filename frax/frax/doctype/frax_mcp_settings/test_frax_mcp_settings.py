from unittest.mock import patch

import frappe
from frappe.exceptions import SessionStopped
from frappe.tests.utils import FrappeTestCase

from frax import setup
from frax import mcp as mcp_module


class TestFraxMCPSettings(FrappeTestCase):
    def setUp(self):
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user(self.previous_user)

    def test_default_settings_are_safe_and_compatible(self):
        settings = frappe.get_single("Frax MCP Settings")
        self.assertEqual(settings.enabled, 1)
        self.assertEqual(settings.oauth_enabled, 1)
        self.assertEqual(settings.api_token_enabled, 1)

    def test_enabled_service_requires_authentication_method(self):
        settings = frappe.get_single("Frax MCP Settings")
        settings.enabled = 1
        settings.oauth_enabled = 0
        settings.api_token_enabled = 0
        self.assertRaises(frappe.ValidationError, settings.validate)

    def test_codex_callback_is_stable_and_url_specific(self):
        with patch("frax.setup.mcp_url", return_value="https://erp.example/api/method/frax.mcp.handle_mcp"):
            first = setup.callback_uris("codex", 8766)[0]
            second = setup.callback_uris("codex", 8766)[0]
        with patch("frax.setup.mcp_url", return_value="https://other.example/api/method/frax.mcp.handle_mcp"):
            other = setup.callback_uris("codex", 8766)[0]
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertTrue(first.startswith("http://127.0.0.1:8766/callback/"))

    def test_managed_oauth_clients_are_idempotent_and_repairable(self):
        self._clear_managed_connections()
        with patch("frax.setup.require_current_password"):
            result = setup.configure_oauth_clients("test-password", 8875, 8876)
        claude_name = setup._connection("claude").oauth_client
        codex_name = setup._connection("codex").oauth_client
        claude_secret = frappe.db.get_value("OAuth Client", claude_name, "client_secret")

        self.assertIn("claude", result["created"])
        self.assertIn("claude", result["client_secrets"])
        self.assertTrue(frappe.db.exists("OAuth Client", codex_name))

        with patch("frax.setup.require_current_password"):
            second = setup.configure_oauth_clients("test-password", 8875, 8876)
        self.assertEqual(setup._connection("claude").oauth_client, claude_name)
        self.assertEqual(setup._connection("codex").oauth_client, codex_name)
        self.assertEqual(frappe.db.get_value("OAuth Client", claude_name, "client_secret"), claude_secret)
        self.assertFalse(second["client_secrets"])

        frappe.db.set_value("OAuth Client", claude_name, "redirect_uris", "https://invalid.example/callback")
        with patch("frax.setup.require_current_password"):
            setup.configure_oauth_clients("test-password", 8875, 8876)
        client = frappe.get_doc("OAuth Client", claude_name)
        self.assertEqual(client.redirect_uris.splitlines(), setup.callback_uris("claude", 8875))

    def test_user_connection_does_not_adopt_manual_client(self):
        self._clear_managed_connections()
        manual = frappe.get_doc(
            {
                "doctype": "OAuth Client",
                "app_name": setup.CLIENTS["claude"]["app_name"],
                "scopes": "all openid",
                "redirect_uris": "https://manual.example/callback",
                "default_redirect_uri": "https://manual.example/callback",
                "grant_type": "Authorization Code",
                "response_type": "Code",
            }
        ).insert(ignore_permissions=True)
        with patch("frax.setup.require_current_password"):
            setup.configure_oauth_clients("test-password")
        managed = setup._connection("claude").oauth_client
        self.assertNotEqual(managed, manual.name)

        frappe.delete_doc("OAuth Client", managed, ignore_permissions=True, force=True)
        with patch("frax.setup.require_current_password"):
            setup.configure_oauth_clients("test-password")
        self.assertNotEqual(setup._connection("claude").oauth_client, managed)
        self.assertNotEqual(setup._connection("claude").oauth_client, manual.name)

    def test_setup_context_never_contains_secrets(self):
        self._clear_managed_connections()
        with patch("frax.setup.require_current_password"):
            setup.configure_oauth_clients("test-password")
        context = setup.get_setup_context()
        serialized = frappe.as_json(context).lower()
        self.assertNotIn("client_secret", serialized)
        self.assertNotIn("api_secret", serialized)

    def test_oauth_secret_rotation_is_limited_to_the_current_users_client(self):
        self._clear_managed_connections()
        with patch("frax.setup.require_current_password"):
            setup.configure_oauth_clients("test-password")
        claude_name = setup._connection("claude").oauth_client
        before = frappe.db.get_value("OAuth Client", claude_name, "client_secret")
        with patch("frax.setup.require_current_password"):
            result = setup.rotate_oauth_secret("claude", "test-password")
        self.assertNotEqual(before, result["client_secret"])
        self.assertEqual(
            frappe.db.get_value("OAuth Client", claude_name, "client_secret"),
            result["client_secret"],
        )

    def test_runtime_master_switch_returns_service_unavailable(self):
        state = frappe._dict({"enabled": 0, "oauth_enabled": 1, "api_token_enabled": 1})
        with patch("frax.mcp.get_settings_state", return_value=state):
            self.assertRaises(SessionStopped, mcp_module.handle_mcp)

    def test_runtime_authentication_switches_are_enforced(self):
        oauth_off = frappe._dict({"enabled": 1, "oauth_enabled": 0, "api_token_enabled": 1})
        with (
            patch("frax.mcp.get_settings_state", return_value=oauth_off),
            patch("frax.mcp.require_setup_access"),
            patch("frax.mcp._request_auth_method", return_value="oauth"),
        ):
            self.assertRaises(frappe.PermissionError, mcp_module.handle_mcp)

        api_off = frappe._dict({"enabled": 1, "oauth_enabled": 1, "api_token_enabled": 0})
        with (
            patch("frax.mcp.get_settings_state", return_value=api_off),
            patch("frax.mcp.require_setup_access"),
            patch("frax.mcp._request_auth_method", return_value="api_token"),
        ):
            self.assertRaises(frappe.PermissionError, mcp_module.handle_mcp)

    def test_runtime_requires_mcp_setup_page_access(self):
        state = frappe._dict({"enabled": 1, "oauth_enabled": 1, "api_token_enabled": 1})
        with (
            patch("frax.mcp.get_settings_state", return_value=state),
            patch("frax.mcp.require_setup_access", side_effect=frappe.PermissionError),
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

    def _clear_managed_connections(self):
        for name in frappe.get_all(
            "Frax MCP Connection", filters={"user": frappe.session.user}, pluck="name"
        ):
            frappe.delete_doc("Frax MCP Connection", name, ignore_permissions=True, force=True)
