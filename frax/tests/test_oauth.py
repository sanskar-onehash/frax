from unittest import TestCase
from unittest.mock import patch

from frax import oauth


class TestOAuthCompatibility(TestCase):
    def test_v16_uses_native_oauth_discovery(self):
        with patch.object(oauth.frappe, "__version__", "16.27.0"):
            self.assertTrue(oauth._frappe_has_oauth_metadata_routes())

    def test_older_versions_use_compatibility_discovery(self):
        with patch.object(oauth.frappe, "__version__", "15.88.1"):
            self.assertFalse(oauth._frappe_has_oauth_metadata_routes())

    def test_fallback_metadata_retains_public_pkce_support(self):
        with patch("frax.oauth.get_server_url", return_value="https://onehash.example"):
            metadata = oauth.authorization_server_metadata()

        self.assertEqual(
            metadata["code_challenge_methods_supported"], ["S256", "plain"]
        )
        self.assertIn("none", metadata["token_endpoint_auth_methods_supported"])
        self.assertNotIn("registration_endpoint", metadata)
