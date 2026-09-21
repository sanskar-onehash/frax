frappe.ui.form.on("Frax MCP Settings", {
  refresh(frm) {
    frm.add_custom_button(__("Open Frax Setup"), () =>
      frappe.set_route("frax-setup"),
    );
    frm.add_custom_button(__("Manage MCP Access"), () => {
      frappe
        .set_route("Form", "Role Permission for Page and Report")
        .then(() => {
          if (cur_frm?.doctype !== "Role Permission for Page and Report")
            return;
          cur_frm
            .set_value("set_role_for", "Page")
            .then(() => cur_frm.set_value("page", "frax-setup"));
        });
    });
    frm.add_custom_button(
      __("Enable Recommended"),
      () => set_categories(frm, {
        enable_core_tools: 1,
        enable_context_tools: 1,
        enable_customization_tools: 0,
        enable_reporting_tools: 1,
        enable_business_tools: frappe.boot.versions?.erpnext ? 1 : 0,
      }),
      __("Tool Controls"),
    );
    frm.add_custom_button(
      __("Enable All"),
      () => set_categories(frm, Object.fromEntries(category_fields.map((field) => [field, 1]))),
      __("Tool Controls"),
    );
    frm.add_custom_button(
      __("Open Audit Log"),
      () => frappe.set_route("List", "Frax MCP Audit Log"),
      __("Tool Controls"),
    );

    const endpoint = `${window.location.origin}/api/method/frax.mcp.handle_mcp`;
    frm.fields_dict.status_html.$wrapper.html(`
			<div class="alert alert-info">
				<div><strong>${__("MCP Endpoint")}</strong></div>
				<code>${frappe.utils.escape_html(endpoint)}</code>
				<p class="mt-2 mb-0">${__(
          "Access is controlled by the roles assigned to the Frax Setup Page. OAuth clients and local callback ports are created per user on that page.",
        )}</p>
			</div>
		`);
    render_category_summary(frm);
  },
  enable_core_tools: render_category_summary,
  enable_context_tools: render_category_summary,
  enable_customization_tools: render_category_summary,
  enable_reporting_tools: render_category_summary,
  enable_business_tools: render_category_summary,
});

const category_fields = [
  "enable_core_tools",
  "enable_context_tools",
  "enable_customization_tools",
  "enable_reporting_tools",
  "enable_business_tools",
];

const category_labels = {
  enable_core_tools: __("Core"),
  enable_context_tools: __("Context and inspection"),
  enable_customization_tools: __("Customization"),
  enable_reporting_tools: __("Reporting"),
  enable_business_tools: __("Business operations"),
};

function set_categories(frm, values) {
  return frm.set_value(values).then(() => {
    render_category_summary(frm);
    frappe.show_alert({ message: __("Review and save the settings to apply these tool controls."), indicator: "blue" });
  });
}

function render_category_summary(frm) {
  if (!frm.fields_dict.category_summary_html) return;
  const enabled = category_fields.filter((field) => frm.doc[field]);
  const labels = enabled.map((field) => category_labels[field]);
  const warning = frm.doc.enable_core_tools
    ? ""
    : `<div class="text-warning mt-2">${__("Core tools are disabled. Users will not be able to perform general document operations.")}</div>`;
  frm.fields_dict.category_summary_html.$wrapper.html(`
    <div class="alert alert-${enabled.length ? "info" : "warning"}">
      <strong>${__("Enabled for MCP users:")}</strong>
      ${frappe.utils.escape_html(labels.join(", ") || __("No tool categories"))}
      ${warning}
    </div>
  `);
}
