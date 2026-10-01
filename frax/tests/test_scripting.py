import unittest
from unittest.mock import patch

from frax.tools.scripting import validate_server_script


class TestServerScriptValidation(unittest.TestCase):
    def test_runtime_constraints_are_diagnostics_not_write_blockers(self):
        validator = validate_server_script.__wrapped__
        with patch("frax.tools.scripting.is_safe_exec_enabled", return_value=True):
            result = validator(
                "import os\ndoc.db_set('status', 'Open', update_modified=False)\nfrappe.db.commit()",
                script_type="DocType Event",
            )
        codes = {item["code"] for item in result["diagnostics"]}
        self.assertTrue(
            {
                "imports_unavailable",
                "direct_database_write",
                "modified_timestamp_bypass",
                "transaction_unavailable",
            }
            <= codes
        )
        self.assertFalse(result["blocking"])
