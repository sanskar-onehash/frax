import unittest
from unittest.mock import patch

import frappe

from frax.tools.scripting import (
    INPLACE_ASSIGNMENT_AVAILABLE,
    validate_script_payload,
    validate_server_script,
)


class TestServerScriptValidation(unittest.TestCase):
    def test_runtime_errors_are_write_blockers(self):
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
        self.assertTrue(result["blocking"])

    def test_unsafe_string_format_is_detected_before_runtime(self):
        with patch("frax.tools.scripting.is_safe_exec_enabled", return_value=True):
            result = validate_server_script.__wrapped__(
                "message = 'Hello {}'.format(doc.name)",
                script_type="DocType Event",
            )

        unsafe = [
            item for item in result["diagnostics"] if item["code"] == "unsafe_attribute"
        ]
        self.assertTrue(result["compilable"])
        self.assertTrue(result["blocking"])
        self.assertEqual(unsafe[0]["line"], 1)
        self.assertIn(".format", unsafe[0]["message"])

    def test_blocking_diagnostics_reject_write_payload(self):
        with patch(
            "frax.tools.scripting.is_safe_exec_enabled", return_value=True
        ), patch(
            "frax.tools.scripting.frappe.throw", side_effect=frappe.ValidationError
        ), self.assertRaises(frappe.ValidationError):
            validate_script_payload(
                {
                    "script": "message = '{}'.format(doc.name)",
                    "script_type": "DocType Event",
                }
            )

    def test_f_string_alternative_is_allowed(self):
        with patch("frax.tools.scripting.is_safe_exec_enabled", return_value=True):
            result = validate_server_script.__wrapped__(
                'message = f"Hello {doc.name}"',
                script_type="DocType Event",
            )

        self.assertTrue(result["compilable"])
        self.assertFalse(result["blocking"])

    def test_advisory_database_write_remains_non_blocking(self):
        with patch("frax.tools.scripting.is_safe_exec_enabled", return_value=True):
            result = validate_server_script.__wrapped__(
                "frappe.db.set_value('ToDo', doc.name, 'status', 'Closed')",
                script_type="DocType Event",
            )

        self.assertFalse(result["blocking"])
        self.assertIn(
            "direct_database_write",
            {item["code"] for item in result["diagnostics"]},
        )

    def test_augmented_assignment_matches_installed_runtime(self):
        with patch("frax.tools.scripting.is_safe_exec_enabled", return_value=True):
            result = validate_server_script.__wrapped__(
                "total = 1\ntotal += 2",
                script_type="DocType Event",
            )

        diagnostic = next(
            item
            for item in result["diagnostics"]
            if item["code"] == "augmented_assignment"
        )
        self.assertEqual(
            diagnostic["severity"],
            "warning" if INPLACE_ASSIGNMENT_AVAILABLE else "error",
        )
        self.assertEqual(result["blocking"], not INPLACE_ASSIGNMENT_AVAILABLE)
