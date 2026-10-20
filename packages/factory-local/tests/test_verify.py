import z3

from conftest import make_ir
from verify import OK_STATUS, check_cross_rule_collisions, check_status_bodies, status_bodies, verify_ir


def test_fixture_is_deterministic_and_complete(ir):
    result = verify_ir(ir)
    assert result["status"] == OK_STATUS
    assert result["overlaps"] == [] and result["gap_counterexample"] is None


def test_prohibition_and_mixed_types_verify():
    ir = make_ir(
        "M1",
        [
            {"fact": "org.revenue", "operator": "GREATER_THAN", "value": 1.5},
            {"fact": "org.revenue", "operator": "LESS_THAN", "value": 10},
            {"fact": "org.state", "operator": "EQUALS", "value": "CO"},
        ],
        modality="PROHIBITION",
    )
    assert verify_ir(ir)["status"] == OK_STATUS


def test_drifted_bodies_give_overlap_counterexample(ir):
    # Simulate a compiler regression: the safe harbor body forgets `not action`.
    bodies, env = status_bodies(ir)
    sh = env["controls.nist_ai_rmf_aligned"]
    applicable = z3.And(env["fte_count"] > 49, env["does_business_in_co"] == True)  # noqa: E712
    bodies["COMPLIANT_VIA_SAFE_HARBOR"] = z3.And(applicable, sh)

    result = check_status_bodies(bodies, env)
    assert result["status"] == "SAT_OVERLAP" and not result["deterministic"]
    hit = result["overlaps"][0]
    assert hit["statuses"] == ["COMPLIANT", "COMPLIANT_VIA_SAFE_HARBOR"]
    m = hit["counterexample"]
    assert m["fte_count"] > 49 and m["does_business_in_co"] is True
    assert m["controls.annual_impact_assessment_completed"] is True
    assert m["controls.nist_ai_rmf_aligned"] is True


def test_missing_body_gives_gap_counterexample(ir):
    bodies, env = status_bodies(ir)
    del bodies["NON_COMPLIANT_BREACH"]
    result = check_status_bodies(bodies, env)
    assert result["status"] == "SAT_GAP"
    gap = result["gap_counterexample"]
    assert gap["controls.annual_impact_assessment_completed"] is False
    assert gap["controls.nist_ai_rmf_aligned"] is False


def test_cross_rule_collision_returns_concrete_model(ir):
    other = make_ir("US_TEST_LARGE", [{"fact": "fte_count", "operator": "GREATER_THAN", "value": 99}])
    hits = check_cross_rule_collisions([ir, other])
    by_dir = {(h["exempt_rule"], h["obligated_rule"]): h for h in hits}
    # Both directions are SAT: fte 50..99 (SB205 applies, other exempt) and fte > 99 outside CO.
    assert set(by_dir) == {("US_TEST_LARGE", "US_CO_SB205_V2"), ("US_CO_SB205_V2", "US_TEST_LARGE")}
    m = by_dir[("US_TEST_LARGE", "US_CO_SB205_V2")]["model"]
    assert 49 < m["fte_count"] <= 99 and m["does_business_in_co"] is True
    m2 = by_dir[("US_CO_SB205_V2", "US_TEST_LARGE")]["model"]
    assert m2["fte_count"] > 99 and m2["does_business_in_co"] is False
    assert all(h["shared_facts"] == ["fte_count"] for h in hits)


def test_cross_rule_subset_is_one_directional():
    wide = make_ir("WIDE", [{"fact": "n", "operator": "GREATER_THAN", "value": 0}])
    narrow = make_ir("NARROW", [{"fact": "n", "operator": "GREATER_THAN", "value": 10}])
    hits = check_cross_rule_collisions([wide, narrow])
    assert [(h["exempt_rule"], h["obligated_rule"]) for h in hits] == [("NARROW", "WIDE")]


def test_cross_rule_no_shared_facts_and_type_conflict():
    a = make_ir("A", [{"fact": "x", "operator": "EQUALS", "value": True}])
    b = make_ir("B", [{"fact": "y", "operator": "EQUALS", "value": 1}])
    c = make_ir("C", [{"fact": "x", "operator": "EQUALS", "value": "yes"}])
    assert check_cross_rule_collisions([a, b]) == []
    [hit] = check_cross_rule_collisions([a, c])
    assert "type_conflict" in hit
