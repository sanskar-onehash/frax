## Frax

Model Context Protocol (MCP) server for ERP automation and AI integration.

### MCP setup

After installing or upgrading Frax, run `bench --site <site> migrate`. A System Manager can then open **Frax MCP Settings** to:

- enable or disable the MCP service, OAuth, and API-token authentication independently;
- choose allowed roles from the **Allowed Roles** multi-select;
- enable or disable tool categories and set result, download, and audit-retention limits.

Leaving **Allowed Roles** empty permits every System User; normal user, role, document, workflow, and user-permission rules still apply. Administrator is always permitted. An allowed user can open `/app/frax-setup` to copy the exact Streamable HTTP endpoint, copy client commands, manage their own API-token fallback, and run read-only connection checks.

The endpoint is:

```text
https://<your-site>/api/method/frax.mcp.handle_mcp
```

OAuth is recommended. A compatible client registers itself from the site's OAuth metadata, then opens the browser for sign-in and authorization. Users normally provide only the endpoint—no client ID, client secret, callback port, or setup-page password. v15 supplies the missing discovery and dynamic-registration compatibility routes; v16 uses the framework's native OAuth discovery, public-client PKCE, and dynamic registration.

The API-token fallback creates or rotates credentials only for the signed-in user. Its bearer value is:

```text
<API_KEY>:<API_SECRET>
```

These are normal Frappe API credentials, not MCP-only credentials. They can access every Frappe API permitted to that user, so use a least-privilege user and revoke the credentials when they are no longer required.

Client references:

- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [Claude custom connectors](https://support.anthropic.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [Codex MCP](https://developers.openai.com/codex/mcp)

#### Defaults and upgrades

The service, OAuth, API-token fallback, and all tool categories default to enabled on both supported branches. No `site_config.json` entry is required. After migration, review **Allowed Roles**, disable any categories the site does not need, and use the setup page's connection checks before distributing the endpoint.

### Reliability, reporting, and ERPNext

Frax exposes bounded query/count/batch-read tools, native Link search, attachments, PDFs, assignments, tags, reporting-artifact validation, Report Builder previews, and saved-report execution. Responses use a consistent `data`, `meta`, `warnings`, and `links` shape where appropriate. MCP Apps-capable clients can render document lists, details, and reports inline; other clients receive the same JSON/text result.

Server Script writes are compiled against the installed Frappe restricted-Python runtime before saving. Diagnostics are warnings-only and call out unavailable imports/private attributes, document-event transaction calls, direct database writes, `update_modified=False`, and recursive event saves. This intentionally guides developers without introducing a separate developer mode.

When ERPNext is installed, **Business Operations Tools** add native helpers for item and party details, stock balance, fiscal year/exchange rate, common transaction mappings, and draft Payment Entries. Frax uses ERPNext's own methods and the acting user's permissions; it does not duplicate ERPNext's business logic. Sites without the owning application do not advertise these tools.

Write and destructive tools publish MCP risk/confirmation annotations and still execute through normal permissions, validations, workflows, hooks, and document APIs. They do not require the user to leave their current client for a second approval screen. Tool calls are recorded in **Frax MCP Audit Log** with redacted arguments, outcome, duration, and affected-document information where available.

Tool categories and limits are configured in **Frax MCP Settings**. Core, context/inspection, customization, reporting, and business operations are enabled by default. Disabled categories are both hidden from discovery and blocked at execution time.

More detail:

- [Business tools](docs/business-tools.md)
- [Reporting and MIS tools](docs/reporting.md)
- [v15/v16 compatibility](docs/compatibility.md)

### White-label configuration

Branding works without configuration: the default software/framework name is **OneHash**, the MCP server identifier is `frax`, and strict implementation-name disclosure is enabled. For a special deployment, add only the required overrides under `frax_branding` in the site's `site_config.json`:

```json
{
  "frax_branding": {
    "product_name": "OneHash Assist",
    "display_title": "OneHash ERP Assistant",
    "server_name": "onehash-erp",
    "logo_url": "https://example.com/logo.svg",
    "support_url": "https://example.com/support",
    "documentation_url": "https://example.com/docs",
    "operator_wording": "Use the company's approved reporting terminology."
  }
}
```

Branding changes setup presentation and MCP `serverInfo` metadata. The endpoint, `frax_*` tools, internal DocTypes, and audit identity remain stable for compatibility. HTTP(S) is required for configured URLs; invalid values fall back safely.

See [white-label configuration](docs/white-label.md) for every supported field and disclosure mode.

### Compatibility

The `main` branch targets Frappe/ERPNext v15 and `version-16` targets v16. Run `bench --site <site> migrate` after installing or upgrading, then use the setup page's read-only connection checks. Test customized sites with their own roles, workflows, scripts, reports, and overrides before enabling write tools in production.

#### License

mit
