from __future__ import annotations

from frappe_mcp.server.types import PromptMessage, TextContent

from frax.context import OPERATOR_CONTEXT
from frax.mcp import mcp


APP_SOURCE_CONTEXT = """Use this for app-specific behavior, source inspection, hooks, controllers, fixtures, patches, and app/source correlation.

App model:

- A Frappe app is a Python package installed into a site. Apps contribute modules, DocType JSON, controllers, client/list JS, reports, pages, workspaces, dashboards, print formats, web forms, notifications, hooks, fixtures, patches, assets, templates, and whitelisted methods.
- Frappe is the framework. ERPNext and other apps are domain behavior. Never infer Frappe core behavior from one domain app.
- Apps can customize other apps through fixtures, exported customizations, Custom Fields, Property Setters, Custom DocPerm, hooks, overrides, assets, and whitelisted methods.
- Installed app order can affect hooks and overrides.

Inspection order:

1. List installed apps and app order.
2. Identify app version, branch/tag/commit, remote URL, source availability, and package-relative root.
3. Inspect hooks summary: doc events, scheduler events, fixtures, overrides, permission hooks, assets/includes, Jinja hooks, and whitelisted/API surfaces.
4. For a DocType, inspect standard JSON, child DocTypes, controller class, inherited controllers/base classes, client/list JS, and exported customizations from any installed app.
5. Compare source behavior with live metadata: Custom Fields, Property Setters, Custom DocPerm, Workflows, Client Scripts, Server Scripts, Reports, Settings, and permissions.
6. Inspect patches/migration state when fields are missing, entities were renamed, behavior changed across versions, or source and live metadata disagree.

Rules:

- Expose package-relative source pointers by default, not absolute server paths.
- If source is private, missing, unavailable, or version metadata is uncertain, say that and rely on live metadata plus user confirmation.
- Do not dump source into prompts; use source pointers and targeted reads.
- Controller inheritance can carry important business behavior. Do not stop at the immediate controller for submittable or transactional DocTypes."""


NATIVE_UI_CONTEXT = """Use this for dashboards, KPIs, reports, tables, navigation, forms, prints, email output, and Desk/portal surfaces.

Native solution map:

- Dashboard/KPI: Workspace, Dashboard Chart, Number Card, Report.
- Data table/export/list: List View, Report Builder, Query Report, Script Report.
- Navigation hub: Workspace, shortcuts, quick lists, Page only if necessary.
- External or semi-external intake: Web Form, portal route, DocType permissions.
- Print/output: Print Format.
- Email/message output: Email Template, Notification, Email Queue, Email Account.
- Process status: Workflow, status fields, ToDo/Assignment, Notification.
- Form UI behavior: DocType metadata, Custom Field, Property Setter, Client Script, app JS.

Inspection order:

1. Inspect target process/DocType metadata, permissions, child tables, Singles/virtual/tree/submittable flags, and relevant Settings DocTypes.
2. Inspect existing Reports, Dashboard Charts, Number Cards, Workspaces, Pages, Web Forms, Print Formats, Email Templates, and Notifications for the same process/DocType.
3. Inspect report/chart/card source type: DocType-backed, Report-backed, custom-source/custom-method, Query Report, Script Report, or Report Builder.
4. Inspect public/hidden/user-specific flags and reference DocType permissions.
5. Inspect Client Scripts, Server Scripts, permission query scripts, User Permissions, and Workflows that could change visible data or metrics.

Rules:

- Do not create outside-the-system artifacts when native Desk/portal records satisfy the request.
- Use Report Builder for simple field/filter tables, Query Report for safe parameterized SQL, and Script Report for business logic, joins, permission-aware computation, charts, or summaries.
- Treat custom-source charts and custom-method cards as code-backed behavior, not simple metadata.
- Keep metric and process names redacted by default if they reveal private business operations."""


