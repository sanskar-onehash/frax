from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from frax.tools import reporting


class TestReportingTools(TestCase):
    def test_nested_filters_cannot_use_unpermitted_fields(self):
        filters = [
            ["status", "=", "Open"],
            [
                "or",
                [
                    ["Customer", "customer_name", "like", "%Acme%"],
                    ["secret_segment", "=", "Internal"],
                ],
            ],
        ]

        invalid = reporting._invalid_filter_fields(
            filters, {"status", "customer_name"}, "Customer"
        )

        self.assertEqual(invalid, ["secret_segment"])

    def test_order_by_accepts_one_permitted_field_only(self):
        self.assertEqual(
            reporting._validated_order_by("modified desc", {"modified"}),
            "modified desc",
        )
        with (
            patch.object(reporting, "_", side_effect=lambda text: text),
            patch.object(
                reporting.frappe,
                "throw",
                side_effect=frappe.ValidationError("invalid order"),
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            reporting._validated_order_by("modified desc, owner", {"modified", "owner"})

    def test_report_builder_preview_is_permission_aware_and_bounded(self):
        rows = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        with (
            patch.object(reporting, "_require_source_permission"),
            patch.object(
                reporting,
                "get_permitted_fields",
                return_value=["name", "status", "modified"],
            ),
            patch.object(reporting, "_page", return_value=(0, 2)),
            patch.object(reporting.frappe, "get_list", return_value=rows) as get_list,
        ):
            result = reporting.preview_report_builder.__wrapped__(
                "ToDo",
                ["name", "status"],
                filters={"status": "Open"},
                order_by="modified desc",
            )

        get_list.assert_called_once_with(
            "ToDo",
            fields=["name", "status"],
            filters={"status": "Open"},
            group_by=None,
            order_by="modified desc",
            limit_start=0,
            limit_page_length=3,
        )
        self.assertEqual(len(result["data"]), 2)
        self.assertTrue(result["meta"]["has_more"])

    def test_invalid_preview_fields_return_suggestions_without_querying(self):
        with (
            patch.object(reporting, "_require_source_permission"),
            patch.object(
                reporting,
                "get_permitted_fields",
                return_value=["name", "status"],
            ),
            patch.object(reporting.frappe, "get_list") as get_list,
        ):
            result = reporting.preview_report_builder.__wrapped__(
                "ToDo", ["name", "statsu"]
            )

        get_list.assert_not_called()
        self.assertFalse(result["meta"]["query_executed"])
        self.assertEqual(result["warnings"][0]["fields"][0]["field"], "statsu")

    def test_run_report_preserves_native_permissions_and_bounds_output(self):
        report = Mock()
        report.disabled = 0
        report.ref_doctype = "ToDo"
        report.report_type = "Report Builder"
        report.is_permitted.return_value = True
        report.get_data.return_value = (
            [{"label": "Name", "fieldname": "name", "fieldtype": "Data"}],
            [{"name": "A"}, {"name": "B"}, {"name": "C"}],
        )
        with (
            patch.object(reporting.frappe, "get_doc", return_value=report),
            patch.object(reporting.frappe, "has_permission", return_value=True),
            patch.object(reporting, "_page", return_value=(0, 2)),
            patch.object(
                reporting.frappe,
                "session",
                SimpleNamespace(user="reporter@example.com"),
            ),
            patch.object(
                reporting.frappe.utils,
                "get_url",
                return_value="https://onehash.example",
            ),
        ):
            result = reporting.run_report.__wrapped__("Open Work")

        report.check_permission.assert_called_once_with("read")
        report.get_data.assert_called_once_with(
            filters={},
            limit=3,
            user="reporter@example.com",
            as_dict=True,
        )
        self.assertEqual(len(result["data"]), 2)
        self.assertTrue(result["meta"]["has_more"])

    def test_query_report_requires_safe_sql_and_explicit_roles(self):
        doc = {
            "doctype": "Report",
            "report_type": "Query Report",
            "query": "select name from `tabToDo`",
            "roles": [],
        }
        with patch("frappe.utils.safe_exec.check_safe_sql_query", return_value=True):
            diagnostics = reporting._report_diagnostics(doc)

        codes = {item["code"] for item in diagnostics}
        self.assertIn("query_report_permissions", codes)
        self.assertIn("missing_report_roles", codes)

    def test_standard_artifacts_are_rejected_before_save(self):
        meta = SimpleNamespace(fields=[], get_valid_columns=lambda: ["is_standard"])
        with patch.object(reporting.frappe, "get_meta", return_value=meta):
            result = reporting._validate_reporting_artifact(
                {
                    "doctype": "Dashboard Chart",
                    "chart_name": "Revenue",
                    "is_standard": 1,
                }
            )

        self.assertFalse(result["valid"])
        self.assertIn(
            "standard_artifact", {item["code"] for item in result["diagnostics"]}
        )

    def test_update_values_cannot_change_identity_or_standard_status(self):
        values = reporting._mutable_values(
            {
                "doctype": "Report",
                "name": "Revenue",
                "is_standard": "Yes",
                "module": "Core",
                "query": "select 1",
            }
        )

        self.assertEqual(values, {"query": "select 1"})

    def test_workspace_content_must_be_a_json_list(self):
        diagnostics = reporting._artifact_diagnostics(
            {"doctype": "Workspace", "content": '{"type":"header"}'}
        )

        self.assertIn(
            "invalid_workspace_content",
            {item["code"] for item in diagnostics},
        )
