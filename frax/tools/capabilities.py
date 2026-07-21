from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import frappe
from frappe.config import get_modules_from_all_apps_for_user

from frax.tools.registry import annotations_for, frax_tool, get_tool_policies


def register():
    return None


@frax_tool(name="frax_list_apps", risk="read", annotations=annotations_for("read", idempotent=True))
def list_apps():
    """List installed Frappe apps visible to the current site."""
    prepared_apps = []

    for app in frappe.get_installed_apps():
        app_hooks = frappe.get_hooks(app_name=app)
        prepared_apps.append(
            {
                "name": app,
                "description": (app_hooks.get("app_description") or [""])[0],
                "version": app_hooks.get("app_version"),
            }
        )

    return prepared_apps


@frax_tool(name="frax_list_app_modules", risk="read", annotations=annotations_for("read", idempotent=True))
def list_app_modules(app_name: str):
    """List modules belonging to an installed app.

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


@frax_tool(name="frax_list_app_doctypes", risk="read", annotations=annotations_for("read", idempotent=True))
def list_app_doctypes(app_name: str, module: str | None = None):
    """List DocTypes belonging to an installed app.

    Args:
        app_name: Installed app name.
        module: Optional module name within the app.
    """
    modules = _get_app_modules(app_name, module)
    if not modules:
        return []

    return frappe.get_all(
        "DocType",
        filters={"module": ["in", modules]},
        fields=["name", "module", "custom", "istable", "issingle"],
        order_by="module asc, name asc",
    )


@frax_tool(name="frax_list_app_reports", risk="read", annotations=annotations_for("read", idempotent=True))
def list_app_reports(app_name: str, module: str | None = None):
    """List reports belonging to an installed app.

    Args:
        app_name: Installed app name.
        module: Optional module name within the app.
    """
    modules = _get_app_modules(app_name, module)
    if not modules:
        return []

    return frappe.get_all(
        "Report",
        filters={"module": ["in", modules]},
        fields=["name", "module", "report_type", "ref_doctype", "is_standard"],
        order_by="module asc, name asc",
    )


@frax_tool(name="frax_list_app_pages", risk="read", annotations=annotations_for("read", idempotent=True))
def list_app_pages(app_name: str, module: str | None = None):
    """List pages belonging to an installed app.

    Args:
        app_name: Installed app name.
        module: Optional module name within the app.
    """
    modules = _get_app_modules(app_name, module)
    if not modules:
        return []

    return frappe.get_all(
        "Page",
        filters={"module": ["in", modules]},
        fields=["name", "module", "title", "standard"],
        order_by="module asc, name asc",
    )


@frax_tool(name="frax_list_tool_policies", risk="read", annotations=annotations_for("read", idempotent=True))
def list_tool_policies():
    """List Frax tool risk metadata used for MCP annotations and future enforcement."""
    return get_tool_policies()


@frax_tool(name="frax_list_app_whitelisted_methods", risk="read", annotations=annotations_for("read", idempotent=True))
def list_app_whitelisted_methods(app_name: str, module: str | None = None):
    """Discover app Python methods decorated with frappe.whitelist without importing app modules.

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
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        return [{"file": str(path), "error": f"SyntaxError: {exc}"}]

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
                "file": str(path),
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
