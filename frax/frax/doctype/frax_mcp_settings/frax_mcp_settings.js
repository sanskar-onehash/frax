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
  },
});
