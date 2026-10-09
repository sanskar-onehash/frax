frappe.pages["frax-setup"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Connection Setup"),
    single_column: true,
  });
  const $root = $(frappe.render_template("frax_setup")).appendTo(page.body);
  const controller = new FraxMCPSetup($root, page);
  controller.bind();
  controller.refresh();
};

class FraxMCPSetup {
  constructor($root, page) {
    this.$root = $root;
    this.page = page;
    this.context = null;
  }

  bind() {
    this.$root.on("click", "[data-copy='endpoint']", () =>
      this.copy(this.context.mcp_url),
    );
    this.$root.on("click", "[data-copy='codex']", () =>
      this.copy(this.context.snippets.codex_cli),
    );
    this.$root.on("click", "[data-copy='claude']", () =>
      this.copy(this.context.snippets.claude_code),
    );
    this.$root.on("click", ".frax-generate-api", () => this.generate_api(false));
    this.$root.on("click", ".frax-rotate-api", () => this.generate_api(true));
    this.$root.on("click", ".frax-revoke-api", () => this.revoke_api());
    this.$root.on("click", ".frax-run-checks", (event) => {
      event.preventDefault();
      this.run_checks();
    });
    this.$root.on("click", ".frax-refresh-health", () => this.load_operations());
    this.$root.on("click", ".frax-export-diagnostics", () =>
      this.download_diagnostics(),
    );
  }

  async refresh() {
    const response = await frappe.call({
      method: "frax.setup.get_setup_context",
      type: "GET",
    });
    this.context = response.message;
    this.render();
  }

  render() {
    const context = this.context;
    const branding = context.branding;
    this.page.set_title(__("{0} Setup", [branding.product_name]));
    this.$root.find("[data-brand-title]").text(branding.display_title);
    const logo = branding.logo_url || branding.icon_url;
    this.$root
      .find("[data-brand-logo]")
      .attr({ src: logo || "", alt: branding.product_name })
      .toggleClass("hide", !logo);
    this.brand_link("[data-brand-doc]", branding.documentation_url);
    this.brand_link("[data-brand-support]", branding.support_url);
    const enabled = context.settings.enabled;
    this.$root
      .find(".frax-service-status")
      .html(this.badge(enabled ? __("Service enabled") : __("Service disabled"), enabled));
    this.$root.find(".frax-endpoint").text(context.mcp_url);
    this.$root.find(".frax-codex-command").text(context.snippets.codex_cli);
    this.$root.find(".frax-claude-command").text(context.snippets.claude_code);
    this.$root
      .find(".frax-api-state")
      .html(
        this.badge(
          context.api_token.api_key_exists
            ? __("API key exists")
            : __("No API key"),
          context.api_token.api_key_exists,
        ),
      );
    this.$root.find(".frax-generate-api").toggle(!context.api_token.api_key_exists);
    this.$root
      .find(".frax-rotate-api, .frax-revoke-api")
      .toggle(context.api_token.api_key_exists);
    this.$root
      .find(".frax-generate-api, .frax-rotate-api, .frax-revoke-api")
      .prop("disabled", !enabled || !context.settings.api_token_enabled);
    Object.entries(context.docs).forEach(([key, url]) =>
      this.$root.find(`[data-doc='${key}']`).attr("href", url),
    );
    const canViewOperations = Boolean(context.operations?.can_view);
    this.$root.find(".frax-operations").toggleClass("hide", !canViewOperations);
    if (canViewOperations) this.load_operations();
  }

  badge(text, good) {
    return `<span class="indicator-pill ${good ? "green" : "orange"}">${frappe.utils.escape_html(text)}</span>`;
  }

  brand_link(selector, url) {
    this.$root.find(selector).attr("href", url || "").toggleClass("hide", !url);
  }

