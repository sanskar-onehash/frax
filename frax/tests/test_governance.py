import unittest

from frax.audit import arguments_hash, redacted


class TestToolGovernance(unittest.TestCase):
    def test_argument_hash_is_order_independent(self):
        first = {"doctype": "ToDo", "name": "A"}
        second = {"name": "A", "doctype": "ToDo"}
        self.assertEqual(arguments_hash(first), arguments_hash(second))

    def test_audit_redaction_removes_scripts_and_secrets(self):
        result = redacted(
            {"script": "private", "api_secret": "secret", "name": "safe"}
        )
        self.assertEqual(
            result,
            {
                "script": "<redacted>",
                "api_secret": "<redacted>",
                "name": "safe",
            },
        )
