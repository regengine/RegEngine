"""Guardrail tests for tenant_id scoping in tenant_models Cypher emitters (#1413).

Every ``to_cypher_*`` method on tenant-scoped Pydantic models in
``services/shared/tenant_models.py`` MUST scope MATCH/MERGE patterns on
tenant-scoped labels (``TenantControl``, ``CustomerProduct``, ``ControlMapping``)
by ``tenant_id``. Without this predicate, a tenant can reference another
tenant's node simply by supplying its id.

These tests parse the emitted Cypher and assert the invariant for:
  * ``ControlMapping.to_cypher_create`` (the #1413 regression)
  * ``ProductControlLink.to_cypher_create`` (already correct — guarded here
    so a future refactor cannot silently drop the scoping)

They also enumerate every public model in the module and ensure any future
``to_cypher_*`` addition is covered automatically.

``Provision`` is intentionally excluded: it lives in the global
``reg_global`` database and is not tenant-scoped.
"""
from __future__ import annotations

import importlib.util
import inspect
import re
import sys
from pathlib import Path
from uuid import uuid4

import pytest


# ---- Load services.shared.tenant_models without depending on package __init__ ----
_shared_dir = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "services.shared.tenant_models_1413",
    _shared_dir / "tenant_models.py",
)
tenant_models = importlib.util.module_from_spec(_spec)
sys.modules["services.shared.tenant_models_1413"] = tenant_models
_spec.loader.exec_module(tenant_models)

ControlMapping = tenant_models.ControlMapping
CustomerProduct = tenant_models.CustomerProduct
MappingType = tenant_models.MappingType
ProductControlLink = tenant_models.ProductControlLink
ProductType = tenant_models.ProductType
TenantControl = tenant_models.TenantControl


# ---- Labels that MUST carry a tenant_id predicate in every MATCH/MERGE ---------
TENANT_SCOPED_LABELS = frozenset({"TenantControl", "CustomerProduct", "ControlMapping"})


# Matches ``MATCH (var:Label {props})`` and ``MERGE (var:Label {props})``.
# Group 1: MATCH|MERGE. Group 2: variable. Group 3: label. Group 4: prop body.
_NODE_PATTERN_RE = re.compile(
    r"\b(MATCH|MERGE)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\{([^}]*)\}",
    re.IGNORECASE,
)


def _assert_tenant_scoped(query: str, method_name: str) -> None:
    """Every MATCH/MERGE on a tenant-scoped label must include ``tenant_id:``.

    CREATE clauses are exempt — they set the tenant_id, not filter by it —
    which is why the regex scopes itself to MATCH/MERGE only.
    """
    for match in _NODE_PATTERN_RE.finditer(query):
        op, var, label, props = match.group(1), match.group(2), match.group(3), match.group(4)
        if label not in TENANT_SCOPED_LABELS:
            continue
        assert "tenant_id" in props, (
            f"{method_name}: {op} on tenant-scoped label :{label} "
            f"(var='{var}') is missing 'tenant_id' predicate. "
            f"Pattern props were: {{{props.strip()}}}. "
            "This is a cross-tenant graph-scoping vulnerability (#1413)."
        )


# ---- Concrete, readable tests for each known emitter --------------------------


class TestControlMappingScoping:
    """#1413 regression guard."""

    def test_to_cypher_create_scopes_tenant_control_match_by_tenant_id(self):
        mapping = ControlMapping(
            tenant_id=uuid4(),
            control_id=uuid4(),
            provision_hash="prov_hash_abc",
            mapping_type=MappingType.IMPLEMENTS,
            confidence=0.9,
            created_by=uuid4(),
        )

        query, params = mapping.to_cypher_create()

        assert "MATCH (control:TenantControl {id: $control_id, tenant_id: $tenant_id})" in query, (
            "ControlMapping must scope its TenantControl MATCH by tenant_id "
            "to prevent cross-tenant mapping injection (#1413)."
        )
        assert params["tenant_id"] == str(mapping.tenant_id)
        _assert_tenant_scoped(query, "ControlMapping.to_cypher_create")


