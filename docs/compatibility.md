# v15 and v16 compatibility

Frax maintains separate release branches because authentication and several native
application APIs differ between framework generations:

- `main` targets Frappe and ERPNext v15.
- `version-16` targets Frappe and ERPNext v16.

Both branches expose the same Frax endpoint, setup experience, tool identifiers,
default OneHash presentation, administrator controls, and response envelopes.

## OAuth behavior

Users connect with only the MCP endpoint on both branches.

- v15 uses Frax's compatibility implementation for OAuth discovery, RFC 7591 dynamic
  client registration, and the framework's authenticated token exchange.
- v16 defers to the framework's native discovery, dynamic client registration, public
  clients, and PKCE implementation.

OAuth discovery, dynamic registration, and API-token authentication are enabled by
default. Administrators can disable OAuth or API tokens independently in **Frax MCP
Settings**. On v16, disabling dynamic client registration in the framework's OAuth
Settings is an additional site-level override; the setup page's connection checks
report that condition.

## Native API adapters

Frax probes installed applications and imports domain APIs only when their category is
used. The v16 branch contains narrow adapters for known framework changes, including
module discovery and the v16 Payment Entry helper signature. Business calculations,
document mapping, report execution, permissions, hooks, and workflows remain owned by
the installed applications.

## Upgrade and verification

After changing Frax branches or upgrading the framework:

```bash
bench --site <site> migrate
bench --site <site> clear-cache
```

Then open **Connection Setup**, run its read-only checks, and test with a dedicated
least-privilege System User. On customized sites, verify representative reads and
writes against custom fields, permissions, workflows, Server Scripts, reports, and
method overrides before production use.

Site-backed automated tests require a disposable site with Frax installed and tests
enabled:

```bash
bench --site <test-site> run-tests --app frax
```
