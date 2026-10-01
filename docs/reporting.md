# Reporting and MIS tools

Reporting tools use the platform's native Reports, Dashboard Charts, Number Cards,
and Workspaces. They do not introduce a separate analytics database or dashboard
format.

The tool set provides four workflows:

1. Inspect the readable fields and existing reporting surfaces for a business
   DocType.
2. Preview a bounded Report Builder-style query before saving anything.
3. Run an existing saved report with its native report roles and reference-DocType
   permissions.
4. Validate, create, or update non-standard reporting artifacts.

Report results use the configured default and maximum page sizes. Responses include
columns, charts, report summaries, execution metadata, and a `has_more` indicator.
Prepared-report behavior is never bypassed by MCP.

## Administrative safeguards

- Standard and source-backed artifacts cannot be created or overwritten.
- Updates require the exact `modified` timestamp observed by the agent.
- Native create/write permissions and document validation still run.
- Saving requires System Manager or Report Manager access.
- Filter, grouping, aggregate, and order fields are checked against the user's
  permitted fields before a preview query runs.
- SQL reports accept only read-only query forms supported by the installed platform.
- Query and Script Reports require explicit allowed roles.
- Query Reports return a warning because SQL does not automatically apply
  document-level permission conditions; administrators must review their roles and
  query logic carefully.
- Script Report source is compiled with the installed restricted runtime before save.
- Invalid JSON used by reports, charts, cards, or workspaces is rejected during
  preflight validation.

For common receivable, payable, sales, purchasing, stock, and accounting MIS, prefer
running the installed standard reports with suitable filters. Create a new report only
when an existing report or Report Builder preview cannot express the requirement.
