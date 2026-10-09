from __future__ import annotations

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase
from jsonschema import Draft202012Validator

from frax import operations, prompts, setup
from frax.mcp import mcp
from frax.tools import register_all_tools
from frax.tools import core, erpnext as business_tools, reporting


EXPECTED_FRAMEWORK_MAJOR = 16
COMPATIBILITY_PROFILE = os.environ.get("FRAX_COMPAT_PROFILE", "core").lower()
VALID_PROFILES = {"core", "business", "customized"}


class TestCompatibilityReleaseGate(FrappeTestCase):
    def setUp(self):
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user(self.previous_user)

    def test_release_branch_matches_installed_framework_and_profile(self):
        self.assertIn(COMPATIBILITY_PROFILE, VALID_PROFILES)
        self.assertEqual(_major_version(frappe.__version__), EXPECTED_FRAMEWORK_MAJOR)
        installed_apps = frappe.get_installed_apps()
        self.assertIn("frax", installed_apps)

        if COMPATIBILITY_PROFILE in {"business", "customized"}:
            self.assertIn(
                "erpnext",
                installed_apps,
                "The selected compatibility profile requires ERPNext.",
            )
        if "erpnext" in installed_apps:
            import erpnext

            self.assertEqual(
                _major_version(erpnext.__version__), EXPECTED_FRAMEWORK_MAJOR
            )

    def test_installation_defaults_and_setup_context(self):
        for doctype in (
            "Frax MCP Settings",
            "Frax MCP Allowed Role",
            "Frax MCP Audit Log",
        ):
            self.assertTrue(frappe.db.exists("DocType", doctype), doctype)

        settings = setup.get_settings_state()
        self.assertTrue(settings.enabled)
        self.assertTrue(settings.oauth_enabled)
        self.assertTrue(settings.api_token_enabled)
        self.assertTrue(settings.enable_core_tools)
        self.assertTrue(settings.enable_context_tools)
        self.assertTrue(settings.enable_customization_tools)
        self.assertTrue(settings.enable_reporting_tools)
        self.assertTrue(settings.enable_business_tools)

        context = setup.get_setup_context()
        self.assertTrue(context["access"]["can_use"])
        self.assertTrue(context["operations"]["can_view"])
        self.assertTrue(context["branding"]["server_name"])
        self.assertEqual(context["mcp_url"], setup.mcp_url())
        serialized = json.dumps(context).lower()
        self.assertNotIn("client_secret", serialized)
        self.assertNotIn("api_secret", serialized)

    def test_registered_tool_and_prompt_contracts(self):
        prompts.register()
        register_all_tools()
        expected_tools = {
            "frax_list_documents",
            "frax_get_document",
            "frax_create_document",
            "frax_get_doctype_context",
            "frax_preview_report_builder",
            "frax_run_report",
        }
        self.assertTrue(expected_tools.issubset(mcp._tool_registry))
        self.assertIn("frax_operator", mcp._prompt_registry)
        for tool in mcp._tool_registry.values():
            Draft202012Validator.check_schema(tool["input_schema"])
            self.assertFalse(tool["input_schema"].get("additionalProperties", True))

        if "erpnext" in frappe.get_installed_apps():
            self.assertTrue(
                business_tools.get_business_capabilities.__wrapped__()["installed"]
            )

    def test_native_document_permissions_and_report_query(self):
        result = core.create_document.__wrapped__(
            {
                "doctype": "ToDo",
                "description": "Frax compatibility probe",
            }
        )
        name = result["name"]
        self.addCleanup(_delete_if_exists, "ToDo", name)

        fetched = core.get_document.__wrapped__("ToDo", name=name)
        self.assertEqual(fetched["name"], name)
        with self.set_user("Guest"):
            with self.assertRaises(frappe.PermissionError):
                core.get_document.__wrapped__("ToDo", name=name)

        preview = reporting.preview_report_builder.__wrapped__(
            "ToDo",
            ["name", "status"],
            filters={"name": name},
            page_length=5,
        )
        self.assertEqual(preview["meta"]["doctype"], "ToDo")
        self.assertTrue(any(row["name"] == name for row in preview["data"]))

    def test_parent_queries_support_multiple_child_tables_and_distinct(self):
        user_name = f"frax-query-{frappe.generate_hash(length=10)}@example.com"
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": user_name,
                "first_name": "Frax Query Probe",
                "enabled": 1,
                "send_welcome_email": 0,
                "roles": [
                    {"role": "System Manager"},
                    {"role": "Website Manager"},
                ],
                "block_modules": [
                    {"module": "Core"},
                    {"module": "Email"},
                ],
            }
        ).insert(ignore_permissions=True)
        self.addCleanup(_delete_if_exists, "User", user.name)

        rows = core.list_documents.__wrapped__(
            "User",
            fields=[],
            filters=[
                [
                    "Has Role",
                    "role",
                    "in",
                    ["System Manager", "Website Manager"],
                ],
                ["Block Module", "module", "in", ["Core", "Email"]],
            ],
            distinct=True,
        )
        self.assertEqual([row["name"] for row in rows], [user.name])

        child_rows = core.list_documents.__wrapped__(
            "Has Role",
            fields=["parent", "role"],
            filters={"parent": user.name},
            parent_doctype="User",
        )
        self.assertEqual(
            {row["role"] for row in child_rows},
            {"System Manager", "Website Manager"},
        )

    def test_audit_aggregation_and_diagnostic_redaction_on_database(self):
        tool_name = "frax_compatibility_probe"
        secret_marker = "compatibility-secret-must-not-export"
        for outcome, duration, error_class, error_message in (
            ("success", 999_998, None, None),
            ("error", 999_999, "CompatibilityProbeError", secret_marker),
        ):
            audit = frappe.get_doc(
                {
                    "doctype": "Frax MCP Audit Log",
                    "actor": "Administrator",
                    "tool_name": tool_name,
                    "category": "core",
                    "risk": "read",
                    "outcome": outcome,
                    "duration_ms": duration,
                    "arguments_hash": "compatibility-probe",
                    "arguments_preview": '{"token":"<redacted>"}',
                    "error_class": error_class,
                    "error_message": error_message,
                }
            ).insert(ignore_permissions=True)
            self.addCleanup(_delete_if_exists, "Frax MCP Audit Log", audit.name)

        health = operations._operational_health(1)
        self.assertTrue(health["available"])
        self.assertTrue(any(row["tool"] == tool_name for row in health["slow_tools"]))
        self.assertTrue(
            any(
                row["tool"] == tool_name
                and row["error_class"] == "CompatibilityProbeError"
                for row in health["failures"]
            )
        )
        diagnostic = operations.get_diagnostic_export.__wrapped__(1)
        serialized = json.dumps(diagnostic)
        self.assertNotIn(secret_marker, serialized)
        for failure in diagnostic["health"]["failures"]:
            self.assertNotIn("arguments_preview", failure)
            self.assertNotIn("error_message", failure)

    def test_customized_profile_preserves_form_layout_metadata(self):
        if COMPATIBILITY_PROFILE != "customized":
            self.skipTest("Run with FRAX_COMPAT_PROFILE=customized")

        definitions = (
            {
                "fieldname": "custom_frax_compatibility_tab",
                "label": "Compatibility",
                "fieldtype": "Tab Break",
                "insert_after": "description",
            },
            {
                "fieldname": "custom_frax_compatibility_section",
                "label": "Details",
                "fieldtype": "Section Break",
                "insert_after": "custom_frax_compatibility_tab",
            },
            {
                "fieldname": "custom_frax_compatibility_choice",
                "label": "Choice",
                "fieldtype": "Select",
                "options": "\nOption 1",
                "insert_after": "custom_frax_compatibility_section",
            },
            {
                "fieldname": "custom_frax_compatibility_column",
                "fieldtype": "Column Break",
                "insert_after": "custom_frax_compatibility_choice",
            },
        )
        for definition in definitions:
            existing = frappe.db.get_value(
                "Custom Field",
                {"dt": "ToDo", "fieldname": definition["fieldname"]},
            )
            if existing:
                _delete_custom_field(existing)
            custom_field = frappe.get_doc(
                {"doctype": "Custom Field", "dt": "ToDo", **definition}
            ).insert(ignore_permissions=True)
            self.addCleanup(_delete_custom_field, custom_field.name)

        frappe.clear_cache(doctype="ToDo")
        fields = frappe.get_meta("ToDo").fields
        positions = {
            field.fieldname: index
            for index, field in enumerate(fields)
            if field.fieldname
            in {definition["fieldname"] for definition in definitions}
        }
        self.assertEqual(
            list(positions), [definition["fieldname"] for definition in definitions]
        )
        self.assertEqual(list(positions.values()), sorted(positions.values()))
        choice = frappe.get_meta("ToDo").get_field("custom_frax_compatibility_choice")
        self.assertEqual(choice.options, "\nOption 1")
        self.assertFalse(choice.default)


def _major_version(value) -> int:
    return int(str(value).split(".", 1)[0])


def _delete_if_exists(doctype, name):
    previous_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        if frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
    finally:
        frappe.set_user(previous_user)


def _delete_custom_field(name):
    _delete_if_exists("Custom Field", name)
    frappe.clear_cache(doctype="ToDo")
