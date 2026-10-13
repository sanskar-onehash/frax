from unittest import TestCase
from unittest.mock import patch

from werkzeug import Response

from frax.mcp import _filter_tools_response


class TestMCPResponse(TestCase):
    @patch("frax.mcp.frappe.log_error")
    def test_empty_notification_response_is_ignored(self, log_error):
        response = Response(status=202)

        result = _filter_tools_response(response)

        self.assertIs(result, response)
        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.get_data(), b"")
        log_error.assert_not_called()
