#!/usr/bin/env python3
"""Build the L2 classification-registry seed from Vector's residual_digest.json.

Joins each residual nodeid with the file->RC mapping from
defect-ledger/DEFECT_LEDGER_2026-09-17.md + residual_classification.md.
Nodeid-level granularity: mixed-class files (test_integration_router_1342)
split by message content. Prints a coverage report; any unmatched nodeid is
emitted with class "unclassified" so the gate surfaces it rather than hiding it.

Output: artifacts/classification_registry.seed.json
"""
import json
import re
import sys
from pathlib import Path

_LONG_HEX = re.compile(r"[0-9a-fA-F]{32,64}")


def _short_hex(s: str) -> str:
    """Shorten long hex runs (git SHAs, content hashes) copied verbatim from
    assertion messages — keeps the seed clear of secrets-scanner findings."""
    return _LONG_HEX.sub(lambda m: m.group(0)[:8] + "...", s)

VECTOR_WS = Path("/Users/sellers/.openclaw-agents/vector/workspace")
GATE_WS = Path("/Users/sellers/.openclaw-agents/gate/workspace")

# file -> (class, rc_id, status, owner, evidence)
FILE_MAP = {
    # env-mark (44 nodeids; pool_checkout carries 2 in digest vs 1 in table)
    "tests/contract/test_error_envelope_contract_2863.py": ("env-mark", None, "env-provided", "prism", "blocked on frontend/public/openapi.json artifact"),
    "tests/contract/test_openapi_production_surface_2861.py": ("env-mark", None, "env-provided", "prism", "blocked on frontend/public/openapi.json artifact"),
    "tests/sdk/test_route_contract.py": ("env-mark", None, "open", "gate", "needs ENABLED_ROUTERS scaffolding"),
    "services/ingestion/tests/test_fsma_readiness_compat_2893.py": ("env-mark", None, "open", "gate", "production-posture subprocess requires ENABLED_ROUTERS/DISABLED_ROUTERS"),
    "services/shared/tests/test_build_info.py": ("env-mark", None, "open", "gate", ".git checkout leaks real commit hash; expects None"),
    "services/admin/tests/test_pool_checkout_guc_reset.py": ("env-mark", None, "open", "gate", "live-DB checkout idle-reset assertion"),
    "services/graph/tests/test_fsma_metrics.py": ("env-mark", None, "open", "vector", "VERIFIED: prometheus_client 0.25.0 vs lock 0.26.0; lock-sync clears"),
    "services/admin/tests/test_hallucination_tracker.py": ("env-mark", None, "open", "vector", "VERIFIED: same prometheus_client root"),
    # harness-bug
    "services/graph/tests/test_fsma_routes.py": ("harness-bug", "RC-101", "open", "vector", "auth-fixture: no auth context seeded"),
    "services/graph/tests/test_fsma_physics.py": ("harness-bug", "RC-101", "open", "vector", "auth-fixture cluster"),
    "services/graph/tests/test_mobile_ingestion.py": ("harness-bug", "RC-101", "open", "vector", "auth-fixture cluster"),
    "services/ingestion/tests/test_routes_status_1342.py": ("harness-bug", "RC-101", "open", "vector", "auth-fixture cluster (incl. 2 mock-assertion downstream)"),
    "tests/shared/test_tenant_log_context_2859.py": ("harness-bug", "RC-102", "open", "vector", "log/audit capture fixture stopped capturing"),
    "services/ingestion/tests/test_stripe_webhook_missing_handlers_1189.py": ("harness-bug", "RC-102", "open", "vector", "log/audit capture cluster"),
    "services/shared/tests/test_change_scopes.py": ("harness-bug", "RC-102", "open", "vector", "log/audit capture cluster"),
    "services/shared/tests/test_rules_deadletter_2709.py": ("harness-bug", "RC-102", "open", "vector", "log/audit capture cluster"),
    "services/ingestion/tests/test_stripe_routes_1342.py": ("harness-bug", "RC-102", "open", "vector", "mismatch-log capture"),
    "tests/billing/test_stripe_billing.py": ("harness-bug", "RC-108", "fixed", "vector", "FIXED 091af550 autouse fixture stubs rate-limit check; deterministic standalone"),
    "tests/shared/test_secret_validation.py": ("harness-bug", "RC-109", "fixed", "vector", "FIXED 398ec903 base_env gains 4 prod-required vars added under #2911/#2912"),
    "services/admin/tests/test_erasure_no_false_success_2900.py": ("harness-bug", "RC-103", "open", "vector", "Depends() object misused as session"),
    "services/ingestion/tests/test_stripe_billing_router.py": ("harness-bug", "RC-103", "open", "vector", "mock call-args KeyError tenant_id"),
    "services/shared/tests/test_api_key_store_rate_limit_minute_rollover.py": ("harness-bug", "RC-104", "open", "vector", "clock not frozen; no clock seam (product improvement noted)"),
    "tests/shared/test_merkle_no_chain_evidence_2698.py": ("harness-bug", "RC-106", "open", "vector", "stale import app.fda_export post-reorg"),
    # real-defect
    "services/shared/tests/test_secrets_fail_closed.py": ("real-defect", "RC-001", "open", "anvil", "fail-closed secret checks lost in server/main.py refactor; High"),
    "services/admin/tests/test_no_login_role_credentials_2920.py": ("real-defect", "RC-002", "open", "anvil", "hardcoded login-role password; RLS outside Alembic chain; High; Anvil E2 in flight"),
    "services/ingestion/tests/test_fda_export_router_1342.py": ("real-defect", "RC-003", "open", "anvil", "error branches raise unhandled instead of status mapping"),
    "tests/shared/test_visibility_timeout_2918.py": ("real-defect", "RC-004", "open", "anvil", "#2918 implementation missing on 5dca9b8a; tests merged ahead"),
    "services/ingestion/tests/test_fda_export_pii_redaction.py": ("real-defect", "RC-005", "open", "anvil", "seeded fixtures not visible to export query"),
    "services/ingestion/tests/test_fda_export_verify_roundtrip_2898.py": ("real-defect", "RC-006", "open", "anvil", "seeding split + str/int coverage compare"),
    "services/ingestion/tests/test_fda_export_audit_logging.py": ("real-defect", "RC-007", "open", "anvil", "seeding split; coverage-bypass unreachable"),
    "services/ingestion/tests/test_fda_export_perf_2515_2516.py": ("real-defect", "RC-008", "open", "anvil", "seeding split"),
    "services/ingestion/tests/test_fda_export_router.py": ("real-defect", "RC-009", "open", "anvil", "seeding split; str>int type bug"),
    "tests/security/test_repo_visibility_claims_2811.py": ("real-defect", "RC-010", "open", "anvil", "PRE_PUBLIC_CHECKLIST.md lists 15 nonexistent paths; docs fix"),
    "services/shared/tests/test_tenant_guc_hook.py": ("real-defect", "RC-011", "open", "anvil", "GUC seeded with 'explicit' sentinel instead of row tenant_id"),
    "services/ingestion/tests/test_routes_discovery_task_queue.py": ("real-defect", "RC-012", "open", "anvil", "task type never registered"),
    "services/ingestion/tests/test_routes_regulation_task_queue.py": ("real-defect", "RC-012", "open", "anvil", "task type never registered"),
    "services/ingestion/tests/test_routes_scraping_task_queue.py": ("real-defect", "RC-012", "open", "anvil", "task types never registered"),
    "services/ingestion/tests/test_routes_sources_task_queue.py": ("real-defect", "RC-012", "open", "anvil", "task types never registered"),
    "services/ingestion/tests/test_stripe_webhooks_1342.py": ("real-defect", "RC-013", "open", "anvil", "invoice.paid funnel emission dropped in refactor"),
    "services/ingestion/tests/test_supplier_portal_1342.py": ("real-defect", "RC-014", "open", "anvil", "per-link rate limiting not enforced"),
    "tests/migrations/test_destructive_downgrade_documented_2827.py": ("real-defect", "RC-015", "open", "anvil", "v116 destroys rows without acknowledgement guard"),
    "tests/migrations/test_migration_fresh_db.py": ("real-defect", "RC-016", "open", "anvil", "policy resolver gap"),
    "tests/scripts/test_regenerate_public_samples_gate.py": ("real-defect", "RC-017", "open", "anvil", "workflow yaml drift after lock policy change"),
    "tests/scripts/test_export_env_bundle_no_disk_secrets.py": ("real-defect", "RC-018", "open", "anvil", "script named for what it doesn't do; rename"),
    "services/scheduler/tests/test_deadline_monitor_2908.py": ("real-defect", "RC-019", "open", "anvil", "#2908 hardening constants/registration not on tree"),
}

