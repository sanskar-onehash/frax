from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import frappe

try:
    from frappe.utils.modules import get_modules_from_all_apps_for_user
except ImportError:
    from frappe.config import get_modules_from_all_apps_for_user

from frax.tools.registry import annotations_for, frax_tool, get_tool_policies


def register():
    return None


@frax_tool(
    name="frax_list_apps",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List Installed Apps"),
)
def list_apps():
    """List installed apps with compact version, source, and hook context.

    Use first for app-aware work. Returns installed order plus package-relative source
    pointers and repository/version hints when available; does not expose absolute paths.
    """
    prepared_apps = []

    for index, app in enumerate(frappe.get_installed_apps(), start=1):
        app_hooks = frappe.get_hooks(app_name=app)
        source_info = _app_source_info(app)
        prepared_apps.append(
            {
                "name": app,
                "installed_order": index,
                "description": (app_hooks.get("app_description") or [""])[0],
                "version": app_hooks.get("app_version"),
                "source": source_info,
                "hook_summary": _hook_summary(app_hooks),
            }
        )

    return prepared_apps


@frax_tool(
    name="frax_list_app_modules",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List App Modules"),
)
def list_app_modules(app_name: str):
    """List modules belonging to an installed app.

    Use to narrow app exploration before listing DocTypes, reports, pages, or source paths.

    Args:
        app_name: Installed app name.
    """
    if not app_name:
        return frappe.throw("App name is required")

    return [
        module.get("module_name")
        for module in get_modules_from_all_apps_for_user()
        if module.get("app") == app_name
    ]


@frax_tool(
    name="frax_list_app_doctypes",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List App DocTypes"),
)
def list_app_doctypes(app_name: str, module: str | None = None):
    """List DocTypes belonging to an installed app or module.

    Returns compact DocType flags and package-relative source pointers. Use
    frax_get_document_meta or a context summary before writing to any listed DocType.

    Args:
        app_name: Installed app name.
        module: Optional module name within the app.
    """
    modules = _get_app_modules(app_name, module)
    if not modules:
        return []

    rows = frappe.get_all(
        "DocType",
        filters={"module": ["in", modules]},
        fields=["name", "module", "custom", "istable", "issingle", "is_submittable", "is_tree", "is_virtual"],
        order_by="module asc, name asc",
    )
    for row in rows:
        row["source"] = _doctype_source_pointer(app_name, row["module"], row["name"])
    return rows


@frax_tool(
    name="frax_list_app_reports",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List App Reports"),
)
def list_app_reports(app_name: str, module: str | None = None):
    """List reports belonging to an installed app or module.

    Use before creating new tables/analytics. Prefer existing native reports where possible.

    Args:
        app_name: Installed app name.
        module: Optional module name within the app.
    """
    modules = _get_app_modules(app_name, module)
    if not modules:
        return []

    rows = frappe.get_all(
        "Report",
        filters={"module": ["in", modules]},
        fields=["name", "module", "report_type", "ref_doctype", "is_standard"],
        order_by="module asc, name asc",
    )
    for row in rows:
        row["source"] = _record_source_pointer(app_name, row["module"], "report", row["name"])
    return rows


@frax_tool(
    name="frax_list_app_pages",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List App Pages"),
)
def list_app_pages(app_name: str, module: str | None = None):
    """List Desk pages belonging to an installed app or module.

    Use only when Workspace/Report/native surfaces are not enough or when inspecting
    existing app-provided Desk routes.

    Args:
        app_name: Installed app name.
        module: Optional module name within the app.
    """
    modules = _get_app_modules(app_name, module)
    if not modules:
        return []

    rows = frappe.get_all(
        "Page",
        filters={"module": ["in", modules]},
        fields=["name", "module", "title", "standard"],
        order_by="module asc, name asc",
    )
    for row in rows:
        row["source"] = _record_source_pointer(app_name, row["module"], "page", row["name"])
    return rows


