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

## Release compatibility gate

Compatibility is verified with three disposable-site profiles on each supported
branch. A stock site alone is not sufficient evidence for customized deployments.

| Profile | Installed applications | Automated evidence |
| --- | --- | --- |
| `core` | Frappe and Frax | Installation/defaults, setup context, OAuth/unit coverage, MCP schemas, document permissions, report queries, audit aggregation, and redacted diagnostics |
| `business` | Matching Frappe, ERPNext, and Frax majors | Core evidence plus business-application detection and business-tool exposure |
| `customized` | Business profile with test customizations | Business evidence plus live Tab/Section/Column Break ordering and Select-option metadata |

The branch itself is part of the gate: `main` fails against any framework major other
than v15, and `version-16` fails against any major other than v16. When ERPNext is
installed, its major must match the framework branch.

Prepare a disposable site with tests enabled, install the profile's applications, and
apply migrations:

```bash
bench --site <test-site> migrate
./apps/frax/scripts/run_compatibility_tests.sh \
  <bench-directory> <test-site> core
```

Run the same command with `business` and `customized` on their respective disposable
sites. The runner executes the full Frax test application, including the compatibility
release gate. Never use a production site: the customized profile creates and removes
test metadata and all profiles create transactional test records.

### Customized-site acceptance

Synthetic tests cannot prove compatibility with a customer's proprietary hooks,
workflows, scripts, overrides, reports, or integrations. Before releasing to a
customized site, run the following on a staging clone with a least-privilege test user:

1. Complete OAuth discovery, dynamic registration, browser authorization/PKCE, refresh,
   and reconnect from a supported real MCP client.
2. Verify one allowed and one denied read, write, report, and workflow action.
3. Exercise a representative custom field, form layout, Client Script, Server Script,
   Workflow, Report, and overridden method or hook where present.
4. Verify one domain transaction mapping in draft mode and inspect its normal app hooks,
   permissions, and validations; do not submit or post ledgers as a smoke test.
5. Confirm the operational-health panel aggregates the calls and that its downloaded
   diagnostic file contains no actors, arguments, document identifiers, error messages,
   secrets, or private app names.
6. Record the branch commit, framework/application versions, profile, site customization
   revision, test user, results, and approved exceptions as release evidence.