  async generate_api(rotate) {
    const warning = rotate
      ? __("This immediately invalidates your existing API secret and may break other integrations using it.")
      : __("These credentials can use every platform API available to your account.");
    const password = await this.ask_password(
      rotate ? __("Rotate API secret") : __("Generate API credentials"),
      warning,
    );
    if (!password) return;
    const response = await frappe.call("frax.setup.generate_my_api_credentials", {
      password,
      rotate: rotate ? 1 : 0,
    });
    this.show_secret(__("API bearer token"), response.message.bearer_token);
    await this.refresh();
  }

  revoke_api() {
    frappe.confirm(
      __("Revoke your API key and secret? Any integration using them will stop immediately."),
      async () => {
        const password = await this.ask_password(
          __("Revoke API credentials"),
          __("Enter your current password to continue."),
        );
        if (!password) return;
        await frappe.call("frax.setup.revoke_my_api_credentials", { password });
        frappe.show_alert({ message: __("API credentials revoked"), indicator: "green" });
        await this.refresh();
      },
    );
  }

  ask_password(title, description) {
    return new Promise((resolve) => {
      const dialog = new frappe.ui.Dialog({
        title,
        fields: [
          {
            fieldname: "description",
            fieldtype: "HTML",
            options: `<p>${frappe.utils.escape_html(description)}</p>`,
          },
          {
            fieldname: "password",
            fieldtype: "Password",
            label: __("Current Password"),
            reqd: 1,
          },
        ],
        primary_action_label: __("Continue"),
        primary_action(values) {
          dialog.hide();
          resolve(values.password);
        },
      });
      dialog.$wrapper.on("hidden.bs.modal", () => resolve(null));
      dialog.show();
    });
  }

  show_secret(title, value) {
    const dialog = new frappe.ui.Dialog({
      title,
      fields: [
        {
          fieldname: "notice",
          fieldtype: "HTML",
          options: `<div class="alert alert-warning">${__("Copy this now. It will not be shown again automatically.")}</div>`,
        },
        {
          fieldname: "secret",
          fieldtype: "Small Text",
          label: title,
          read_only: 1,
          default: value,
        },
      ],
      primary_action_label: __("Copy"),
      primary_action: () => this.copy(value),
    });
    dialog.show();
  }

  copy(value) {
    if (value) frappe.utils.copy_to_clipboard(value);
  }

  async load_operations() {
    const $state = this.$root
      .find(".frax-health-state")
      .removeClass("text-danger")
      .addClass("text-muted")
      .text(__("Loading operational health…"));
    this.$root.find(".frax-health-content").addClass("hide");
    this.$root.find(".frax-refresh-health").prop("disabled", true);
    try {
      const response = await frappe.call({
        method: "frax.operations.get_operational_health",
        type: "GET",
        args: { days: 7 },
      });
      this.render_operations(response.message);
    } catch (error) {
      $state
        .removeClass("text-muted")
        .addClass("text-danger")
        .text(error.message || __("Could not load operational health."));
    } finally {
      this.$root.find(".frax-refresh-health").prop("disabled", false);
    }
  }

  render_operations(health) {
    const totals = health.totals || {};
    this.$root.find("[data-health='calls']").text(this.number(totals.calls));
    this.$root
      .find("[data-health='success-rate']")
      .text(`${this.number(totals.success_rate_percent)}%`);
    this.$root.find("[data-health='errors']").text(this.number(totals.errors));
    this.$root
      .find("[data-health='average-latency']")
      .text(`${this.number(totals.average_duration_ms)} ms`);
    this.render_health_rows(
      ".frax-slow-tools",
      health.slow_tools,
      (row) => [row.tool, __(`{0} ms average`, [this.number(row.average_ms)])],
      __("No calls in this period."),
    );
    this.render_health_rows(
      ".frax-failures",
      health.failures,
      (row) => [
        row.tool,
        __(`{0} · {1} occurrences`, [row.error_class, this.number(row.calls)]),
      ],
      __("No failures in this period."),
    );
    this.$root
      .find(".frax-health-state")
      .text(
        health.available
          ? __("Showing the last {0} days.", [health.window.days])
          : __("Audit data is not available yet."),
      );
    this.$root.find(".frax-health-content").removeClass("hide");
  }

