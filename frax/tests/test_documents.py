from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from frax.tools import core, documents


class TestDocumentTools(FrappeTestCase):
    def test_list_documents_uses_configured_default_and_maximum(self):
        settings = SimpleNamespace(default_page_length=25, maximum_page_length=100)
        with (
            patch("frax.setup.get_settings_state", return_value=settings),
            patch("frappe.get_list", return_value=[]) as get_list,
        ):
            core.list_documents.__wrapped__("User", limit_start=-10, limit_page_length=500)

        self.assertEqual(get_list.call_args.kwargs["limit_start"], 0)
        self.assertEqual(get_list.call_args.kwargs["limit_page_length"], 100)

    def test_list_documents_forwards_multiple_child_filters_and_distinct(self):
        filters = [
            ["Has Role", "role", "=", "System Manager"],
            ["Block Module", "module", "=", "Core"],
        ]
        with patch("frappe.get_list", return_value=[]) as get_list:
            core.list_documents.__wrapped__(
                "User",
                fields=[],
                filters=filters,
                distinct=True,
            )

        self.assertEqual(get_list.call_args.kwargs["filters"], filters)
        self.assertTrue(get_list.call_args.kwargs["distinct"])

    def test_list_documents_requires_real_parent_for_direct_child_query(self):
        with patch("frappe.get_list", return_value=[]) as get_list:
            core.list_documents.__wrapped__(
                "Has Role",
                fields=["parent", "role"],
                parent_doctype="User",
            )
        self.assertEqual(get_list.call_args.kwargs["parent_doctype"], "User")

        with self.assertRaises(frappe.PermissionError):
            core.list_documents.__wrapped__("Has Role")
        with self.assertRaises(frappe.PermissionError):
            core.list_documents.__wrapped__("Has Role", parent_doctype="ToDo")

    def test_page_length_uses_site_default(self):
        settings = SimpleNamespace(default_page_length=30, maximum_page_length=80)
        with patch("frax.tools.documents.get_settings_state", return_value=settings):
            self.assertEqual(documents._page_length(None), 30)
            self.assertEqual(documents._page_length(500), 80)

    def test_batch_read_rejects_more_than_fifty_names(self):
        with self.assertRaises(frappe.ValidationError):
            documents.get_documents.__wrapped__("User", [str(index) for index in range(51)])

    def test_attachment_download_requires_exact_parent(self):
        parent = MagicMock()
        file_doc = SimpleNamespace(
            attached_to_doctype="Note",
            attached_to_name="OTHER",
        )
        with (
            patch("frappe.get_doc", side_effect=[parent, file_doc]),
            self.assertRaises(frappe.PermissionError),
        ):
            documents.download_attachment.__wrapped__("FILE-1", "Note", "NOTE-1")

        parent.check_permission.assert_called_once_with("read")