HIGH_RISK_WRITE_CONTEXT = """Use this before material writes, destructive actions, submit/cancel/amend, update-after-submit, financial/accounting, stock, asset, purchase, fee/discount, integration, permission, workflow, naming, or business-critical operations.

Risk model:

- Frappe document writes are behaviorful. They can trigger validations, link checks, mandatory checks, permissions, workflow transitions, docstatus changes, child-table sync, versions, notifications, global search, controllers, inherited controllers, hooks, Server Scripts, Assignment rules, webhooks, background jobs, and integrations.
- Submittable transaction DocTypes can update ledgers, stock bins, valuations, linked document status, billing percentages, outstanding amounts, comments, emails, compliance records, and downstream records.

Preflight inspection:

1. Target DocType merged metadata, including fields, child tables, `issingle`, `istable`, `is_virtual`, `is_tree`, `is_submittable`, and `allow_on_submit`.
2. Current document state, `docstatus`, owner, modified timestamp, links, and child rows.
3. Standard DocPerm, Custom DocPerm, field permlevels, User Permissions, shares, and acting user roles.
4. Active Workflow, allowed transitions, transition roles, transition conditions, state/docstatus effects, and current allowed actions.
5. Controller lifecycle methods, inherited controllers, `doc_events`, hooks, Server Scripts, Client Scripts, notifications, naming/autoname, Document Naming Rules, and relevant Settings DocTypes.
6. Linked records and downstream side effects, especially ledgers, stock, assets, accounting, approvals, integrations, and email.
7. Idempotency and rollback/repair plan.

Write rules:

- Prefer normal document APIs and app public methods.
- Prefer workflow actions over direct workflow-state edits.
- Avoid direct SQL, `db_set`, `db_update`, `ignore_permissions=True`, and permission bypasses except for explicit administrative repair.
- Ask for confirmation before material/high-risk writes unless the user already authorized the exact action and tool policy permits it.
- If facts are missing, stop and inspect; do not invent fieldnames, states, roles, or child tables."""


PERMISSION_WORKFLOW_CONTEXT = """Use this for permission failures, missing records, restricted lists, workflow buttons/actions, role issues, shares, and effective-access debugging.

Permission layers:

- Current user and roles.
- Standard DocPerm and Custom DocPerm.
- Field `permlevel`, read/write permissions, owner restrictions, and `if_owner`.
- User Permissions restricting linked values.
- DocShare grants.
- Workflow state, transition roles, transition conditions, and docstatus.
- Controller permission methods and hook permission methods.
- Permission Query scripts and app-level query conditions.
- Broad/public-like roles and portal/website access where relevant.

Debug flow:

1. Identify acting user, target DocType/document, requested operation, current document state, and expected behavior.
2. Inspect merged DocType permissions and Custom DocPerm.
3. Inspect field permlevels for the fields involved.
4. Inspect User Permissions and linked fields that could scope records.
5. Inspect DocShare if document-level access differs from list access.
6. Inspect Workflow, transitions, roles, conditions, and current allowed actions.
7. Inspect permission query scripts, hooks, controller checks, and Server Scripts.
8. Compare list/read/write/submit/cancel/delete separately; they can differ.

Rules:

- Do not recommend permission bypass first.
- Prefer Role Permission Manager, Custom DocPerm, User Permissions, workflow transition roles, shares, or settings before scripts.
- Treat permission query Server Scripts as high-impact because they alter visibility at query time."""


