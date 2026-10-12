from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from frax import oauth


class TestOAuthCompatibility(TestCase):
    def test_authorization_metadata_advertises_registration_and_pkce(self):
        with patch("frax.oauth.get_server_url", return_value="https://onehash.example"):
            metadata = oauth.authorization_server_metadata()

        self.assertEqual(
            metadata["registration_endpoint"],
            "https://onehash.example/api/method/frax.oauth.register_client",
        )
        self.assertEqual(metadata["code_challenge_methods_supported"], ["S256"])
        self.assertEqual(metadata["token_endpoint_auth_methods_supported"], ["none"])

    def test_public_loopback_client_metadata_is_accepted(self):
        metadata = oauth._validate_client_metadata(
            {
                "client_name": "Codex",
                "redirect_uris": ["http://127.0.0.1:1455/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            }
        )

        self.assertEqual(metadata["token_endpoint_auth_method"], "none")
        self.assertEqual(metadata["scope"], "all openid")

    def test_omitted_auth_method_defaults_to_public_client(self):
        metadata = oauth._validate_client_metadata(
            {
                "client_name": "Codex",
                "redirect_uris": ["http://127.0.0.1:1455/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            }
        )

        self.assertEqual(metadata["token_endpoint_auth_method"], "none")

    def test_confidential_client_authentication_is_rejected(self):
        for auth_method in ("client_secret_basic", "client_secret_post"):
            with self.subTest(auth_method=auth_method):
                with self.assertRaisesRegex(
                    ValueError, "only public-client PKCE authentication is supported"
                ):
                    oauth._validate_client_metadata(
                        {
                            "client_name": "Confidential client",
                            "redirect_uris": ["https://client.example/callback"],
                            "token_endpoint_auth_method": auth_method,
                        }
                    )

    def test_registration_payload_does_not_issue_a_client_secret(self):
        payload = oauth._registration_payload(
            SimpleNamespace(client_id="public-client"),
            {
                "client_name": "Codex",
                "redirect_uris": ["http://127.0.0.1:1455/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": "all openid",
            },
        )

        self.assertEqual(payload["client_id"], "public-client")
        self.assertEqual(payload["token_endpoint_auth_method"], "none")
        self.assertNotIn("client_secret", payload)
        self.assertNotIn("client_secret_expires_at", payload)

    def test_https_and_localhost_redirects_are_accepted(self):
        for uri in (
            "https://client.example/oauth/callback",
            "http://localhost:8765/callback",
            "http://[::1]:8765/callback",
        ):
            with self.subTest(uri=uri):
                self.assertTrue(oauth._is_secure_redirect_uri(uri))

    def test_insecure_or_ambiguous_redirects_are_rejected(self):
        for uri in (
            "http://client.example/callback",
            "https://client.example/callback#fragment",
            "https://user:password@client.example/callback",
            "javascript:alert(1)",
        ):
            with self.subTest(uri=uri):
                self.assertFalse(oauth._is_secure_redirect_uri(uri))

    def test_unsupported_client_metadata_is_rejected(self):
        invalid_clients = (
            {"client_name": "No redirect", "redirect_uris": []},
            {
                "client_name": "Implicit",
                "redirect_uris": ["https://client.example/callback"],
                "response_types": ["token"],
            },
            {
                "client_name": "Password grant",
                "redirect_uris": ["https://client.example/callback"],
                "grant_types": ["password"],
            },
        )
        for metadata in invalid_clients:
            with self.subTest(metadata=metadata):
                with self.assertRaises(ValueError):
                    oauth._validate_client_metadata(metadata)