  render_health_rows(selector, rows = [], values, emptyText) {
    const html = rows.length
      ? rows
          .map((row) => {
            const [label, detail] = values(row);
            return `<div class="frax-health-row"><span>${frappe.utils.escape_html(label)}</span><small>${frappe.utils.escape_html(detail)}</small></div>`;
          })
          .join("")
      : `<div class="text-muted">${frappe.utils.escape_html(emptyText)}</div>`;
    this.$root.find(selector).html(html);
  }

  number(value) {
    return Number(value || 0).toLocaleString();
  }

  async download_diagnostics() {
    const $button = this.$root.find(".frax-export-diagnostics").prop("disabled", true);
    try {
      const response = await frappe.call({
        method: "frax.operations.get_diagnostic_export",
        type: "GET",
        args: { days: 7 },
      });
      const blob = new Blob([JSON.stringify(response.message, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const serverName = this.context.branding.server_name || "frax";
      link.href = url;
      link.download = `${serverName}-diagnostics-${frappe.datetime.get_today()}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      $button.prop("disabled", false);
    }
  }

  async run_checks() {
    const $output = this.$root.find(".frax-diagnostics").html(__("Running checks…"));
    const checks = [];
    const run = async (label, fn) => {
      try {
        checks.push({ label, ok: true, detail: await fn() });
      } catch (error) {
        checks.push({ label, ok: false, detail: error.message || String(error) });
      }
    };
    await run(__("Protected-resource metadata"), async () => {
      const response = await fetch("/.well-known/oauth-protected-resource", {
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok || data.resource !== this.context.mcp_url)
        throw new Error(__("Endpoint metadata does not match"));
      return __("Resource URL matches");
    });
    await run(__("Authorization-server metadata"), async () => {
      const response = await fetch("/.well-known/oauth-authorization-server", {
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok || !data.authorization_endpoint || !data.token_endpoint)
        throw new Error(__("OAuth endpoints are missing"));
      return __("Authorization and token endpoints found");
    });
    await run(__("Automatic client registration"), async () => {
      const response = await fetch("/.well-known/oauth-authorization-server", {
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok || !data.registration_endpoint)
        throw new Error(__("Registration endpoint is missing"));
      return __("Available");
    });
    await run(__("CORS preflight"), async () => {
      const response = await fetch(this.context.mcp_url, {
        method: "OPTIONS",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(__("HTTP {0}", [response.status]));
      return __("HTTP {0}", [response.status]);
    });

    let rpcId = 1;
    const rpc = async (method, params = {}) => {
      const response = await fetch(this.context.mcp_url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "MCP-Protocol-Version": "2025-03-26",
          "X-Frappe-CSRF-Token": frappe.csrf_token,
        },
        body: JSON.stringify({ jsonrpc: "2.0", id: rpcId++, method, params }),
      });
      const text = await response.text();
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 180)}`);
      const data = JSON.parse(text);
      if (data.error) throw new Error(data.error.message || __("MCP error"));
      return data.result;
    };
    await run(__("MCP initialize"), async () => {
      const result = await rpc("initialize", {
        protocolVersion: "2025-03-26",
        capabilities: {},
        clientInfo: { name: "frax-setup-check", version: "1.0" },
      });
      return `${result.serverInfo?.name || "frax"} · ${result.protocolVersion}`;
    });
    await run(__("MCP ping"), async () => {
      await rpc("ping");
      return __("Responded");
    });
    await run(__("Tools list"), async () => {
      const result = await rpc("tools/list");
      return __("{0} tools", [result.tools?.length || 0]);
    });
    await run(__("Prompts list"), async () => {
      const result = await rpc("prompts/list");
      return __("{0} prompts", [result.prompts?.length || 0]);
    });
    $output.html(
      checks
        .map(
          (check) =>
            `<div class="frax-check"><span>${check.ok ? "✓" : "✕"} ${frappe.utils.escape_html(check.label)}</span><span class="text-${check.ok ? "success" : "danger"}">${frappe.utils.escape_html(check.detail)}</span></div>`,
        )
        .join(""),
    );
  }
}