# nodeid-level split for mixed-class files: (file, msg-substring) -> spec
MSG_OVERRIDES = [
    # test_integration_router_1342: 5 harness (mock-shape KeyErrors) vs 11 retracted (404 pollution)
    ("services/ingestion/tests/test_integration_router_1342.py", ("tid", "since", "payload", "KeyError"),
     ("harness-bug", "RC-107", "open", "vector", "mock-shape KeyError; file itself retracted as real-defect")),
]

# excluded from registry entirely (retracted / no-defect verdicts)
EXCLUDED_FILES = {
    "tests/migrations/test_rls_predicate_hardening_v090.py": "RC-105 verdict: no defect (stale-tree scan state; standalone/direct guard scans 108, exit 0)",
}
RETRACTED_DEFAULT = ("excluded", None, "retracted", "vector", "RETRACTED 2026-09-17 P3 re-screen: passes 39/39 standalone; suite-context pollution")


def classify(file: str, msg: str):
    if file in EXCLUDED_FILES:
        return None
    for f, needles, spec in MSG_OVERRIDES:
        if file == f and any(n in msg for n in needles):
            return spec
    if file == "services/ingestion/tests/test_integration_router_1342.py":
        return RETRACTED_DEFAULT
    if file in FILE_MAP:
        return FILE_MAP[file]
    return ("unclassified", None, "open", "vector", "not itemized in classification tables; needs Vector triage")


