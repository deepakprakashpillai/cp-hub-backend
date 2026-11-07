import ast
from collections import defaultdict
from pathlib import Path

APP_ROOT = Path("app")
COMPOSITION_ROOTS = {
    "app.api.router",
    "app.db.models",
}
ADAPTER_PACKAGES = {
    "app.modules.admin",
    "app.modules.portal",
    "app.modules.read_models",
}
ROLE_ADAPTER_PACKAGES = {
    "app.modules.admin",
    "app.modules.portal",
}


def _module_name(path: Path) -> str:
    return ".".join(path.with_suffix("").parts)


def _imports(path: Path) -> set[str]:
    imports: set[str] = set()
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _is_under(module: str, package: str) -> bool:
    return module == package or module.startswith(f"{package}.")


def test_core_and_shared_do_not_import_features() -> None:
    violations = []
    for path in [*Path("app/core").glob("*.py"), *Path("app/shared").glob("*.py")]:
        for imported in _imports(path):
            if imported.startswith("app.modules."):
                violations.append(f"{path}: {imported}")
    assert violations == []


def test_models_and_schemas_do_not_import_adapters_routes_or_services() -> None:
    violations = []
    for path in Path("app/modules").rglob("*.py"):
        if path.name not in {"models.py", "schemas.py"}:
            continue
        for imported in _imports(path):
            if any(_is_under(imported, package) for package in ROLE_ADAPTER_PACKAGES):
                violations.append(f"{path}: {imported}")
            if imported.endswith(".routes") or imported.endswith(".service"):
                violations.append(f"{path}: {imported}")
    assert violations == []


def test_domain_code_does_not_import_admin_portal_or_routes() -> None:
    violations = []
    for path in Path("app/modules").rglob("*.py"):
        module = _module_name(path)
        if any(_is_under(module, package) for package in ADAPTER_PACKAGES):
            continue
        for imported in _imports(path):
            if any(_is_under(imported, package) for package in ADAPTER_PACKAGES):
                violations.append(f"{path}: {imported}")
            if imported.endswith(".routes"):
                violations.append(f"{path}: {imported}")
    assert violations == []


def test_role_adapters_do_not_depend_on_each_other() -> None:
    violations = []
    for package, forbidden in (
        (Path("app/modules/admin"), "app.modules.portal"),
        (Path("app/modules/portal"), "app.modules.admin"),
    ):
        for path in package.rglob("*.py"):
            for imported in _imports(path):
                if _is_under(imported, forbidden):
                    violations.append(f"{path}: {imported}")
    assert violations == []


def test_leaf_services_only_compose_notification_infrastructure() -> None:
    violations = []
    for path in Path("app/modules").glob("*/service.py"):
        if path.parent.name == "notifications":
            continue
        for imported in _imports(path):
            if not imported.endswith(".service"):
                continue
            if imported == "app.modules.notifications.service":
                continue
            violations.append(f"{path}: {imported}")
    assert violations == []


def test_removed_god_service_names_do_not_return() -> None:
    forbidden = {
        "AdminService",
        "BookingService",
        "BatchScheduleDayService",
        "BatchGroupService",
    }
    violations = []
    for path in APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in forbidden:
                violations.append(f"{path}: {node.name}")
    assert violations == []


def test_application_import_graph_has_no_cycles() -> None:
    files = list(APP_ROOT.rglob("*.py"))
    modules = {_module_name(path): path for path in files}
    graph: dict[str, set[str]] = defaultdict(set)
    for module, path in modules.items():
        if module in COMPOSITION_ROOTS:
            continue
        for imported in _imports(path):
            matches = [
                candidate
                for candidate in modules
                if imported == candidate or imported.startswith(f"{candidate}.")
            ]
            if matches:
                target = max(matches, key=len)
                if target != module:
                    graph[module].add(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str, trail: list[str]) -> None:
        if module in visiting:
            start = trail.index(module)
            cycle = " -> ".join([*trail[start:], module])
            raise AssertionError(f"Import cycle detected: {cycle}")
        if module in visited:
            return
        visiting.add(module)
        for dependency in graph[module]:
            visit(dependency, [*trail, module])
        visiting.remove(module)
        visited.add(module)

    for module in modules:
        visit(module, [])
