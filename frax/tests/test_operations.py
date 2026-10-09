import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from frax import operations


class TestOperations(unittest.TestCase):
    @staticmethod
    def _raise_frappe_error(message, exception=frappe.ValidationError, **kwargs):
        raise exception(message)

    def test_operational_access_is_limited_to_system_managers(self):
        self.assertTrue(
            operations.has_operational_access("Administrator", ["Sales User"])
        )
        self.assertFalse(operations.has_operational_access("Guest", ["System Manager"]))
        self.assertTrue(
            operations.has_operational_access("manager@example.com", ["System Manager"])
        )
        self.assertFalse(
            operations.has_operational_access("user@example.com", ["Sales User"])
        )

        regular_user = SimpleNamespace(
            session=SimpleNamespace(user="user@example.com"),
            get_roles=lambda: ["Sales User"],
            throw=self._raise_frappe_error,
            PermissionError=frappe.PermissionError,
        )
        with (
            patch.object(operations, "frappe", regular_user),
            patch.object(operations, "_", side_effect=lambda value: value),
        ):
            with self.assertRaises(frappe.PermissionError):
                operations.require_operational_access()

        manager = SimpleNamespace(
            session=SimpleNamespace(user="manager@example.com"),
            get_roles=lambda: ["System Manager"],
            throw=self._raise_frappe_error,
            PermissionError=frappe.PermissionError,
        )
        with patch.object(operations, "frappe", manager):
            operations.require_operational_access()

    def test_health_summary_aggregates_without_record_details(self):
        def get_all(doctype, **kwargs):
            fields = kwargs["fields"]
            if "outcome" in fields:
                return [
                    {"outcome": "success", "calls": 8},
                    {"outcome": "error", "calls": 2},
                ]
            if "category" in fields:
                return [{"category": "core", "calls": 10}]
            if "error_class" in fields:
                return [
                    {
                        "tool_name": "frax_get_document",
                        "error_class": "PermissionError",
                        "calls": 2,
                        "last_seen": datetime(2026, 10, 9, 12, 30),
                    }
                ]
            if "tool_name" not in fields:
                return [{"calls": 10, "average_ms": 25.5, "maximum_ms": 80}]
            return [
                {
                    "tool_name": "frax_get_document",
                    "calls": 10,
                    "average_ms": 25.5,
                    "maximum_ms": 80,
                }
            ]

        fake_frappe = SimpleNamespace(
            db=SimpleNamespace(exists=lambda *args: True),
            get_all=get_all,
        )
        with (
            patch.object(operations, "frappe", fake_frappe),
            patch(
                "frax.operations.now_datetime",
                return_value=datetime(2026, 10, 9, 13, 0),
            ),
        ):
            result = operations._operational_health(7)

        self.assertEqual(result["totals"]["calls"], 10)
        self.assertEqual(result["totals"]["success_rate_percent"], 80.0)
        self.assertEqual(result["totals"]["average_duration_ms"], 25.5)
        self.assertEqual(result["failures"][0]["error_class"], "PermissionError")
        serialized = json.dumps(result)
        self.assertNotIn("arguments", serialized)
        self.assertNotIn("error_message", serialized)
        self.assertNotIn("target_name", serialized)

    def test_diagnostic_export_excludes_sensitive_record_data(self):
        settings = frappe._dict(
            {
                **operations.DEFAULTS,
                "enabled": True,
                "audit_retention_days": 90,
            }
        )
        health = {
            "available": True,
            "window": {"days": 7},
            "totals": {"calls": 3},
            "categories": [],
            "slow_tools": [],
            "failures": [],
        }
        fake_frappe = SimpleNamespace(
            __version__="16.0.0",
            get_installed_apps=lambda: [
                "frappe",
                "erpnext",
                "frax",
                "private_app",
            ],
        )
        with (
            patch("frax.operations.get_settings_state", return_value=settings),
            patch(
                "frax.operations.get_allowed_roles",
                return_value=["Accounts User"],
            ),
            patch.object(operations, "frappe", fake_frappe),
            patch("frax.operations._operational_health", return_value=health),
            patch("frax.operations.require_operational_access"),
            patch("frax.operations._package_version", return_value="1.2.3"),
            patch(
                "frax.operations.now_datetime",
                return_value=datetime(2026, 10, 9, 13, 0),
            ),
        ):
            result = operations.get_diagnostic_export.__wrapped__(7)

        serialized = json.dumps(result)
        self.assertTrue(result["service"]["business_application_installed"])
        self.assertEqual(result["service"]["allowed_role_count"], 1)
        self.assertNotIn("Accounts User", serialized)
        self.assertNotIn("private_app", serialized)
        self.assertNotIn("arguments_preview", serialized)
        self.assertEqual(result["redaction"]["error_messages"], "excluded")

    def test_diagnostic_window_is_bounded(self):
        self.assertEqual(operations._window_days(0), 1)
        self.assertEqual(operations._window_days(365), operations.MAX_WINDOW_DAYS)
        self.assertEqual(operations._window_days("invalid"), 7)