@frax_tool(
    name="frax_list_tool_policies",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List Frax Tool Policies"),
)
def list_tool_policies():
    """List Frax tool risk metadata, confirmation flags, and server-enforced role requirements.

    `requires_confirmation` is advisory policy for MCP clients and human approval UX.
    Server-side enforcement currently covers role requirements and Frappe permissions,
    not a confirmation nonce.
    """
    return {
        "confirmation_enforcement": "client_human_in_loop",
        "server_enforced": ["roles", "frappe_permissions", "tool_input_schema"],
        "policies": get_tool_policies(),
    }


@frax_tool(
    name="frax_list_app_whitelisted_methods",
    risk="read",
    annotations=annotations_for("read", idempotent=True, title="List App Whitelisted Methods"),
)
def list_app_whitelisted_methods(app_name: str, module: str | None = None):
    """Discover app Python methods decorated with frappe.whitelist without importing modules.

    Returns package-relative source pointers, signatures, docstrings, whitelist options,
    and whether each method is explicitly declared in the app's frax_tools hook. This is
    read-only source inspection; calling methods is separate and higher risk.

    Args:
        app_name: Installed app name.
        module: Optional Frappe module name within the app.
    """
    app_path = Path(frappe.get_app_path(app_name)).resolve()
    module_path = _get_module_path(app_name, app_path, module) if module else app_path
    package_root = app_path.parent
    declared_frax_tools = set(frappe.get_hooks("frax_tools", app_name=app_name))

    methods = []
    for path in sorted(module_path.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        methods.extend(_find_whitelisted_methods(path, package_root, declared_frax_tools))

    return methods


def _get_app_modules(app_name: str, module: str | None = None) -> list[str]:
    modules = list_app_modules(app_name)
    if module is None:
        return modules

    if module not in modules:
        frappe.throw(f"Module {module} not found in app {app_name}.")

    return [module]


def _get_module_path(app_name: str, app_path: Path, module: str | None) -> Path:
    modules = _get_app_modules(app_name, module)
    if not modules or module is None:
        return app_path

    module_path = app_path / frappe.scrub(module)
    if not module_path.exists():
        frappe.throw(f"Module path not found for {module} in app {app_name}.")

    return module_path


def _find_whitelisted_methods(path: Path, package_root: Path, declared_frax_tools: set[str]) -> list[dict[str, Any]]:
    source_path = _relative_source_path(path, package_root)
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        return [{"source_path": source_path, "error": f"SyntaxError: {exc}"}]

    import_aliases = _get_whitelist_aliases(tree)
    module_name = _module_name(path, package_root)
    methods = []

    for parent, node in _iter_functions(tree):
        if not _has_whitelist_decorator(node, import_aliases):
            continue

        qualname = f"{parent}.{node.name}" if parent else node.name
        method = f"{module_name}.{qualname}"
        methods.append(
            {
                "method": method,
                "module": module_name,
                "function": qualname,
                "source_path": source_path,
                "line": node.lineno,
                "docstring": ast.get_docstring(node) or "",
                "signature": _signature_for(node),
                "whitelist": _whitelist_options(node, import_aliases),
                "callable_by_frax": method in declared_frax_tools,
                "reason": "declared in frax_tools" if method in declared_frax_tools else "not declared in frax_tools",
            }
        )

    return methods


def _get_whitelist_aliases(tree: ast.Module) -> set[str]:
    aliases = {"frappe.whitelist"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "frappe":
            for alias in node.names:
                if alias.name == "whitelist":
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "frappe":
                    aliases.add(f"{alias.asname or alias.name}.whitelist")
    return aliases


def _iter_functions(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield node.name, child
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield "", node


def _has_whitelist_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef, aliases: set[str]) -> bool:
    return any(_decorator_name(decorator) in aliases for decorator in node.decorator_list)


def _whitelist_options(node: ast.FunctionDef | ast.AsyncFunctionDef, aliases: set[str]) -> dict[str, Any]:
    for decorator in node.decorator_list:
        if _decorator_name(decorator) not in aliases:
            continue
        if not isinstance(decorator, ast.Call):
            return {}
        options = {}
        for keyword in decorator.keywords:
            try:
                options[keyword.arg] = ast.literal_eval(keyword.value)
            except Exception:
                options[keyword.arg] = ast.unparse(keyword.value)
        return options
    return {}


def _decorator_name(decorator: ast.expr) -> str:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Attribute):
        prefix = _decorator_name(target.value)
        return f"{prefix}.{target.attr}" if prefix else target.attr
    if isinstance(target, ast.Name):
        return target.id
    return ""


def _signature_for(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = []
    defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults)
    for arg, default in zip(node.args.args, defaults, strict=False):
        if arg.arg == "self":
            continue
        text = arg.arg
        if arg.annotation:
            text += f": {ast.unparse(arg.annotation)}"
        if default:
            text += f" = {ast.unparse(default)}"
        args.append(text)
    return f"{node.name}({', '.join(args)})"


def _module_name(path: Path, package_root: Path) -> str:
    relative = path.relative_to(package_root).with_suffix("")
    return ".".join(relative.parts)


def _app_source_info(app_name: str) -> dict[str, Any]:
    try:
        app_path = Path(frappe.get_app_path(app_name)).resolve()
    except Exception:
        return {"available": False, "package_root": app_name}

    git = _git_info(app_path)
    return {
        "available": app_path.exists(),
        "package_root": app_name,
        "repository_url": _sanitize_remote_url(git.get("repository_url")),
        "branch": git.get("branch"),
        "commit": git.get("commit"),
    }


def _git_info(path: Path) -> dict[str, str | None]:
    return {
        "repository_url": _git(path, "config", "--get", "remote.origin.url"),
        "branch": _git(path, "rev-parse", "--abbrev-ref", "HEAD"),
        "commit": _git(path, "rev-parse", "HEAD"),
    }


def _git(path: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None

    value = result.stdout.strip()
    return value or None


def _sanitize_remote_url(remote_url: str | None) -> str | None:
    if not remote_url:
        return None

    if "://" not in remote_url:
        return remote_url

    parsed = urlsplit(remote_url)
    hostname = parsed.hostname
    if not hostname:
        return remote_url

    netloc = hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"

    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _hook_summary(app_hooks: dict[str, Any]) -> dict[str, int]:
    hook_keys = (
        "doc_events",
        "scheduler_events",
        "fixtures",
        "override_doctype_class",
        "override_whitelisted_methods",
        "permission_query_conditions",
        "has_permission",
        "app_include_js",
        "app_include_css",
        "doctype_js",
        "doctype_list_js",
        "jinja",
        "frax_tools",
    )
    return {key: _hook_count(app_hooks.get(key)) for key in hook_keys if app_hooks.get(key)}


def _hook_count(value: Any) -> int:
    if isinstance(value, dict):
        return len(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return 1 if value else 0


def _doctype_source_pointer(app_name: str, module: str, doctype: str) -> dict[str, str]:
    scrubbed_module = frappe.scrub(module)
    scrubbed_doctype = frappe.scrub(doctype)
    base = f"{app_name}/{scrubbed_module}/doctype/{scrubbed_doctype}"
    return {
        "json": f"{base}/{scrubbed_doctype}.json",
        "controller": f"{base}/{scrubbed_doctype}.py",
        "client_js": f"{base}/{scrubbed_doctype}.js",
        "list_js": f"{base}/{scrubbed_doctype}_list.js",
    }


def _record_source_pointer(app_name: str, module: str, artifact_type: str, name: str) -> dict[str, str]:
    scrubbed_module = frappe.scrub(module)
    scrubbed_name = frappe.scrub(name)
    base = f"{app_name}/{scrubbed_module}/{artifact_type}/{scrubbed_name}"
    return {
        "json": f"{base}/{scrubbed_name}.json",
        "python": f"{base}/{scrubbed_name}.py",
        "javascript": f"{base}/{scrubbed_name}.js",
    }


def _relative_source_path(path: Path, package_root: Path) -> str:
    return str(path.relative_to(package_root))
