import pytest
from pydantic import ValidationError

from compiler import compile_ir_to_rego
from conftest import make_ir
from schemas import DeonticIR, DeonticPredicate


def test_fixture_rego_shape(ir):
    rego = compile_ir_to_rego(ir, "factory.us_co_sb205")
    assert rego.startswith("package factory.us_co_sb205\n\nimport rego.v1\n")
    assert 'default status := "EXEMPT_OR_NOT_APPLICABLE"' in rego
    assert "default violation_exposure_usd := 0" in rego
    assert "\tinput.fte_count > 49\n\tinput.does_business_in_co == true\n" in rego
    assert (
        'status := "COMPLIANT" if {\n\tis_applicable\n'
        "\tinput.controls.annual_impact_assessment_completed == true\n}"
    ) in rego
    assert (
        'status := "COMPLIANT_VIA_SAFE_HARBOR" if {\n\tis_applicable\n'
        "\tnot input.controls.annual_impact_assessment_completed == true\n"
        "\tinput.controls.nist_ai_rmf_aligned == true\n}"
    ) in rego
    assert (
        'status := "NON_COMPLIANT_BREACH" if {\n\tis_applicable\n'
        "\tnot input.controls.annual_impact_assessment_completed == true\n"
        "\tnot input.controls.nist_ai_rmf_aligned == true\n}"
    ) in rego
    assert (
        "violation_exposure_usd := input.affected_consumer_count * 20000 if {\n"
        '\tstatus == "NON_COMPLIANT_BREACH"\n}'
    ) in rego
    assert 'citation := "C.R.S. § 6-1-1703"' in rego


def test_prohibition_flips_action_test():
    rego = compile_ir_to_rego(make_ir("P1", [], modality="PROHIBITION"), "factory.p1")
    assert 'status := "COMPLIANT" if {\n\tis_applicable\n\tnot input.controls.assessment_done == true\n}' in rego
    assert "is_applicable if {\n\ttrue\n}" in rego


def test_string_and_nested_fact_literals():
    ir = make_ir("S1", [{"fact": "org.state", "operator": "EQUALS", "value": 'CO"; allow := true #'}])
    rego = compile_ir_to_rego(ir, "factory.s1")
    assert 'input.org.state == "CO\\"; allow := true #"' in rego


@pytest.mark.parametrize("fact", ["fte count", "a..b", "x;y", "1abc", "default", "a.not", ""])
def test_unsafe_fact_rejected_by_schema(fact):
    with pytest.raises(ValidationError):
        DeonticPredicate(fact=fact, operator="EQUALS", value=1)


def test_unsafe_names_rejected_by_compiler_even_without_validation(ir):
    bad_pred = DeonticPredicate.model_construct(fact="x } allow if { true", operator="EQUALS", value=1)
    bad = ir.model_copy(update={"applicability_predicates": [bad_pred]})
    with pytest.raises(ValueError, match="unsafe fact"):
        compile_ir_to_rego(bad, "factory.x")
    with pytest.raises(ValueError, match="unsafe control"):
        compile_ir_to_rego(ir.model_copy(update={"safe_harbor_control": "a-b"}), "factory.x")
    with pytest.raises(ValueError, match="unsafe package"):
        compile_ir_to_rego(ir, "factory.us-co")


def test_ordering_operator_requires_number():
    with pytest.raises(ValidationError):
        DeonticPredicate(fact="x", operator="GREATER_THAN", value=True)
    with pytest.raises(ValidationError):
        DeonticPredicate(fact="x", operator="LESS_THAN", value="10")


def test_bool_not_coerced_to_int():
    assert DeonticPredicate(fact="x", operator="EQUALS", value=True).value is True
    assert DeonticPredicate(fact="x", operator="EQUALS", value=1).value == 1
    with pytest.raises(ValidationError):
        DeonticIR.model_validate({**make_ir("N", []).model_dump(), "max_penalty_usd": -1})