class TestProductControlLinkScoping:
    """Already correct; guarded so future edits cannot silently regress."""

    def test_to_cypher_create_scopes_both_matches_by_tenant_id(self):
        link = ProductControlLink(
            product_id=uuid4(),
            control_id=uuid4(),
            tenant_id=uuid4(),
        )

        query, params = link.to_cypher_create()

        _assert_tenant_scoped(query, "ProductControlLink.to_cypher_create")
        assert params["tenant_id"] == str(link.tenant_id)


class TestTenantControlCreate:
    """TenantControl.to_cypher_create is CREATE-only — no MATCH to scope —
    but the node body must still carry tenant_id so later MATCHes can scope on it.
    """

    def test_create_writes_tenant_id_property(self):
        tenant_id = uuid4()
        control = TenantControl(
            tenant_id=tenant_id,
            control_id="AC-001",
            title="Access Control Baseline",
            description="Baseline access control policy",
            framework="NIST CSF",
        )

        query, params = control.to_cypher_create()

        assert "tenant_id: $tenant_id" in query
        assert params["tenant_id"] == str(tenant_id)


class TestCustomerProductCreate:
    """CustomerProduct.to_cypher_create is CREATE-only — same contract."""

    def test_create_writes_tenant_id_property(self):
        tenant_id = uuid4()
        product = CustomerProduct(
            tenant_id=tenant_id,
            product_name="Custody Platform",
            description="Qualified custody of digital assets",
            product_type=ProductType.CUSTODY,
            jurisdictions=["US"],
        )

        query, params = product.to_cypher_create()

        assert "tenant_id: $tenant_id" in query
        assert params["tenant_id"] == str(tenant_id)


# ---- Property-based sweep: catches NEW to_cypher_* methods automatically ------


def _sample_instance(model_cls):
    """Return a minimally-valid instance for each known tenant model.

    If a new tenant model is added to tenant_models.py, add a factory branch
    here so the sweep test below can auto-cover it. If none matches, the
    sweep test explicitly fails — forcing the author to wire up the
    guardrail.
    """
    if model_cls is TenantControl:
        return TenantControl(
            tenant_id=uuid4(),
            control_id="X-1",
            title="t",
            description="d",
            framework="NIST",
        )
    if model_cls is CustomerProduct:
        return CustomerProduct(
            tenant_id=uuid4(),
            product_name="p",
            description="d",
            product_type=ProductType.OTHER,
            jurisdictions=["US"],
        )
    if model_cls is ControlMapping:
        return ControlMapping(
            tenant_id=uuid4(),
            control_id=uuid4(),
            provision_hash="h",
            mapping_type=MappingType.REFERENCES,
            confidence=0.5,
            created_by=uuid4(),
        )
    if model_cls is ProductControlLink:
        return ProductControlLink(
            product_id=uuid4(),
            control_id=uuid4(),
            tenant_id=uuid4(),
        )
    return None


def _tenant_models_with_cypher():
    """Yield ``(cls, method_name)`` for every public ``to_cypher_*`` method."""
    for name, obj in inspect.getmembers(tenant_models, inspect.isclass):
        if obj.__module__ != tenant_models.__name__:
            continue  # Skip re-exported classes like BaseModel.
        if not hasattr(obj, "model_fields"):
            continue  # Not a Pydantic model.
        for method_name in dir(obj):
            if method_name.startswith("to_cypher_") and callable(getattr(obj, method_name)):
                yield obj, method_name


@pytest.mark.parametrize(
    "model_cls,method_name",
    list(_tenant_models_with_cypher()),
    ids=lambda v: v.__name__ if inspect.isclass(v) else v,
)
def test_every_to_cypher_method_scopes_tenant_labels_by_tenant_id(model_cls, method_name):
    """Property-based guardrail.

    For every public ``to_cypher_*`` method on every Pydantic model in
    tenant_models.py, invoke it and assert the emitted Cypher string's
    MATCH/MERGE patterns on tenant-scoped labels all carry a tenant_id
    predicate.

    If this test fails after a new method is added, either:
      (a) the new method has a MATCH/MERGE on a tenant label without
          tenant_id scoping — fix the Cypher; or
      (b) the new method uses a new tenant-scoped label — add it to
          TENANT_SCOPED_LABELS above.
    """
    instance = _sample_instance(model_cls)
    assert instance is not None, (
        f"New tenant model {model_cls.__name__} has no sample factory in "
        "test_tenant_models_cypher_scoping_1413._sample_instance. "
        "Add one so the cross-tenant guardrail covers it."
    )

    result = getattr(instance, method_name)()

    # Emitters return ``(query_str, params_dict)``.
    assert isinstance(result, tuple) and len(result) == 2, (
        f"{model_cls.__name__}.{method_name} must return (query, params)."
    )
    query, params = result
    assert isinstance(query, str) and query.strip(), "empty query"
    assert isinstance(params, dict), "params must be a dict"

    _assert_tenant_scoped(query, f"{model_cls.__name__}.{method_name}")


