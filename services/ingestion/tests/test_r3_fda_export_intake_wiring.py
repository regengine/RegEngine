"""Data-free wiring tests for FDA export and intake formats.

21 CFR 1.1455(c)(1) requires records to be provided to FDA within 24 hours,
and 21 CFR 1.1455(c)(3)(ii) requires an electronic sortable spreadsheet on
request. These tests parse source with ``ast`` and check only constants,
signatures, routing and wiring. They load no records, CSV rows or EPCIS docs.
"""

from __future__ import annotations

import ast
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1]
APP = SERVICE / "app"


def _tree(rel: str) -> ast.Module:
    return ast.parse((SERVICE / rel).read_text(encoding="utf-8"))


def _router_prefix(tree: ast.Module) -> str:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "router"
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", None) == "APIRouter"
        ):
            for kw in node.value.keywords:
                if kw.arg == "prefix":
                    return ast.literal_eval(kw.value)
    raise AssertionError("router = APIRouter(prefix=...) not found")


def _routes(tree: ast.Module) -> dict[tuple[str, str], ast.FunctionDef]:
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and getattr(dec.func.value, "id", None) == "router"
                    and dec.args
                ):
                    out[(dec.func.attr, ast.literal_eval(dec.args[0]))] = node
    return out


def _main_includes() -> dict[str, str | None]:
    """Map imported router alias -> _router_enabled flag guarding it (None = always)."""
    tree = _tree("main.py")
    aliases: dict[str, str | None] = {}

    def visit(body, flag):
        for node in body:
            if isinstance(node, ast.If):
                t = node.test
                f = flag
                if isinstance(t, ast.Call) and getattr(t.func, "id", None) == "_router_enabled":
                    f = ast.literal_eval(t.args[0])
                visit(node.body, f)
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    aliases[a.asname or a.name] = flag

    visit(tree.body, None)
    included = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            included.add(node.args[0].id)
    return {k: v for k, v in aliases.items() if k in included}


def test_fda_export_router_registered_and_compliance_critical():
    """21 CFR 1.1455(c)(1): the FDA export router is mounted and cannot be silently disabled."""
    includes = _main_includes()
    assert includes.get("fda_export_router") == "fda_export"
    src = (SERVICE / "main.py").read_text(encoding="utf-8")
    assert "from app.fda_export.router import router as fda_export_router" in src
    tree = _tree("main.py")
    compliance = next(
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "_COMPLIANCE_ROUTERS"
    )
    assert "fda_export" in ast.literal_eval(compliance)


def test_fda_spreadsheet_endpoint_path_method_and_service():
    """21 CFR 1.1455(c)(3)(ii): GET /api/v1/fda/export builds the sortable CSV via _generate_csv."""
    tree = _tree("app/fda_export/router.py")
    assert _router_prefix(tree) == "/api/v1/fda"
    routes = _routes(tree)
    fn = routes[("get", "/export")]
    assert fn.name == "export_fda_spreadsheet"
    called = {
        getattr(c.func, "id", None) for c in ast.walk(fn) if isinstance(c, ast.Call)
    }
    assert "_generate_csv" in called
    imported = {
        a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "fda_export_service"
        for a in n.names
    }
    assert "_generate_csv" in imported


def test_fda_columns_constant_drives_csv_headers():
    """21 CFR 1.1455(c)(3)(ii): FDA_COLUMNS are the spreadsheet headers used by _generate_csv."""
    tree = _tree("app/fda_export_service.py")
    cols = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "FDA_COLUMNS"
    )
    assert len(cols) == len(set(cols))
    for header in (
        "Traceability Lot Code (TLC)",
        "Product Description",
        "Quantity",
        "Unit of Measure",
        "Event Type (CTE)",
        "Event Date",
        "Location GLN",
        "Immediate Previous Source",
        "TLC Source GLN",
        "Reference Document Number",
        "System Entry Timestamp",
    ):
        assert header in cols, header
    gen = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_generate_csv"
    )
    assert "include_pii" in {a.arg for a in gen.args.args + gen.args.kwonlyargs}
    assert any(
        isinstance(n, ast.keyword)
        and n.arg == "fieldnames"
        and getattr(n.value, "id", None) == "FDA_COLUMNS"
        for n in ast.walk(gen)
    )


def test_supported_intake_formats_are_routed():
    """21 CFR 1.1455(c)(1): webhook, CSV and EPCIS intake paths are all mounted."""
    includes = _main_includes()
    assert "webhook_router" in includes and includes["webhook_router"] is None
    assert includes.get("csv_router") == "csv"
    assert includes.get("epcis_ingestion_router") == "epcis_ingestion"

    expected = {
        "webhook": ("app/webhook_router_v2/routes.py", "/api/v1/webhooks", ("post", "/ingest")),
        "csv": ("app/csv_templates.py", "/api/v1", ("post", "/ingest/csv")),
        "epcis": ("app/epcis/router.py", "/api/v1/epcis", ("post", "/events")),
    }
    for fmt, (rel, prefix, route) in expected.items():
        tree = _tree(rel)
        assert _router_prefix(tree) == prefix, fmt
        assert route in _routes(tree), fmt
