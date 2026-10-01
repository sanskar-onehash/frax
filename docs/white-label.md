# White-label configuration

The connection works without any branding configuration. Its defaults are:

- software and platform name: `OneHash`
- MCP server identifier: `frax`
- disclosure policy: `strict`

Site-specific values are optional. Add only the overrides you need under
`frax_branding` in the site's `site_config.json`:

```json
{
  "frax_branding": {
    "product_name": "Acme Business",
    "platform_name": "Acme Platform",
    "display_title": "Acme Assistant",
    "server_name": "acme",
    "disclosure_mode": "strict",
    "logo_url": "/assets/acme/images/logo.svg",
    "icon_url": "https://assets.example.com/icon.svg",
    "support_url": "https://support.example.com",
    "documentation_url": "https://docs.example.com",
    "operator_wording": "Use our approved terminology for customer-facing replies."
  }
}
```

`strict` instructs the agent to keep underlying framework, vendor application,
package, and integration identities out of user-facing answers. Exact internal
identifiers remain available for silent tool calls so operations continue to work.

`contextual` still uses the configured brand by default, but permits exact technical
names when an administrator explicitly needs them for diagnostics, code, or setup.

Configured logo and icon values may be root-relative asset paths or HTTP(S) URLs.
Documentation and support values must be HTTP(S) URLs. Invalid values safely fall
back to the defaults above.