RESTRICTED_SCRIPTING_CONTEXT = """Use this when writing or reviewing Frappe Server Scripts, API Server Scripts, Permission Query scripts, Scheduler scripts, Email Templates, Print Formats, or other Frappe Jinja templates.

Server Script execution:

- Server Scripts are disabled unless `server_script_enabled` is enabled in common site config.
- Saving Server Script requires Script Manager permission.
- Frappe validates by compiling with RestrictedPython and Frappe's `FrappeTransformer`.
- Script types are `DocType Event`, `Scheduler Event`, `Permission Query`, and `API`.
- DocType Event scripts run through `safe_exec(..., _locals={"doc": doc}, restrict_commit_rollback=True)`. They receive `doc`; `frappe.db.commit`, `frappe.db.rollback`, and `frappe.db.add_index` are removed.
- Scheduler scripts sync to Scheduled Job Type and run through safe_exec.
- Permission Query scripts receive `user` and should set `conditions`.
- API scripts can allow guest access and rate limiting; return data by setting values on `frappe.flags`.
- `frappe.call` can call whitelisted functions or API Server Scripts through Frappe's command handler.

Restricted Python rules:

- This is not normal Python. Do not use imports or arbitrary modules.
- Do not access private/underscore attributes or keys.
- Do not use unsafe attributes such as `.format`, `.format_map`, frame/code/traceback/generator/coroutine internals.
- Do not write to modules, classes, functions, methods, code objects, tracebacks, or frames.
- Avoid augmented assignment such as `+=` and `-=` because Frappe's safe globals do not expose normal unrestricted inplace behavior.
- Prefer simple assignment, explicit temporary variables, straightforward loops, list/dict literals, and safe Frappe APIs.
- Read SQL is limited to SELECT/EXPLAIN or read-only WITH where supported. Do not write SQL.

Safe globals include:

- Top-level: `json`, `as_json`, `dict`, `log`, `_dict`, `args`, `_`, `scrub`, `html2text`, `style`, `get_toc`, `get_next_link`, `FrappeClient`, `run_script`, `is_job_queued`, `get_visible_columns`.
- Builtins: `abs`, `all`, `any`, `bool`, `dict`, `enumerate`, `isinstance`, `issubclass`, `list`, `max`, `min`, `range`, `set`, `sorted`, `sum`, `tuple`.
- `frappe`: `call`, `flags`, `format`, `format_value`, `date_format`, `time_format`, `format_date`, `form_dict`, `bold`, `copy_doc`, `errprint`, `qb`, `get_meta`, `new_doc`, `get_doc`, `get_mapped_doc`, `get_last_doc`, `get_cached_doc`, `get_list`, `get_all`, `get_system_settings`, `rename_doc`, `delete_doc`, `utils`, `get_url`, `render_template`, `msgprint`, `throw`, `sendmail`, `get_print`, `attach_print`, `user`, `get_fullname`, `get_gravatar`, `full_name`, `request`, `session`, `make_get_request`, `make_post_request`, `make_put_request`, `make_patch_request`, `make_delete_request`, `socketio_port`, `get_hooks`, `enqueue`, `sanitize_html`, `log_error`, `log`, `db`, `lang`, Frappe exception classes, and `response` when present.
- `frappe.db`: `get_list`, `get_all`, `get_value`, `set_value`, `get_single_value`, `get_default`, `exists`, `count`, `escape`, read-only `sql`, and transaction hooks. In DocType Event scripts, commit/rollback/add_index are removed.
- `frappe.utils`: curated date/time, numeric, money, HTML, markdown, URL, filter, formatting, and hashing helpers such as `getdate`, `nowdate`, `today`, `add_days`, `date_diff`, `flt`, `cint`, `cstr`, `fmt_money`, `money_in_words`, `escape_html`, `strip_html`, `get_url_to_form`, and `generate_hash`.

Jinja behavior:

- Frappe Jinja uses `SandboxedEnvironment` with `DebugUndefined`.
- The Jinja environment loads Frappe `get_safe_globals()` and then app-provided Jinja hook methods/filters from `hooks.py`.
- Default filters include `json`, `len`, `int`, `str`, and `flt`.
- `frappe.render_template(..., safe_render=True)` rejects template strings containing `.__`.
- Email Templates validate Jinja syntax and render subject/body with the passed document/context.
- Keep Jinja declarative. Do not write Python Server Script logic in templates. Inspect available document fields first.

Standard practice:

- Prefer app code for complex, durable, tested behavior.
- Use Server Script for small site-local behavior only after checking settings, metadata, workflow, notification, and app hooks.
- Use Email Template/Print Format Jinja for presentation/output, not business mutation.
- If a script/template fails, check restricted syntax first before inventing custom workarounds."""


