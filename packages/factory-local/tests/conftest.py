import pytest

from extract import load_fixture
from schemas import DeonticIR


@pytest.fixture
def ir() -> DeonticIR:
    return load_fixture()


def make_ir(rule_id: str, predicates: list[dict], **overrides) -> DeonticIR:
    base = {
        "rule_id": rule_id,
        "citation": f"TEST § {rule_id}",
        "modality": "OBLIGATION",
        "applicability_predicates": predicates,
        "action_required": "assessment_done",
        "max_penalty_usd": 1000,
        "private_right_of_action": False,
    }
    return DeonticIR.model_validate({**base, **overrides})
