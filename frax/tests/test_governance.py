import unittest
from typing import Literal
from unittest.mock import patch

import frappe

from frax.audit import arguments_hash, redacted
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
