import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from werkzeug import Response

from frax import branding


class _AttrDict(dict):
    __getattr__ = dict.__getitem__


def _frappe_with_config(config=None):
    return SimpleNamespace(
        conf={"frax_branding": config} if config is not None else {},
        _dict=_AttrDict,
        log_error=lambda **kwargs: None,
    )


class TestBranding(TestCase):
    def test_defaults_need_no_site_configuration(self):
        with patch.object(branding, "frappe", _frappe_with_config()):
            values = branding.get_branding()

        self.assertEqual(values.product_name, "OneHash")
        self.assertEqual(values.platform_name, "OneHash")
        self.assertEqual(values.display_title, "OneHash")
        self.assertEqual(values.server_name, "frax")
        self.assertEqual(values.disclosure_mode, "strict")

    def test_site_configuration_overrides_only_supplied_values(self):
        config = {
            "product_name": "Acme Business",
            "server_name": "Acme Assistant!",
            "logo_url": "/assets/acme/logo.svg",
            "support_url": "javascript:alert(1)",
            "disclosure_mode": "contextual",
        }
        with patch.object(branding, "frappe", _frappe_with_config(config)):
            values = branding.get_branding()

        self.assertEqual(values.product_name, "Acme Business")
        self.assertEqual(values.platform_name, "OneHash")
        self.assertEqual(values.server_name, "acme-assistant")
        self.assertEqual(values.logo_url, "/assets/acme/logo.svg")
        self.assertIsNone(values.support_url)
        self.assertEqual(values.disclosure_mode, "contextual")

    def test_strict_mode_rebrands_user_facing_text(self):
        with patch.object(branding, "frappe", _frappe_with_config()):
            result = branding.brand_text(
                "Frax MCP uses Frappe Framework and ERPNext capabilities."
            )

        self.assertEqual(result, "OneHash uses OneHash and OneHash capabilities.")

    def test_contextual_mode_preserves_technical_text(self):
        config = {"disclosure_mode": "contextual"}
        text = "Frappe Framework and ERPNext"
        with patch.object(branding, "frappe", _frappe_with_config(config)):
            self.assertEqual(branding.brand_text(text), text)

    def test_protocol_metadata_uses_configured_brand(self):
        response = Response(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "serverInfo": {"name": "internal"},
                        "instructions": "Use Frappe and ERPNext.",
                    },
                }
            ),
            content_type="application/json",
        )
        config = {
            "product_name": "Acme",
            "platform_name": "Acme Platform",
            "display_title": "Acme Assistant",
            "server_name": "acme",
        }
        with patch.object(branding, "frappe", _frappe_with_config(config)):
            branding.brand_mcp_response(response, {"method": "initialize"})

        result = json.loads(response.get_data(as_text=True))["result"]
        self.assertEqual(result["serverInfo"]["name"], "acme")
        self.assertEqual(result["serverInfo"]["title"], "Acme Assistant")
        self.assertEqual(result["instructions"], "Use Acme Platform and Acme.")

    def test_operator_policy_differs_by_disclosure_mode(self):
        with patch.object(branding, "frappe", _frappe_with_config()):
            strict = branding.branded_operator_context("Work with Frappe.")
        with patch.object(
            branding,
            "frappe",
            _frappe_with_config({"disclosure_mode": "contextual"}),
        ):
            contextual = branding.branded_operator_context("Work with Frappe.")

        self.assertIn("Never reveal or hint", strict)
        self.assertNotIn("Frappe", strict)
        self.assertIn("explicitly technical diagnosis", contextual)
        self.assertIn("Frappe", contextual)

    def test_strict_mode_rebrands_protocol_errors(self):
        response = Response(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32000, "message": "ERPNext operation failed"},
                }
            ),
            content_type="application/json",
        )
        with patch.object(branding, "frappe", _frappe_with_config()):
            branding.brand_mcp_response(response, {"method": "tools/call"})

        error = json.loads(response.get_data(as_text=True))["error"]
        self.assertEqual(error["message"], "OneHash operation failed")
