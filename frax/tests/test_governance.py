import unittest
from types import SimpleNamespace
from typing import Literal
from unittest.mock import MagicMock, patch

import frappe

from frax import audit
from frax.audit import _affected_documents, arguments_hash, redacted
from frax.tools.registry import _resolve_input_schema, _validate_arguments


class TestToolGovernance(unittest.TestCase):
    def setUp(self):
        self.throw_patcher = patch("frappe.throw", side_effect=self._raise_frappe_error)
        self.throw_patcher.start()
        self.addCleanup(self.throw_patcher.stop)

    @staticmethod
    def _raise_frappe_error(message, exception=frappe.ValidationError, **kwargs):
        raise exception(message)

    def test_argument_hash_is_order_independent(self):
        first = {"doctype": "ToDo", "name": "A"}
        second = {"name": "A", "doctype": "ToDo"}
        self.assertEqual(arguments_hash(first), arguments_hash(second))

    def test_audit_redaction_removes_scripts_and_secrets(self):
        result = redacted({"script": "private", "api_secret": "secret", "name": "safe"})
        self.assertEqual(
            result,
            {
                "script": "<redacted>",
                "api_secret": "<redacted>",
                "name": "safe",
            },
        )

    def test_affected_documents_accepts_frappe_dict(self):
        result = frappe._dict(doctype="Event", name="EV00022")

        self.assertEqual(
            _affected_documents(result),
            [{"doctype": "Event", "name": "EV00022"}],
        )

    def test_audit_keeps_invalid_doctype_out_of_link_field(self):
        audit_document = MagicMock()
        fake_frappe = SimpleNamespace(
            db=SimpleNamespace(
                exists=lambda doctype, name: name == "Frax MCP Audit Log"
            ),
            session=SimpleNamespace(user="Administrator"),
            get_doc=MagicMock(return_value=audit_document),
            log_error=MagicMock(),
        )

        with patch.object(audit, "frappe", fake_frappe), patch.object(
            audit, "_authentication_method", return_value="oauth"
        ):
            audit.log_tool_call(
                tool_name="frax_get_doctype_context",
                category="context",
                risk="read",
                arguments={"doctype": "Missing DocType"},
                outcome="error",
                duration_ms=8,
                error=RuntimeError("DocType not found"),
            )

        payload = fake_frappe.get_doc.call_args.args[0]
        self.assertIsNone(payload["target_doctype"])
        self.assertIn("Missing DocType", payload["arguments_preview"])
        audit_document.insert.assert_called_once_with(ignore_permissions=True)
        fake_frappe.log_error.assert_not_called()

    def test_tool_schema_rejects_missing_required_argument(self):
        def example(doctype: str, limit: int | None = None):
            return doctype, limit

        schema = _resolve_input_schema(example)

        with self.assertRaisesRegex(frappe.ValidationError, "doctype.*required"):
            _validate_arguments(example, {}, schema)

    def test_tool_schema_rejects_incorrect_argument_type(self):
        def example(limit: int):
            return limit

        schema = _resolve_input_schema(example)

        with self.assertRaisesRegex(frappe.ValidationError, "limit.*integer"):
            _validate_arguments(example, {"limit": "20"}, schema)

    def test_tool_schema_preserves_literal_choices(self):
        def example(operation: Literal["count", "sum"] | None = None):
            return operation

        schema = _resolve_input_schema(example)
        self.assertEqual(
            schema["properties"]["operation"]["anyOf"][0]["enum"],
            ["count", "sum"],
        )
        _validate_arguments(example, {"operation": None}, schema)
        with self.assertRaisesRegex(frappe.ValidationError, "operation"):
            _validate_arguments(example, {"operation": "average"}, schema)

    def test_unknown_argument_suggests_matching_name(self):
        def example(status: str):
            return status

        with self.assertRaisesRegex(frappe.ValidationError, r"statsu \(use status\)"):
            _validate_arguments(example, {"statsu": "Open"})

    def test_explicit_nested_schema_is_enforced(self):
        def example(args: dict):
            return args

        schema = {
            "type": "object",
            "properties": {
                "args": {
                    "type": "object",
                    "properties": {"company": {"type": "string"}},
                    "required": ["company"],
                }
            },
            "required": ["args"],
            "additionalProperties": False,
        }
        resolved = _resolve_input_schema(example, schema)

        with self.assertRaisesRegex(frappe.ValidationError, "company.*required"):
            _validate_arguments(example, {"args": {}}, resolved)