def test_node_pattern_regex_itself_detects_missing_tenant_id():
    """Sanity check: the guardrail fires on the pre-fix pattern.

    This protects the test from silently going green if the regex ever
    breaks (e.g. labels-on-next-line formatting).
    """
    vulnerable = "MATCH (control:TenantControl {id: $control_id}) CREATE (x:Foo)"
    with pytest.raises(AssertionError, match="missing 'tenant_id' predicate"):
        _assert_tenant_scoped(vulnerable, "synthetic_vulnerable")

    safe = "MATCH (control:TenantControl {id: $control_id, tenant_id: $tenant_id})"
    _assert_tenant_scoped(safe, "synthetic_safe")  # must not raise


# ---- Parameter-binding contract: no f-string injection of tenant_id ------------


@pytest.mark.parametrize(
    "model_cls,method_name",
    list(_tenant_models_with_cypher()),
    ids=lambda v: v.__name__ if inspect.isclass(v) else v,
)
def test_tenant_id_is_bound_parameter_not_interpolated(model_cls, method_name):
    """Cypher must reference tenant_id via the ``$tenant_id`` placeholder,
    not as an interpolated literal. If a future refactor switches to
    f-string-built queries, this test fails — protecting against Cypher
    injection (#1413 hardening).
    """
    instance = _sample_instance(model_cls)
    assert instance is not None, f"missing factory for {model_cls.__name__}"
    query, params = getattr(instance, method_name)()

    # If the method touches tenant_id at all, the literal UUID string from
    # ``params['tenant_id']`` must not appear anywhere in the query body —
    # only the ``$tenant_id`` placeholder may.
    if "tenant_id" in params:
        literal = params["tenant_id"]
        assert literal not in query, (
            f"{model_cls.__name__}.{method_name}: tenant_id value "
            f"'{literal}' appears literally in the Cypher string. "
            "Use the $tenant_id bound parameter — not f-string "
            "interpolation — to prevent Cypher injection."
        )
        assert "$tenant_id" in query, (
            f"{model_cls.__name__}.{method_name}: query references "
            "tenant_id but does not use the $tenant_id placeholder."
        )


# ---- Negative control: Provision is global, not tenant-scoped ------------------


def test_provision_node_is_not_tenant_scoped_in_control_mapping():
    """``Provision`` lives in the global ``reg_global`` database (shared
    reference data keyed by hash). The ControlMapping query intentionally
    references ``(:Provision {hash: $provision_hash})`` WITHOUT a
    tenant_id predicate. Document and lock that decision so a well-meaning
    ``add tenant_id everywhere`` refactor does not break the global
    cross-reference.

    If Provision is ever migrated into per-tenant databases, delete this
    test and add ``Provision`` to ``TENANT_SCOPED_LABELS`` above.
    """
    mapping = ControlMapping(
        tenant_id=uuid4(),
        control_id=uuid4(),
        provision_hash="prov_hash_xyz",
        mapping_type=MappingType.IMPLEMENTS,
        confidence=0.5,
        created_by=uuid4(),
    )
    query, _ = mapping.to_cypher_create()

    # The provision node pattern must be present and must NOT carry tenant_id.
    provision_patterns = re.findall(
        r"\(:Provision\s*\{[^}]*\}\)", query
    )
    assert provision_patterns, "ControlMapping must still reference Provision"
    for pat in provision_patterns:
        assert "tenant_id" not in pat, (
            f"Provision is global reference data — must NOT carry "
            f"tenant_id. Got: {pat}"
        )