def main():
    digest = json.load(open(VECTOR_WS / "residual_digest.json"))
    entries, excluded = [], []
    for file, items in digest["byFile"].items():
        for it in items:
            spec = classify(file, it.get("msg", ""))
            if spec is None:
                excluded.append({"nodeid": it["nodeid"], "why": EXCLUDED_FILES[file]})
                continue
            cls, rc, status, owner, evidence = spec
            entries.append({
                "nodeid": it["nodeid"], "file": file, "class": cls, "rc_id": rc,
                "status": status, "owner": owner, "evidence": evidence,
                "baseline_msg": _short_hex(it.get("msg", ""))[:200],
            })
    out = GATE_WS / "artifacts/classification_registry.seed.json"
    out.write_text(json.dumps({"baseline": "5dca9b8a", "source": "vector residual_digest.json",
                               "entries": entries, "excluded": excluded}, indent=1))
    # coverage report
    from collections import Counter
    by_class = Counter(e["class"] for e in entries)
    by_rc = Counter(e["rc_id"] for e in entries if e["rc_id"])
    print(f"entries={len(entries)} excluded={len(excluded)}")
    print("by_class:", dict(by_class))
    print("unclassified files:", sorted({e['file'] for e in entries if e['class'] == 'unclassified'}))
    print("env-mark:", by_class.get("env-mark"), "harness:", by_class.get("harness-bug"),
          "real:", by_class.get("real-defect"))
    print("RC-101:", by_rc.get("RC-101"), "RC-102:", by_rc.get("RC-102"))
    print(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