REQUIREMENT_MAPPING_CONTEXT = """Use this for broad process questions, such as "how is this flow implemented?", "create a dashboard for this process", "add an approval", or "automate this business step".

Build a redacted requirement-to-system map. Inspect the process family, not only one DocType.

Separate layers:

- Source-backed layer: installed apps, owner apps, controllers, hooks, reports, workspaces, fixtures, integrations, UI/theme apps, and app settings.
- Site-configured layer: Custom Fields, Property Setters, Workflows, Client Scripts, Server Scripts, Custom DocPerm, User Permissions, Document Naming Rules, Notifications, Web Forms, Reports, Charts, Cards, Workspaces, Print Formats, Email Templates, Settings DocTypes, and shares.
- Flow chain: intake/capture, validation/defaulting, conversion/linking, workflow-governed stages, approval gates, financial/fee/discount automation, final record creation, reporting/navigation/communication.
- Risk layer: submitted documents, permission bypass scripts, external calls, amount math, naming exceptions, workflow docstatus effects, broad permissions, and integration side effects.

Generic patterns are only examples:

- Intake/admissions-like flows often use forms or CRM-like records, scripts for normalization/linking/downstream creation, workflow-governed stages, notifications, reports, dashboards, workspaces, web forms, and permissions.
- Purchase approval often combines standard Purchase DocTypes with live workflow, conditions, docstatus effects, custom fields/setters, scripts, permissions, notifications, reports, workspaces, charts, and naming exceptions.
- Fee/discount behavior often combines ERP/domain primitives with site fields and scripts for amount math, linking/updating, permissions, reports, and notifications.
- Stock/assets often combine source-backed stock/asset DocTypes with live fields, scripts, naming rules, reports, workspaces, permissions, and ledger/valuation/ownership/depreciation side effects.

Rules:

- Verify the exact site. Do not convert examples into assumptions.
- Prefer the lowest native Frappe layer that fits, then move upward only when needed.
- Redact private data by default. Return categories, counts, risk flags, and native artifact types unless exact names are needed for an authorized operation."""


def _message(text: str, task: str | None = None) -> list[PromptMessage]:
    if task:
        text = f"{text}\n\nCurrent task:\n{task}"
    return [PromptMessage(role="user", content=TextContent(text=text))]


def register():
    return None


@mcp.prompt(
    name="frax_frappe_operator",
    description="Compact operating rules for working Frappe-natively with Frax.",
)
def frappe_operator(task: str | None = None):
    return _message(OPERATOR_CONTEXT, task)


@mcp.prompt(
    name="frax_frappe_app_source_inspection",
    description="Inspect app source, hooks, controllers, fixtures, patches, and source/live behavior boundaries.",
)
def frappe_app_source_inspection(task: str | None = None):
    return _message(APP_SOURCE_CONTEXT, task)


@mcp.prompt(
    name="frax_frappe_native_ui",
    description="Choose native Frappe Reports, Dashboards, Workspaces, Web Forms, Print Formats, Email Templates, and Notifications.",
)
def frappe_native_ui(task: str | None = None):
    return _message(NATIVE_UI_CONTEXT, task)


@mcp.prompt(
    name="frax_frappe_high_risk_write",
    description="Preflight discipline for material, destructive, submittable, accounting, stock, asset, permission, workflow, naming, and integration-sensitive writes.",
)
def frappe_high_risk_write(task: str | None = None):
    return _message(HIGH_RISK_WRITE_CONTEXT, task)


@mcp.prompt(
    name="frax_frappe_permission_workflow_debug",
    description="Debug Frappe permissions, User Permissions, shares, workflow states, transition buttons, and effective access.",
)
def frappe_permission_workflow_debug(task: str | None = None):
    return _message(PERMISSION_WORKFLOW_CONTEXT, task)


@mcp.prompt(
    name="frax_frappe_restricted_scripting",
    description="Rules for writing Frappe Server Scripts and Jinja templates in the restricted Frappe environment.",
)
def frappe_restricted_scripting(task: str | None = None):
    return _message(RESTRICTED_SCRIPTING_CONTEXT, task)


@mcp.prompt(
    name="frax_frappe_requirement_mapping",
    description="Map a business/process requirement to source-backed apps, live customizations, native surfaces, and risk layers.",
)
def frappe_requirement_mapping(task: str | None = None):
    return _message(REQUIREMENT_MAPPING_CONTEXT, task)
