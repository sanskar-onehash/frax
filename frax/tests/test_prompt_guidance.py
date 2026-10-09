import unittest

from frax.context import OPERATOR_CONTEXT
from frax.prompts import NATIVE_UI_CONTEXT


class TestPromptGuidance(unittest.TestCase):
    def test_operator_context_explains_select_initial_value_behavior(self):
        self.assertIn("non-empty first line", OPERATOR_CONTEXT)
        self.assertIn("leading newline", OPERATOR_CONTEXT)
        self.assertIn("Choose intentionally", OPERATOR_CONTEXT)

    def test_native_ui_context_requires_intentional_form_layout(self):
        self.assertIn("complete merged field order", NATIVE_UI_CONTEXT)
        self.assertIn("Tab Break, Section Break, and Column Break", NATIVE_UI_CONTEXT)
        self.assertIn("Avoid both a single long column", NATIVE_UI_CONTEXT)
        self.assertIn("initially selects it", NATIVE_UI_CONTEXT)
        self.assertIn("`\\nOption 1`", NATIVE_UI_CONTEXT)
        self.assertIn("Both are valid", NATIVE_UI_CONTEXT)
        self.assertIn("reread merged metadata", NATIVE_UI_CONTEXT)
