import json
import unittest
from pathlib import Path
from unittest.mock import patch

from frappe import _dict
from werkzeug import Response

from frax.mcp_apps import (
    APP_MIME_TYPE,
    MAX_STRUCTURED_CONTENT_BYTES,
    augment_response,
    handle_resource_request,
)


class TestMCPApps(unittest.TestCase):
    def response(self, result):
        return Response(
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}),
            content_type="application/json",
        )

    def payload(self, response):
        return json.loads(response.get_data(as_text=True))

    @patch("frax.mcp_apps.get_branding")
    def test_resources_are_branded_and_self_contained(self, get_branding):
        get_branding.return_value = _dict(display_title="Acme Suite")
        listed = self.payload(
            handle_resource_request({"id": 1, "method": "resources/list"})
        )

        resources = listed["result"]["resources"]
        self.assertEqual(len(resources), 3)
        self.assertTrue(
            all(item["name"].startswith("Acme Suite ") for item in resources)
        )
        self.assertTrue(all(item["mimeType"] == APP_MIME_TYPE for item in resources))
        self.assertTrue(all(item["_meta"]["ui"]["prefersBorder"] for item in resources))

    @patch("frax.mcp_apps.get_branding")
    @patch("frax.mcp_apps.frappe.get_app_path")
    def test_resource_read_injects_safe_branding(self, get_app_path, get_branding):
        viewer = Path(__file__).parents[1] / "public" / "mcp_apps" / "viewer.html"
        get_app_path.return_value = str(viewer)
        get_branding.return_value = _dict(
            display_title="Acme </script><script>alert(1)</script>"
        )

        response = handle_resource_request(
            {
                "id": 2,
                "method": "resources/read",
                "params": {"uri": "ui://frax/report.html"},
            }
        )
        content = self.payload(response)["result"]["contents"][0]

        self.assertEqual(content["mimeType"], APP_MIME_TYPE)
        self.assertIn('mode="report"', content["text"])
        self.assertIn("Content-Security-Policy", content["text"])
        self.assertNotIn("</script><script>alert", content["text"])
        self.assertNotIn("__FRAX_", content["text"])
        self.assertEqual(content["_meta"]["ui"]["csp"]["connectDomains"], [])

    def test_resource_read_validates_uri(self):
        missing = self.payload(
            handle_resource_request({"id": 1, "method": "resources/read"})
        )
        unknown = self.payload(
            handle_resource_request(
                {
                    "id": 2,
                    "method": "resources/read",
                    "params": {"uri": "ui://frax/missing"},
                }
            )
        )

        self.assertEqual(missing["error"]["code"], -32602)
        self.assertEqual(unknown["error"]["code"], -32002)

    def test_initialize_advertises_resources_and_ui_extension(self):
        response = augment_response(
            self.response({"capabilities": {}}), {"method": "initialize"}
        )
        capabilities = self.payload(response)["result"]["capabilities"]

        self.assertEqual(capabilities["resources"], {"listChanged": False})
        self.assertEqual(
            capabilities["extensions"]["io.modelcontextprotocol/ui"]["mimeTypes"],
            [APP_MIME_TYPE],
        )

    def test_only_supported_tools_receive_ui_metadata(self):
        response = augment_response(
            self.response(
                {
                    "tools": [
                        {"name": "frax_list_documents", "_meta": {"existing": True}},
                        {"name": "frax_get_value"},
                    ]
                }
            ),
            {"method": "tools/list"},
        )
        tools = self.payload(response)["result"]["tools"]

        self.assertEqual(tools[0]["_meta"]["existing"], True)
        self.assertEqual(
            tools[0]["_meta"]["ui"]["resourceUri"],
            "ui://frax/document-list.html",
        )
        self.assertEqual(tools[0]["_meta"]["ui"]["visibility"], ["model"])
        self.assertNotIn("_meta", tools[1])

    def test_tool_call_adds_structured_data_without_removing_text(self):
        content = [{"type": "text", "text": '[{"name":"A"}]'}]
        response = augment_response(
            self.response({"content": content, "isError": False}),
            {"method": "tools/call"},
        )
        result = self.payload(response)["result"]

        self.assertEqual(result["content"], content)
        self.assertEqual(result["structuredContent"]["data"][0]["name"], "A")

    def test_invalid_error_and_oversized_results_are_not_promoted(self):
        cases = [
            {"content": [{"type": "text", "text": "not json"}]},
            {"content": [{"type": "text", "text": "{}"}], "isError": True},
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"value": "x" * MAX_STRUCTURED_CONTENT_BYTES}
                        ),
                    }
                ]
            },
        ]
        for result in cases:
            with self.subTest(result=result.get("isError")):
                response = augment_response(
                    self.response(result), {"method": "tools/call"}
                )
                self.assertNotIn("structuredContent", self.payload(response)["result"])

    def test_viewer_rejects_unrelated_window_messages(self):
        viewer = Path(__file__).parents[1] / "public" / "mcp_apps" / "viewer.html"
        html = viewer.read_text(encoding="utf-8")

        self.assertIn("event.source!==parent", html)
        self.assertNotIn("eval(", html)
        self.assertNotIn("document.write", html)


if __name__ == "__main__":
    unittest.main()
