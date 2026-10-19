"""``scripts/jev_lab``: Jev Lab's offline fake, question sets, scoring, gates, privacy guard and loop.

Contract pinned here (offline; nothing leaves the process):

* The fake speaks the TypeSafe wire format through the real ``JevDecider``,
  is deterministic, and never claims to be Jev (its model name says fake).
* The production wording the lab starts from is production's own question
  builders' output, and the lab scores it exactly like ``scripts/jev_eval.py``
  (same answers, same request bodies).
* A candidate can never rename, add, drop or reorder an option, copy a
  labelled header into an example, or stop explaining the state keys.
* Splits are by case, stratified, stable; Claude's brief carries training
  data only, and the history it gets says one bit per kind about held-out.
* Acceptance: a training screen, then a held-out gate with a margin; each
  failed gate is named.
* The loop runs end to end on the fake, records every generation, counts
  held-out looks, never edits production constants, and keeps accepted
  wording as the next run's incumbent.
* The privacy guard refuses secrets, personal data, GLNs, UUIDs, the value
  of a secret environment variable and rows of values; header names pass.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import threading
from pathlib import Path

import httpx2
import pytest
from shared.jev import JevDecider, JevUnavailable, cte_classification as cte, header_mapping as hm

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "scripts" / "jev_lab"
SCRIPTS = str(ROOT / "scripts")


def _load_lab():
    if "jev_lab" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "jev_lab", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["jev_lab"] = module
        spec.loader.exec_module(module)
    return sys.modules["jev_lab"]


_load_lab()
from jev_lab import fake_jev, jev_access, ledger, loop, privacy, proposer, questions, scoring  # noqa: E402

jev_eval = sys.modules["jev_eval"]
ACCEPTING_SALT = "test-salt-0"
# Built from parts so no scanner mistakes the fixture for a real token.
FAKE_JWT = ".".join(["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0NTY3ODkwIn0", "c2lnbmF0dXJlLXZhbHVl"])
REJECTING_SALT = "test-salt-2"


@pytest.fixture
def cases():
    return jev_eval.load_cases(jev_eval.DEFAULT_CASES, templates=True)


@pytest.fixture
def fake():
    decider = jev_access.LabDecider(jev_access.build_decider(jev_access.FAKE), mode=jev_access.FAKE)
    yield decider
    decider.close()


def _home(tmp_path: Path, salt: str = ACCEPTING_SALT, looks: dict | None = None) -> ledger.Ledger:
    lab = ledger.Ledger(tmp_path / "lab", mode=ledger.FAKE)
    lab.ensure()
    lab.split_path.write_text(json.dumps({"salt": salt, "created": "2026-01-01T00:00:00Z", "looks": looks or {}}))
    return lab


def _recording(bodies: list) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return fake_jev.handler(request)

    return httpx2.MockTransport(handler)


def _obs(kind, case, subject, split, *, correct, confidence, answer=None, expected=("quantity",), consistent=None):
    return scoring.Observation(
        kind=kind,
        case_id=case,
        subject=subject,
        split=split,
        expected=tuple(expected),
        answer=answer or (expected[0] if correct else "carrier"),
        confidence=confidence,
        correct=correct,
        status="ok",
        order_consistent=consistent,
    )


# ---------------------------------------------------------------------------
# Package hygiene
# ---------------------------------------------------------------------------


def test_scripts_directory_is_never_put_on_sys_path():
    assert SCRIPTS not in sys.path


# ---------------------------------------------------------------------------
# Fake Jev
# ---------------------------------------------------------------------------


def test_fake_speaks_the_wire_format_through_the_real_client():
    decider = jev_access.build_decider(jev_access.FAKE)
    questions_ = {
        "cte": {
            "type": "choice",
            "instructions": "Which event?",
            "criteria": {"shipping": "goods leaving: ship date", "receiving": "goods arriving", "unclear": None},
        },
        "lot": {"type": "noul", "instructions": "Does a header name a lot code?"},
        "risk": {"type": "score", "instructions": "How risky?", "criteria": ["low", "medium", "high"]},
    }
    first = decider.ask({"headers": ["Ship Date", "Lot"]}, questions_, purpose="test")
    second = decider.ask({"headers": ["Ship Date", "Lot"]}, questions_, purpose="test")

    assert first.evidence.model == fake_jev.MODEL != "jev-1.13.0"
    assert first.evidence.request_id.startswith("fake_")
    assert first.choices["cte"].choice == "shipping"
    assert 0.0 < first.choices["cte"].confidence <= 1.0
    assert 0.0 <= first.nouls["lot"].probability <= 1.0
    assert set(first.scores["risk"].legend.values()) == {"low", "medium", "high"}
    assert first.to_dict()["choices"] == second.to_dict()["choices"]


def test_fake_with_nothing_to_go_on_is_flat_and_declines():
    answer = fake_jev.answer_choice(
        {"x": "zzz"}, {"instructions": "Which?", "criteria": {"alpha": "aaa", "beta": "bbb", "no_match": "neither"}}
    )

    assert answer["choice"] == "no_match"
    assert answer["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Question sets
# ---------------------------------------------------------------------------


def test_baseline_wording_is_exactly_what_production_asks(cases):
    columns = ["Ship Dte", "Cust Name"]
    base_hm = questions.baseline(questions.HEADER_MAPPING)
    base_cte = questions.baseline(questions.FILE_CTE)
    forbidden = [header for case in cases for header in case.headers]

    assert questions.header_questions(base_hm, columns) == hm.build_questions(columns)
    assert questions.cte_questions(base_cte) == cte.build_questions()
    assert base_hm.label == hm.QUESTIONS_VERSION and base_cte.label == cte.QUESTIONS_VERSION
    assert questions.validate(base_hm, reference=base_hm, forbidden_phrases=forbidden) == []
    assert questions.validate(base_cte, reference=base_cte, forbidden_phrases=forbidden) == []


def _patched(kind, **change):
    base = questions.baseline(kind)
    return base, questions.apply_patch(base, {"criteria": [change]} if "option" in change else change)


@pytest.mark.parametrize(
    "kind,patch,problem",
    [
        (questions.HEADER_MAPPING, {"option": "lot", "what": "A lot."}, "unknown option(s): lot"),
        (
            questions.HEADER_MAPPING,
            {"option": "ship_date", "examples": ["Ship Dte"]},
            "example 'Ship Dte' copies a labelled header",
        ),
        (questions.HEADER_MAPPING, {"option": "quantity", "what": ""}, "quantity: 'what' is empty"),
        (questions.HEADER_MAPPING, {"option": "quantity", "what": "x" * 401}, "'what' is 401 characters"),
        (questions.HEADER_MAPPING, {"task": "Map the column."}, "instructions no longer explain `column`"),
        (questions.HEADER_MAPPING, {"guidance": "Choose the best field."}, "no longer says when to choose no_match"),
        (questions.FILE_CTE, {"guidance": "Choose the event."}, "no longer says when to choose mixed_or_unclear"),
        (
            questions.FILE_CTE,
            {"option": "shipping", "examples": [f"Shipping column {i}" for i in range(13)]},
            "13 examples (limit 12)",
        ),
    ],
)
def test_validate_refuses_wording_that_breaks_a_rule(cases, kind, patch, problem):
    base, candidate = _patched(kind, **patch)
    forbidden = [header for case in cases for header in case.headers]

    problems = questions.validate(candidate, reference=base, forbidden_phrases=forbidden)

    assert any(problem in p for p in problems), problems


def test_validate_refuses_reordered_or_missing_options_and_growth():
    base = questions.baseline(questions.FILE_CTE)
    reordered = questions.QuestionSet(base.kind, base.task, base.guidance, dict(reversed(list(base.criteria.items()))))
    missing = questions.QuestionSet(base.kind, base.task, base.guidance, dict(list(base.criteria.items())[1:]))
    grown = questions.apply_patch(
        base, {"criteria": [{"option": name, "not_for": "y" * 300} for name in base.criteria]}
    )

    assert "options are reordered" in questions.validate(reordered, reference=base)
    assert any("missing option(s): harvesting" in p for p in questions.validate(missing, reference=base))
    assert any("over 1.5x the production size" in p for p in questions.validate(grown, reference=base))


def test_production_examples_stay_allowed_even_where_templates_use_them(cases):
    base = questions.baseline(questions.HEADER_MAPPING)
    forbidden = [header for case in cases for header in case.headers]
    candidate = questions.apply_patch(base, {"criteria": [{"option": "traceability_lot_code", "what": "The TLC."}]})

    assert questions.validate(candidate, reference=base, forbidden_phrases=forbidden) == []
    assert questions.changed_options(base, candidate) == ["traceability_lot_code"]


def test_reading_the_baseline_never_mutates_production():
    before = copy.deepcopy(hm.CANONICAL_FIELDS)
    base = questions.baseline(questions.HEADER_MAPPING)
    base.criteria["quantity"]["what"] = "changed"

    assert hm.CANONICAL_FIELDS == before


# ---------------------------------------------------------------------------
# Scoring parity with scripts/jev_eval.py
# ---------------------------------------------------------------------------


def test_lab_scores_production_wording_exactly_like_jev_eval(cases):
    assert scoring.parity_problems(cases) == []

    eval_bodies: list = []
    lab_bodies: list = []
    settings = jev_access.fake_settings()
    eval_decider = JevDecider(settings, transport=_recording(eval_bodies))
    lab_decider = JevDecider(settings, transport=_recording(lab_bodies))
    jev_eval.evaluate(cases, eval_decider)
    baselines = {kind: questions.baseline(kind) for kind in questions.KINDS}
    scoring.evaluate(cases, baselines, lab_decider, split={})

    def canonical(bodies):
        return sorted(json.dumps(body, sort_keys=True) for body in bodies)

    assert canonical(lab_bodies) == canonical(eval_bodies)
    assert all(set(body["state"]) <= {"csv_headers", "columns_to_map"} for body in lab_bodies)


def test_parity_tripwire_catches_request_drift_the_fake_cannot_score(cases, monkeypatch):
    original = cte._question

    def drifted(criteria):
        question = original(criteria)
        question["instructions"] = {**question["instructions"], "sample_policy": "headers only"}
        return question

    monkeypatch.setattr(cte, "_question", drifted)

    problems = scoring.parity_problems(cases)

    assert any(p.startswith("request bodies differ") for p in problems)
    assert not any("vs lab" in p for p in problems)  # the fake's answers alone would not show it


def test_order_check_reasks_confident_answers_with_options_reversed(cases, fake):
    baselines = {kind: questions.baseline(kind) for kind in questions.KINDS}
    observations = scoring.evaluate(cases, baselines, fake, split={}, order_check_at=0.9)
    mapping = [o for o in observations if o.kind == questions.HEADER_MAPPING]
    confident = [o for o in mapping if o.acts and o.confidence >= 0.9]

    assert confident
    assert all(o.order_consistent is not None for o in confident)
    assert all(o.order_consistent is None for o in mapping if not (o.acts and o.confidence >= 0.9))
    assert all(o.order_consistent is not None for o in observations if o.kind == questions.FILE_CTE)


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------


def test_split_is_by_case_stratified_and_stable(cases):
    split = scoring.split_cases(cases, salt="s1")
    extra = jev_eval.Case("extra", ("Ship Dt", "Cust"), frozenset({"shipping"}), {"Ship Dt": frozenset({"ship_date"})})
    grown = scoring.split_cases([*cases, extra], salt="s1")

    assert set(split) == {case.id for case in cases}
    assert {side for side in split.values()} == {scoring.TRAIN, scoring.HOLDOUT}
    assert all(grown[cid] == side for cid, side in split.items())
    strata: dict = {}
    for case in cases:
        strata.setdefault((bool(case.mappings), sorted(case.cte)[0] if case.cte else "-"), []).append(case.id)
    for members in strata.values():
        if len(members) >= 2:
            assert {split[cid] for cid in members} == {scoring.TRAIN, scoring.HOLDOUT}
    assert scoring.split_cases(cases, salt="s2") != split


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

HM = questions.HEADER_MAPPING


def _pair(train_before, train_after, hold_before, hold_after):
    incumbent = [_obs(HM, f"t{i}", "c", "train", **kw) for i, kw in enumerate(train_before)]
    incumbent += [_obs(HM, f"h{i}", "c", "holdout", **kw) for i, kw in enumerate(hold_before)]
    candidate = [_obs(HM, f"t{i}", "c", "train", **kw) for i, kw in enumerate(train_after)]
    candidate += [_obs(HM, f"h{i}", "c", "holdout", **kw) for i, kw in enumerate(hold_after)]
    return incumbent, candidate


RIGHT_LOW = {"correct": True, "confidence": 0.6}
RIGHT_HIGH = {"correct": True, "confidence": 0.95}
WRONG_LOW = {"correct": False, "confidence": 0.3}
WRONG_HIGH = {"correct": False, "confidence": 0.95}


def test_a_real_improvement_passes_both_stages():
    inc, cand = _pair([RIGHT_LOW, WRONG_LOW], [RIGHT_HIGH, WRONG_LOW], [RIGHT_LOW, RIGHT_LOW], [RIGHT_HIGH, RIGHT_LOW])

    reasons, _ = scoring.screen(HM, inc, cand, auto_apply=0.9)
    decision = scoring.decide(HM, inc, cand, margin=0.01, auto_apply=0.9)

    assert reasons == []
    assert decision.accepted, decision.reasons
    assert decision.paired["wins"] == 1 and decision.paired["losses"] == 0


def test_screen_stops_a_rewrite_that_does_not_help_training():
    inc, cand = _pair([RIGHT_HIGH, WRONG_LOW], [RIGHT_LOW, WRONG_LOW], [RIGHT_LOW], [RIGHT_HIGH])

    reasons, train = scoring.screen(HM, inc, cand, auto_apply=0.9)

    assert any("training Brier did not improve" in r for r in reasons)
    assert train["candidate"]["subjects"] == 2


@pytest.mark.parametrize(
    "hold_before,hold_after,reason",
    [
        ([RIGHT_LOW, RIGHT_LOW], [RIGHT_HIGH, WRONG_LOW], "1 held-out subject(s) went from right to wrong"),
        ([WRONG_LOW, RIGHT_LOW], [WRONG_HIGH, RIGHT_HIGH], "1 new held-out wrong answer(s) at auto-apply"),
        ([RIGHT_LOW, RIGHT_LOW], [{"correct": True, "confidence": 0.61}, RIGHT_LOW], "below the margin"),
        (
            [RIGHT_LOW, RIGHT_LOW, RIGHT_LOW],
            [RIGHT_HIGH, {"correct": True, "confidence": 0.55}, {"correct": True, "confidence": 0.55}],
            "improved 1, worsened 2: not more improved",
        ),
    ],
)
def test_each_failed_held_out_gate_is_named(hold_before, hold_after, reason):
    inc, cand = _pair([WRONG_LOW], [RIGHT_LOW], hold_before, hold_after)

    decision = scoring.decide(HM, inc, cand, margin=0.01, auto_apply=0.9)

    assert not decision.accepted
    assert any(reason in r for r in decision.reasons), decision.reasons


def test_new_order_flips_at_auto_apply_are_refused():
    flip = {"correct": True, "confidence": 0.97, "consistent": False}
    inc, cand = _pair([WRONG_LOW], [RIGHT_LOW], [RIGHT_LOW], [flip])

    decision = scoring.decide(HM, inc, cand, margin=0.01, auto_apply=0.9)

    assert any("new held-out order flip(s) at auto-apply" in r for r in decision.reasons)


def test_gates_compare_subject_by_subject_not_totals():
    # A swap that keeps every total: one subject turns wrong at auto-apply while another is fixed.
    swap_before = [{"correct": True, "confidence": 0.8}, WRONG_HIGH, RIGHT_LOW, RIGHT_LOW]
    swap_after = [WRONG_HIGH, RIGHT_HIGH, {"correct": True, "confidence": 0.92}, {"correct": True, "confidence": 0.92}]
    inc, cand = _pair(swap_before, swap_after, swap_before, swap_after)

    reasons, _ = scoring.screen(HM, inc, cand, auto_apply=0.9)
    decision = scoring.decide(HM, inc, cand, margin=0.01, auto_apply=0.9)

    assert any("went from right to wrong" in r for r in reasons)
    assert any("new training wrong answer(s) at auto-apply" in r for r in reasons)
    assert not decision.accepted
    assert any("went from right to wrong" in r for r in decision.reasons)


def test_noise_allows_as_many_lost_answers_as_jev_flips_by_itself():
    inc, cand = _pair([WRONG_LOW], [RIGHT_LOW], [RIGHT_LOW, RIGHT_LOW, RIGHT_LOW], [RIGHT_HIGH, RIGHT_HIGH, WRONG_LOW])

    strict = scoring.decide(HM, inc, cand, margin=0.01, auto_apply=0.9)
    noisy = scoring.decide(HM, inc, cand, margin=0.01, auto_apply=0.9, allowed_flips=1)

    assert any("went from right to wrong (noise allows 0)" in r for r in strict.reasons)
    assert not any("went from right to wrong" in r for r in noisy.reasons)


# ---------------------------------------------------------------------------
# What Claude gets
# ---------------------------------------------------------------------------


def test_brief_carries_training_cases_only(cases, fake):
    split = scoring.split_cases(cases, salt=ACCEPTING_SALT)
    baselines = {kind: questions.baseline(kind) for kind in questions.KINDS}
    observations = scoring.evaluate(cases, baselines, fake, split=split)
    headers = {case.id: list(case.headers) for case in cases}

    brief = proposer.build_brief(baselines, observations, headers, [], auto_apply=0.9)

    train = {cid for cid, side in split.items() if side == scoring.TRAIN}
    assert proposer.brief_case_ids(brief) <= train
    assert proposer.brief_case_ids(brief)
    assert privacy.findings(brief) == []
    prompt = proposer.render_prompt(brief)
    assert "Never copy a header from the data into `examples`" in prompt


def test_history_tells_claude_one_bit_about_held_out():
    proposal = proposer.Proposal({HM: None, questions.FILE_CTE: None}, "why", "offline")
    results = {
        HM: {
            "accepted": False,
            "stage": "holdout",
            "reasons": ["held-out Brier gain +0.0042 is below the margin 0.0100"],
            "holdout": {"incumbent": {"brier": 0.2142}, "candidate": {"brier": 0.21}},
            "train": {
                "incumbent": {"brier": 0.3, "correct": 4, "wrong_at_auto_apply": 0},
                "candidate": {"brier": 0.25, "correct": 5, "wrong_at_auto_apply": 0},
            },
            "changed": ["quantity"],
        },
        questions.FILE_CTE: {"accepted": False, "stage": "screen", "reasons": ["training Brier did not improve"]},
    }

    entry = loop.public_history(1, "rejected", proposal, results, {"predicted": 0})
    text = json.dumps(entry)

    assert entry["kinds"][HM]["held_out_check"] == "not kept"
    assert entry["kinds"][HM]["training"]["brier"] == [0.3, 0.25]
    assert "0.0042" not in text and "0.2142" not in text and "held-out Brier" not in text
    assert entry["kinds"][questions.FILE_CTE]["held_out_check"] == "not run: the training split did not improve"


def test_copying_a_held_out_header_is_turned_away_by_the_held_out_check(tmp_path, cases, fake):
    lab = _home(tmp_path)
    split = scoring.split_cases(cases, salt=ACCEPTING_SALT)
    train = {questions.normalize_phrase(h) for case in cases if split[case.id] == scoring.TRAIN for h in case.headers}
    held_out = next(
        header
        for case in cases
        if split[case.id] == scoring.HOLDOUT
        for header in case.mappings
        if questions.normalize_phrase(header) not in train
    )

    class CopyingHeuristic:
        """The offline heuristic's training-improving patch, plus one copied held-out header."""

        name = "copying"

        def propose(self, brief):
            proposal = proposer.OfflineProposer().propose(brief)
            patch = proposal.patches[HM]
            if patch:
                first = dict(patch["criteria"][0])
                current = brief["kinds"][HM]["wording"]["criteria"][first["option"]].get("examples", [])
                first["examples"] = [*current[:10], held_out]
                patch = {**patch, "criteria": [first, *patch["criteria"][1:]]}
            return proposer.Proposal({HM: patch, questions.FILE_CTE: None}, "copy", "copying")

    recorder = _Recording(CopyingHeuristic())

    loop.run_loop(ledger=lab, decider=fake, proposer=recorder, config=loop.LoopConfig(generations=2, patience=5))

    decision = lab.generations()[0]["decisions"][HM]
    assert decision["stage"] == "holdout"  # it passed the training screen, and validation did not name it
    assert decision["reasons"] == ["an example copies a held-out or fresh header"]
    judged = sum(1 for g in lab.generations() if (g.get("decisions") or {}).get(HM, {}).get("stage") == "holdout")
    assert lab.epoch()["looks"][HM] == judged >= 1
    history = json.dumps(recorder.briefs[1]["history"])
    assert '"held_out_check": "not kept"' in history
    assert "copies" not in history and held_out not in history


def test_holdout_leak_scan_ignores_wording_but_catches_data():
    brief = {
        "kinds": {
            HM: {"wording": {"criteria": {"x": {"what": "Sealed Header"}}}, "misses": [{"column": "Sealed Header"}]}
        },
        "history": [],
    }

    assert loop.holdout_leaks(brief, {"sealedheader"}) == ["Sealed Header"]
    brief["kinds"][HM]["misses"] = []
    assert loop.holdout_leaks(brief, {"sealedheader"}) == []

    base = questions.baseline(HM)
    copied = questions.apply_patch(base, {"criteria": [{"option": "carrier", "examples": ["Hauler", "Sealed Header"]}]})
    assert loop.copies_secret_header(copied, base, {"sealedheader"})
    assert not loop.copies_secret_header(base, base, {"hauler"})


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


class _Recording:
    """Wraps a proposer and keeps every brief it was handed."""

    def __init__(self, inner):
        self.inner = inner
        self.name = inner.name
        self.briefs: list = []

    def propose(self, brief):
        self.briefs.append(copy.deepcopy(brief))
        return self.inner.propose(brief)


def test_loop_runs_end_to_end_and_keeps_what_generalises(tmp_path, cases, fake):
    lab = _home(tmp_path, ACCEPTING_SALT)
    production = (copy.deepcopy(hm.CANONICAL_FIELDS), copy.deepcopy(cte.CTE_CRITERIA))
    events: list = []
    recorder = _Recording(proposer.OfflineProposer())

    summary = loop.run_loop(
        ledger=lab,
        decider=fake,
        proposer=recorder,
        config=loop.LoopConfig(generations=4),
        emit=lambda e, d: events.append(e),
    )

    assert summary["accepted"] >= 1
    assert (hm.CANONICAL_FIELDS, cte.CTE_CRITERIA) == production
    assert hm.QUESTIONS_VERSION == "csv-header-mapping.v3" and cte.QUESTIONS_VERSION == "csv-file-cte.v2"
    kinds = {e for e in events}
    assert {"run_started", "parity", "evaluated", "noise", "proposal", "generation_done", "run_done"} <= kinds
    generations = lab.generations()
    assert [g["generation"] for g in generations] == list(range(1, len(generations) + 1))
    first = generations[0]
    assert first["outcome"] == "accepted" and first["foresight"]["predicted"] >= 1
    holdout_judgements = sum(
        1 for g in generations for d in (g.get("decisions") or {}).values() if d.get("stage") == "holdout"
    )
    assert sum(lab.epoch()["looks"].values()) == holdout_judgements
    split = scoring.split_cases(loop.load_all_cases(lab), salt=ACCEPTING_SALT)
    train = {cid for cid, side in split.items() if side == scoring.TRAIN}
    assert all(proposer.brief_case_ids(brief) <= train for brief in recorder.briefs)

    kept = lab.incumbents()
    assert any(kept[kind].label.startswith("lab-") for kind in first["accepted"])
    again = loop.run_loop(
        ledger=lab, decider=fake, proposer=proposer.OfflineProposer(), config=loop.LoopConfig(generations=0)
    )
    assert again["incumbents"] == summary["incumbents"]


def test_loop_rejects_everything_when_nothing_generalises(tmp_path, fake):
    lab = _home(tmp_path, REJECTING_SALT)

    summary = loop.run_loop(
        ledger=lab, decider=fake, proposer=proposer.OfflineProposer(), config=loop.LoopConfig(generations=5)
    )

    assert summary["accepted"] == 0
    assert summary["stopped"] == "no improvement in 3 generations"
    assert all(kind.label.startswith("csv-") for kind in lab.incumbents().values())


class _Scripted:
    name = "scripted"

    def __init__(self, *results):
        self.results = list(results)

    def propose(self, brief):
        result = self.results.pop(0) if self.results else proposer.ProposerError("out of ideas")
        if isinstance(result, Exception):
            raise result
        return result


def test_invalid_wording_and_proposer_failures_are_recorded_not_raised(tmp_path, fake):
    lab = _home(tmp_path)
    rename = proposer.Proposal(
        {HM: {"task": None, "guidance": None, "criteria": [{"option": "lot", "what": "x"}]}, questions.FILE_CTE: None},
        "rename an option",
        "scripted",
    )
    scripted = _Scripted(rename, proposer.ProposerError("claude exited 1: error"))

    summary = loop.run_loop(ledger=lab, decider=fake, proposer=scripted, config=loop.LoopConfig(generations=5))

    outcomes = [(g["outcome"], (g.get("decisions") or {}).get(HM, {}).get("stage")) for g in lab.generations()]
    assert outcomes[0] == ("rejected", "invalid")
    assert outcomes[1] == ("no_proposal", None)
    assert summary["stopped"] == "no improvement in 3 generations"
    assert sum(lab.epoch()["looks"].values()) == 0


def test_loop_stops_at_the_held_out_cap_and_on_request(tmp_path, fake):
    capped = _home(tmp_path / "a", looks={kind: ledger.MAX_HOLDOUT_LOOKS for kind in questions.KINDS})
    summary = loop.run_loop(ledger=capped, decider=fake, proposer=proposer.OfflineProposer())
    assert summary["stopped"].startswith("held-out split used 12 times")

    stop = threading.Event()
    stop.set()
    stopped = loop.run_loop(ledger=_home(tmp_path / "b"), decider=fake, proposer=proposer.OfflineProposer(), stop=stop)
    assert stopped["stopped"] == "stop requested" and stopped["generations"] == 0


def test_loop_stops_cleanly_when_the_jev_budget_runs_out(tmp_path):
    decider = jev_access.LabDecider(jev_access.build_decider(jev_access.FAKE), mode=jev_access.FAKE, max_requests=5)

    summary = loop.run_loop(ledger=_home(tmp_path), decider=decider, proposer=proposer.OfflineProposer())

    assert summary["stopped"] == "jev unavailable:lab_budget"
    assert decider.stats()["sent"] == 5


class _Outage:
    """A LabDecider stand-in that answers until ``after`` requests, then reports Jev unavailable."""

    def __init__(self, inner, after):
        self.inner, self.after, self.mode, self.calls = inner, after, inner.mode, 0

    settings = property(lambda self: self.inner.settings)
    enabled = property(lambda self: self.inner.enabled)

    def stats(self):
        return self.inner.stats()

    def ask(self, *args, **kwargs):
        self.calls += 1
        if self.calls > self.after:
            raise JevUnavailable("rate_limited", purpose=kwargs.get("purpose", "x"))
        return self.inner.ask(*args, **kwargs)


def test_a_jev_outage_mid_run_is_a_jev_failure_not_a_verdict(tmp_path, fake):
    lab = _home(tmp_path)
    first = loop.run_loop(
        ledger=lab, decider=fake, proposer=proposer.OfflineProposer(), config=loop.LoopConfig(generations=0)
    )
    flaky = _Outage(fake, after=first["jev"]["sent"] + first["jev"]["cache_hits"] + 1)
    lab2 = _home(tmp_path / "again")

    summary = loop.run_loop(
        ledger=lab2, decider=flaky, proposer=proposer.OfflineProposer(), config=loop.LoopConfig(generations=3)
    )

    assert summary["stopped"] == "jev unavailable:rate_limited"
    assert sum(lab2.epoch()["looks"].values()) == 0
    assert [g["outcome"] for g in lab2.generations()] == ["jev_unavailable"]
    with pytest.raises(JevUnavailable):
        loop.evaluate_once(lab2, _Outage(fake, after=0))


def test_estimate_bounds_what_a_run_sends(tmp_path, cases):
    decider = jev_access.LabDecider(jev_access.build_decider(jev_access.FAKE), mode=jev_access.FAKE)
    lab = _home(tmp_path)

    loop.run_loop(
        ledger=lab, decider=decider, proposer=proposer.OfflineProposer(), config=loop.LoopConfig(generations=3)
    )
    estimate = loop.run_estimate(cases, lab.epoch()["assignment"], generations=3)

    assert decider.stats()["sent"] <= estimate["jev_requests_max"]
    assert estimate["claude_calls_max"] == 3


def test_fresh_rows_are_kept_from_the_loop_for_confirmation(tmp_path, fake):
    lab = _home(tmp_path)
    loop.load_all_cases(lab)  # the first use of the epoch fixes its split
    lab.add_case(
        {
            "id": "local-fresh",
            "headers": ["Pick Dt", "Grower"],
            "cte": "harvesting",
            "mappings": {"Pick Dt": "harvest_date"},
        }
    )

    assert "local-fresh" not in {case.id for case in loop.load_all_cases(lab)}
    assert [case.id for case in loop.fresh_cases(lab)] == ["local-fresh"]
    result = loop.confirm(lab, fake, questions.baseline(HM))
    assert result["fresh_subjects"] == 1 and result["sufficient"] is False

    lab.rotate_split()
    assert "local-fresh" in {case.id for case in loop.load_all_cases(lab)}
    assert loop.fresh_cases(lab) == []


def test_the_epoch_pins_each_case_to_its_side(tmp_path):
    lab = _home(tmp_path)
    before = {case.id for case in loop.load_all_cases(lab)}
    assignment = dict(lab.epoch()["assignment"])
    lab.add_case({"id": "local-x", "headers": ["Txn Kind", "Lot Ref"], "cte": "mixed_or_unclear"})
    first = lab.local_cases()[0]["labelled_at"]
    lab.add_case({"id": "local-x", "headers": ["Txn Kind", "Lot Ref"], "cte": "receiving"})

    assert {case.id for case in loop.load_all_cases(lab)} == before
    assert lab.epoch()["assignment"] == assignment
    assert lab.local_cases()[0]["labelled_at"] == first
    assert [case.id for case in loop.fresh_cases(lab)] == ["local-x"]


def test_a_rotation_during_a_run_stops_it(tmp_path, fake):
    lab = _home(tmp_path)

    class Rotating(_Scripted):
        def propose(self, brief):
            lab.rotate_split()
            return proposer.OfflineProposer().propose(brief)

    summary = loop.run_loop(ledger=lab, decider=fake, proposer=Rotating(), config=loop.LoopConfig(generations=3))

    assert summary["stopped"] == "the split was rotated during the run"
    assert sum(lab.epoch()["looks"].values()) == 0
    assert all(qs.label.startswith("csv-") for qs in lab.incumbents().values())


def test_fake_and_live_ledgers_never_mix(tmp_path, fake):
    live = ledger.Ledger(tmp_path / "lab", mode=ledger.LIVE)

    with pytest.raises(ValueError, match="cannot write to the live ledger"):
        loop.run_loop(ledger=live, decider=fake, proposer=proposer.OfflineProposer())
    assert ledger.Ledger(tmp_path / "lab", mode=ledger.FAKE).state_dir == tmp_path / "lab" / "fake"
    assert live.cases_path == ledger.Ledger(tmp_path / "lab", mode=ledger.FAKE).cases_path


def test_a_tainted_labelled_row_is_refused_before_anything_is_sent(tmp_path, fake):
    """cases.local.json can be edited by hand: a row that must not leave is refused on every load."""
    lab = _home(tmp_path)
    lab.add_case({"id": "local-ok", "headers": ["Ship Dte", "Lot No."], "cte": "shipping", "mappings": {}})
    lab.add_case({"id": "local-bad", "headers": ["Ship Dte", "jane@example.com"], "cte": None, "mappings": {}})

    with pytest.raises(privacy.Refused) as refused:
        loop.every_case(lab)
    message = str(refused.value)
    assert "cases.local.json case 'local-bad'" in message and "personal data" in message
    assert "jane" not in message and "example.com" not in message
    with pytest.raises(privacy.Refused):
        loop.run_loop(ledger=lab, decider=fake, proposer=proposer.OfflineProposer())
    assert fake.stats()["sent"] == 0

    # A row of values, or a secret in a label, is refused the same way.
    lab.add_case({"id": "local-bad", "headers": ["2024-04-23", "LOT-R-0423", "240"], "cte": None, "mappings": {}})
    with pytest.raises(privacy.Refused, match="look like values"):
        loop.every_case(lab)


def test_every_field_of_a_hand_edited_row_is_checked_and_never_echoed(tmp_path, fake):
    """A secret in the label or the id would be repeated by the validation message: it is refused first."""
    token = "Zq7w9x2y4v8u1t3s5r6p0o9n8m7l6k5j4h3g2f1"  # pragma: allowlist secret
    lab = _home(tmp_path)
    lab.add_case({"id": "local-label", "headers": ["Ship Dte", "Lot No."], "cte": token, "mappings": {}})
    lab.add_case({"id": "jane.doe@example.com", "headers": ["Ship Dte", "Lot No."], "cte": "shipping", "mappings": {}})

    with pytest.raises(privacy.Refused) as refused:
        loop.every_case(lab)
    message = str(refused.value)
    assert "cases.local.json case 'local-label': key-like token at $.cte" in message
    assert "cases.local.json case <row 2>: personal data" in message and "at $.id" in message
    assert token not in message and "jane" not in message and "example.com" not in message
    with pytest.raises(privacy.Refused):
        loop.run_loop(ledger=lab, decider=fake, proposer=proposer.OfflineProposer())
    assert fake.stats()["sent"] == 0


def test_a_value_like_label_mapping_or_id_is_refused_before_a_message_could_repeat_it(tmp_path):
    """A lot code, a date or an SSCC where a label belongs matches no secret pattern, yet jev_eval would repeat it."""
    lab = _home(tmp_path)
    lab.add_case({"id": "local-lot", "headers": ["Ship Dte", "Lot No."], "cte": "LOT-R-0423", "mappings": {}})
    lab.add_case(
        {
            "id": "local-map",
            "headers": ["Ship Dte", "Lot No."],
            "cte": "shipping",
            "mappings": {"Ship Dte": "2024-04-23", "003401234567890123": "lot_code"},
        }
    )
    lab.add_case({"id": "012345678905", "headers": ["Ship Dte", "Lot No."], "cte": "shipping", "mappings": {}})

    with pytest.raises(privacy.Refused) as refused:
        loop.every_case(lab)
    message = str(refused.value)
    assert "case 'local-lot': looks like a value (date, number or code), not a label at $.cte" in message
    assert "case 'local-map': looks like a value (date, number or code), not a label at $.mappings.Ship Dte" in message
    assert "case 'local-map': looks like a value (date, number or code), not a label at $.mappings.<key 2>" in message
    assert "case <row 3>: looks like a value (date, number or code), not a label at $.id" in message
    for value in ("LOT-R-0423", "2024-04-23", "003401234567890123", "012345678905"):
        assert value not in message
    # The page's own ids hold digits by design and are never mistaken for values.
    assert privacy.value_findings({"id": "local-123456abcdef"}, codes=False) == []
    assert privacy.value_findings({"cte": "shipping", "mappings": {"Lot No.": "lot_code"}}) == []


def test_a_row_that_is_not_a_case_object_is_refused_by_position(tmp_path):
    lab = _home(tmp_path)
    lab.add_case({"id": "local-ok", "headers": ["Ship Dte", "Lot No."], "cte": "shipping", "mappings": {}})
    data = json.loads(lab.cases_path.read_text())
    data["cases"] += ["not a row", {"id": ["x"], "headers": ["Ship Dte"]}]
    lab.cases_path.write_text(json.dumps(data))

    with pytest.raises(ledger.LabStateError, match=r"cases\.local\.json row 2 is not a case object with a string id"):
        loop.every_case(lab)
    with pytest.raises(ledger.LabStateError, match="row 2"):
        lab.add_case({"id": "local-new", "headers": ["Pick Dt"], "cte": None, "mappings": {}})


def test_a_refusal_counts_rows_as_the_file_does(tmp_path):
    """Row 1 reuses a repository case id and is dropped; the tainted row is still called row 2."""
    lab = _home(tmp_path)
    repo_id = jev_eval.load_cases(jev_eval.DEFAULT_CASES, templates=False)[0].id
    lab.add_case({"id": repo_id, "headers": ["Ship Dte", "Lot No."], "cte": "shipping", "mappings": {}})
    lab.add_case({"id": "jane.doe@example.com", "headers": ["Ship Dte", "Lot No."], "cte": "shipping", "mappings": {}})

    with pytest.raises(privacy.Refused, match=r"case <row 2>: personal data"):
        loop.every_case(lab)


def test_an_edited_question_set_label_parent_or_notes_is_refused_by_shape_not_value(tmp_path):
    """Label, parent and notes sit outside the digest: a hand-edited file is held to the lab's shapes."""
    token = "Zq7w9x2y4v8u1t3s5r6p0o9n8m7l6k5j4h3g2f1"  # pragma: allowlist secret
    lab = _home(tmp_path)
    base = questions.baseline(questions.HEADER_MAPPING)
    rewrite = questions.apply_patch(base, {"guidance": "A rewrite."})
    ours = rewrite.with_label(
        "lab-3f9a8b7c6d5e-g1-header_mapping", parent=base.digest, notes=("header_mapping:guidance:shorter",)
    )
    digest = lab.save_set(ours)
    assert lab.load_set(digest) == ours  # the lab's own label, parent and notes pass
    lab.record_incumbent(ours, generation=1, run_id="r", salt=lab.epoch()["salt"])
    path = lab.sets_dir / f"{digest}.json"
    good = json.loads(path.read_text())

    for field, bad, why in (
        ("label", token, r"must not leave \(key-like token at \$\.label\)"),
        ("label", "jane.doe@example.com", "wrong shape"),
        ("parent", {"owner": "jane.doe@example.com"}, "wrong shape"),
    ):
        path.write_text(json.dumps({**good, field: bad}))
        with pytest.raises(ledger.LabStateError, match=why) as raised:
            lab.load_set(digest)
        assert path.name in str(raised.value) and token not in str(raised.value) and "jane" not in str(raised.value)
        with pytest.raises(ledger.LabStateError):
            lab.incumbents()
    path.write_text(json.dumps({**good, "notes": ["header_mapping:guidance:shorter", "mailto jane.doe@example.com"]}))
    with pytest.raises(ledger.LabStateError, match=r"must not leave \(personal data .* at \$\.notes\[1\]\)") as raised:
        lab.load_set(digest)
    assert "jane" not in str(raised.value)


def test_edited_wording_or_a_value_like_label_in_a_question_set_is_refused(tmp_path):
    """The digest proves the wording is the one the file names, not that it is clean: it is scanned too."""
    lab = _home(tmp_path)
    base = questions.baseline(questions.HEADER_MAPPING)
    data = base.to_dict()
    data["guidance"] = data["guidance"] + " Ask jane.doe@example.com when unsure."
    edited = questions.QuestionSet.from_dict(data)
    (lab.sets_dir / f"{edited.digest}.json").write_text(json.dumps(edited.to_dict()))
    with pytest.raises(
        ledger.LabStateError, match=r"must not leave \(personal data .* at \$\.wording\.guidance\)"
    ) as raised:
        lab.load_set(edited.digest)
    assert "jane" not in str(raised.value)

    digest = lab.save_set(
        questions.apply_patch(base, {"guidance": "Shorter."}).with_label("LOT-R-0423", parent=base.digest)
    )
    with pytest.raises(ledger.LabStateError, match=r"looks like a value .* at \$\.label") as raised:
        lab.load_set(digest)
    assert "LOT-R-0423" not in str(raised.value)
    for kind in questions.KINDS:  # the production wording and labels pass
        assert lab.load_set(lab.save_set(questions.baseline(kind))) == questions.baseline(kind)


def test_a_hand_written_id_is_held_to_the_code_heuristic_but_the_page_s_own_ids_pass(tmp_path):
    lab = _home(tmp_path)
    lab.add_case({"id": "local-123456abcdef", "headers": ["Ship Dte", "Lot No."], "cte": "shipping", "mappings": {}})
    assert [case.id for case in loop.every_case(lab) if case.id.startswith("local-")] == ["local-123456abcdef"]
    lab.add_case({"id": "LOT-R-0423", "headers": ["Pick Dt", "Grower"], "cte": "harvesting", "mappings": {}})
    with pytest.raises(privacy.Refused, match=r"case <row 2>: looks like a value .* at \$\.id") as refused:
        loop.every_case(lab)
    assert "LOT-R-0423" not in str(refused.value)


def test_a_cached_jev_answer_row_edited_by_hand_is_skipped_at_load(tmp_path):
    cache = tmp_path / "cache.jsonl"
    decider = jev_access.LabDecider(jev_access.build_decider(jev_access.FAKE), mode=jev_access.FAKE, cache_path=cache)
    state = {"csv_headers": ["Distinctive Header Name"]}
    questions_ = {"q": {"type": "noul", "instructions": "Is it a date?"}}
    decider.ask(state, questions_, purpose="t")
    row = json.loads(cache.read_text().splitlines()[0])
    row["answers"]["evidence"]["jane.doe@example.com"] = 1
    cache.write_text(json.dumps(row) + "\n")

    reloaded = jev_access.LabDecider(jev_access.build_decider(jev_access.FAKE), mode=jev_access.FAKE, cache_path=cache)
    reloaded.ask(state, questions_, purpose="t")  # the edited row is not a cache hit, and never a TypeError
    assert reloaded.stats()["sent"] == 1 and reloaded.stats()["cache_hits"] == 0


def test_an_unreadable_split_epoch_is_refused_without_repeating_it(tmp_path):
    token = "Zq7w9x2y4v8u1t3s5r6p0o9n8m7l6k5j4h3g2f1"  # pragma: allowlist secret
    lab = _home(tmp_path)
    for broken in (
        {"looks": {"header_mapping": token}},
        {"looks": [1]},
        {"looks": {token: 1}},
        {"assignment": {"c1": ["train"]}},
        {"assignment": {"c1": "elsewhere"}},
        {"created": {"at": token}},
    ):
        lab.split_path.write_text(json.dumps({"salt": "s", "created": "2026-01-01T00:00:00Z", "looks": {}, **broken}))
        with pytest.raises(ledger.LabStateError, match="split.json is unreadable") as raised:
            lab.epoch()
        assert token not in str(raised.value)


def test_a_ledger_line_that_is_not_a_record_is_skipped(tmp_path):
    lab = _home(tmp_path)
    lab.append({"type": "noise"})
    with lab.path.open("a", encoding="utf-8") as stream:
        stream.write('"a bare string"\n[1, 2]\n42\n')
        stream.write('{"type": "generation", "run_id": ["x"]}\n{"type": "generation", "candidates": []}\n')

    assert [row["type"] for row in lab.rows()] == ["noise"]
    assert lab.generations() == [] and lab.incumbents()


def test_a_question_set_file_that_no_longer_matches_its_digest_is_refused(tmp_path):
    lab = _home(tmp_path)
    base = questions.baseline(questions.HEADER_MAPPING)
    digest = lab.save_set(base)
    assert lab.load_set(digest).digest == digest  # the file round-trips to the digest that names it

    path = lab.sets_dir / f"{digest}.json"
    data = json.loads(path.read_text())
    data["guidance"] = (data.get("guidance") or "") + " Edited by hand."
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="does not match its digest"):
        lab.load_set(digest)


def test_labelled_rows_are_locked_on_the_shared_file_in_both_modes(tmp_path):
    live = ledger.Ledger(tmp_path / "lab", mode=ledger.LIVE)
    fake_view = ledger.Ledger(tmp_path / "lab", mode=ledger.FAKE)
    assert live.cases_lock == fake_view.cases_lock == tmp_path / "lab" / ".cases.lock"
    assert live.cases_lock.parent == live.cases_path.parent

    fake_view.add_case({"id": "local-a", "headers": ["Ship Dte", "Lot No."], "cte": "shipping", "mappings": {}})
    live.add_case({"id": "local-b", "headers": ["Recv Dte", "Lot No."], "cte": "receiving", "mappings": {}})
    assert live.cases_lock.exists()
    assert {c["id"] for c in live.local_cases()} == {"local-a", "local-b"}


def test_a_refusal_never_repeats_a_key_that_must_not_leave():
    """A labelled header is a mapping key: a secret or an address in it is given by position, not text."""
    token = "Zq7w9x2y4v8u1t3s5r6p0o9n8m7l6k5j4h3g2f1"  # pragma: allowlist secret
    reasons = privacy.findings({"mappings": {"Ship Dte": "ship_date", token: "quantity", "jane.doe@example.com": "x"}})
    joined = " ".join(reasons)
    assert "key-like token at $.mappings.<key 2>" in reasons
    assert any(r.startswith("personal data") and r.endswith("at $.mappings.<key 3>") for r in reasons)
    assert token not in joined and "jane" not in joined and "example.com" not in joined
    # A clean key is still named, so a reason stays readable.
    assert privacy.findings({"gln": "1234567890128"}) == ["GLN or GTIN number at $.gln"]


def test_an_edited_superseded_question_set_never_blocks_the_lab(tmp_path):
    lab = _home(tmp_path)
    salt = lab.epoch()["salt"]
    base = questions.baseline(questions.HEADER_MAPPING)
    first = questions.apply_patch(base, {"guidance": "First rewrite."}).with_label("g1", parent=base.digest)
    second = questions.apply_patch(base, {"guidance": "Second rewrite."}).with_label("g2", parent=base.digest)
    lab.record_incumbent(first, generation=1, run_id="r", salt=salt)
    lab.record_incumbent(second, generation=2, run_id="r", salt=salt)

    old = lab.sets_dir / f"{first.digest}.json"
    data = json.loads(old.read_text())
    data["guidance"] = "Edited by hand."
    old.write_text(json.dumps(data))

    assert lab.incumbents()[questions.HEADER_MAPPING].label == "g2"  # the winner is the only file read
    lab.reset()
    assert lab.incumbents()[questions.HEADER_MAPPING].label == base.label


def test_an_unreadable_or_misfiled_question_set_is_refused_by_name(tmp_path):
    lab = _home(tmp_path)
    base = questions.baseline(questions.HEADER_MAPPING)
    digest = lab.save_set(base)
    path = lab.sets_dir / f"{digest}.json"
    assert not list(lab.sets_dir.glob("*.tmp"))  # written atomically, nothing half-done left behind

    for broken in ("", "{", "[]", json.dumps({"task": "x"})):
        path.write_text(broken)
        with pytest.raises(ledger.LabStateError, match="is unreadable") as raised:
            lab.load_set(digest)
        assert str(path) in str(raised.value)

    # The kind is outside the digest: a file whose kind was edited is caught where the ledger names its kind.
    lab.record_incumbent(base, generation=1, run_id="r", salt=lab.epoch()["salt"])
    data = base.to_dict()
    data["kind"] = "file_cte"
    path.write_text(json.dumps(data))
    with pytest.raises(ledger.LabStateError, match="names it the header_mapping incumbent"):
        lab.incumbents()
    data["kind"] = "not-a-kind"
    path.write_text(json.dumps(data))
    with pytest.raises(ledger.LabStateError, match="does not match its digest"):
        lab.load_set(digest)

    path.unlink()
    assert lab.load_set(digest) is None  # deleted, as the message advises: no such set


def test_a_hand_edited_row_that_fails_validation_names_the_cases_file(tmp_path):
    lab = _home(tmp_path)
    lab.add_case({"id": "local-bogus", "headers": ["Ship Dte", "Lot No."], "cte": "bogus", "mappings": {}})

    with pytest.raises(ledger.LabStateError) as raised:
        loop.every_case(lab)
    message = str(raised.value)
    assert "cases.local.json" in message and "local-bogus" in message and ".cases-" not in message
    assert message.endswith("fix or delete the row")

    lab.cases_path.write_text("{not json")
    with pytest.raises(ledger.LabStateError, match="is not JSON"):
        loop.every_case(lab)


def test_a_live_ledger_ignores_fake_wording_left_by_an_older_lab(tmp_path):
    """Before fake runs moved to <home>/fake they wrote to <home>/ledger.jsonl, rows without ``mode``."""
    live = ledger.Ledger(tmp_path / "lab", mode=ledger.LIVE)
    live.ensure()
    live.split_path.write_text(json.dumps({"salt": "old-salt", "created": "2026-01-01T00:00:00Z", "looks": {}}))
    base = questions.baseline(questions.HEADER_MAPPING)
    rewrite = questions.apply_patch(base, {"guidance": "A rewrite the offline fake kept."})
    rewrite = rewrite.with_label("lab-old-g1-header_mapping", parent=base.digest)
    legacy = [
        {
            "type": "generation",
            "run_id": "old",
            "generation": 1,
            "jev": {"mode": "fake"},
            "accepted": ["header_mapping"],
        },
        {
            "type": "incumbent",
            "kind": "header_mapping",
            "digest": live.save_set(rewrite),
            "label": rewrite.label,
            "generation": 1,
            "run_id": "old",
            "baseline_digest": questions.baseline(questions.HEADER_MAPPING).digest,
            "epoch": "old-salt",
        },
    ]
    live.path.write_text("".join(json.dumps(row) + "\n" for row in legacy))

    assert live.incumbents()[questions.HEADER_MAPPING].label == questions.baseline(questions.HEADER_MAPPING).label
    assert live.judged_by_fake(rewrite.digest)
    assert not live.judged_by_fake(questions.baseline(questions.HEADER_MAPPING).digest)
    # An older fake run cut off before its generation row left no fake marker, and no live evidence either.
    live.path.write_text(json.dumps(legacy[1]) + "\n")
    assert live.incumbents()[questions.HEADER_MAPPING].label == questions.baseline(questions.HEADER_MAPPING).label
    # Wording live Jev judged (its rows say so) is trusted.
    live_row = {**legacy[1], "run_id": "new", "mode": "live"}
    live.path.write_text(json.dumps(legacy[1]) + "\n" + json.dumps(live_row) + "\n")
    assert live.incumbents()[questions.HEADER_MAPPING].label == "lab-old-g1-header_mapping"
    assert not live.judged_by_fake(rewrite.digest)
    # The same rows, read as the fake ledger they were, still count there.
    fake_view = ledger.Ledger(tmp_path / "lab", mode=ledger.FAKE)
    fake_view.ensure()
    fake_view.path.write_text(live.path.read_text())
    fake_view.split_path.write_text(live.split_path.read_text())
    fake_view.save_set(rewrite)
    assert fake_view.incumbents()[questions.HEADER_MAPPING].label == "lab-old-g1-header_mapping"


# ---------------------------------------------------------------------------
# Budget and cache
# ---------------------------------------------------------------------------


def test_cache_answers_identical_requests_and_never_stores_the_request(tmp_path):
    cache = tmp_path / "cache.jsonl"
    decider = jev_access.LabDecider(
        jev_access.build_decider(jev_access.FAKE), mode=jev_access.FAKE, max_requests=2, cache_path=cache
    )
    state = {"csv_headers": ["Distinctive Header Name"]}
    questions_ = {"q": {"type": "noul", "instructions": "Is it a date?"}}

    first = decider.ask(state, questions_, purpose="t")
    again = decider.ask(state, questions_, purpose="t")
    jev_access.Uncached(decider).ask(state, questions_, purpose="t")

    assert first.to_dict() == again.to_dict()
    assert decider.stats() | {} == decider.stats() and decider.stats()["sent"] == 2
    assert decider.stats()["cache_hits"] == 1
    with pytest.raises(JevUnavailable) as raised:
        decider.ask({"other": 1}, questions_, purpose="t")
    assert raised.value.reason == "lab_budget"
    assert "Distinctive Header Name" not in cache.read_text()
    reloaded = jev_access.LabDecider(jev_access.build_decider(jev_access.FAKE), mode=jev_access.FAKE, cache_path=cache)
    reloaded.ask(state, questions_, purpose="t")
    assert reloaded.stats()["sent"] == 0


# ---------------------------------------------------------------------------
# Privacy guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,kind",
    [
        ("call 415-555-0134", "personal data"),
        ("mail jane.doe@example.com", "personal data"),
        ("ship to 1200 Market St", "personal data"),
        ("gln 0614141000005", "GLN or GTIN number"),
        ("tenant 3f2c1a9e-8b7d-4c6e-9f10-2a3b4c5d6e7f", "UUID"),
        ("postgres://app:hunter2@db.internal/regengine", "credentials in a URL"),  # pragma: allowlist secret
        (FAKE_JWT, "JSON web token"),
        ("api_key = abcdef123456", "secret assignment"),
        ("tok 9f8e7d6c5b4a39281706f5e4d3c2b1a0ffeeddcc", "key-like token"),
    ],
)
def test_privacy_guard_refuses_what_must_not_leave(value, kind):
    found = privacy.findings({"state": value})

    assert any(kind in finding for finding in found), found
    assert all(value not in finding for finding in found)


def test_privacy_guard_passes_headers_and_question_wording():
    assert privacy.findings({"headers": ["Ship Dte", "Lot No.", "Deliver-To GLN", "Qty Shpd", "Freight Co."]}) == []
    assert privacy.findings("Which FSMA 204 critical tracking event do rows with these CSV headers record?") == []
    assert privacy.data_row_findings(["Ship Date", "Lot", "Qty"]) == []


def test_privacy_guard_refuses_rows_of_values_and_secret_env_values():
    assert privacy.data_row_findings(["2024-01-03", "LOT-889", "12", "Acme"])
    row = ["Romaine Hearts 3ct", "LOT-R-0423", "240", "cases", "Fresh Farms Inc", "Salinas CA", "2024-04-23"]
    assert privacy.data_row_findings(row) == [
        "cell(s) 2, 3, 7 look like values (dates, numbers or codes), not column names: paste only the header row"
    ]
    assert privacy.findings({"gln": 1234567890128, "phone": 5551234567, "ok": 3, "flag": True}) == [
        "GLN or GTIN number at $.gln",
        "personal data (email, phone, SSN or street address) at $.phone",
    ]
    environ = {"TYPESAFE_API_KEY": "ts-not-a-real-key-123"}  # pragma: allowlist secret
    found = privacy.findings({"state": "x ts-not-a-real-key-123 y"}, environ=environ)
    assert found == ["the value of TYPESAFE_API_KEY at $.state"]


# ---------------------------------------------------------------------------
# Proposers
# ---------------------------------------------------------------------------


def test_offline_proposer_teaches_untried_abbreviations_once():
    base = questions.baseline(HM)
    brief = {
        "auto_apply_threshold": 0.9,
        "kinds": {
            HM: {
                "wording": base.wording(),
                "misses": [
                    {"case": "c1", "column": "Packed Dte", "expected": ["packing_date"], "csv_headers": ["Packed Dte"]}
                ],
                "uncertain": [],
            }
        },
        "history": [],
    }

    first = proposer.OfflineProposer().propose(brief)
    patch = first.patches[HM]
    brief["history"] = [{"notes": list(first.notes)}]
    second = proposer.OfflineProposer().propose(brief)

    assert patch["criteria"][0]["option"] == "packing_date"
    assert "Dte" in patch["criteria"][0]["what"]
    assert first.predicted_fixes == ((HM, "c1", "Packed Dte"),)
    assert second.patches[HM] is None


@pytest.mark.parametrize(
    "data,message",
    [
        ([], "not a JSON object"),
        ({"rationale": "", HM: {"criteria": "x"}}, "criteria list"),
        ({"rationale": "", HM: {"criteria": [{"what": "x"}]}}, "no option name"),
        ({"rationale": "", HM: {"criteria": [{"option": "quantity"}] * 7}}, "7 option changes (limit 6)"),
    ],
)
def test_parse_proposal_refuses_the_wrong_shape(data, message):
    with pytest.raises(proposer.ProposerError, match=message.replace("(", r"\(").replace(")", r"\)")):
        proposer.parse_proposal(data, backend="t", max_changes=6)


def test_claude_cli_proposer_runs_without_tools_secrets_or_the_repo(monkeypatch):
    seen: dict = {}
    structured = {
        "rationale": "teach Dte",
        HM: {
            "task": None,
            "guidance": None,
            "criteria": [{"option": "ship_date", "what": "Date shipped.", "not_for": None, "examples": None}],
        },
        questions.FILE_CTE: None,
        "predicted_fixes": [{"kind": HM, "case": "c1", "subject": "Ship Dte"}],
    }

    def runner(command, **kwargs):
        seen.update(command=command, **kwargs)
        stdout = json.dumps(
            {
                "is_error": False,
                "structured_output": structured,
                "total_cost_usd": 0.12,
                "modelUsage": {"claude-opus-5-5": {}},
            }
        )
        return type("Done", (), {"returncode": 0, "stdout": stdout})()

    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-should-not-pass-1234")  # pragma: allowlist secret
    claude = proposer.ClaudeCliProposer(runner=runner)

    result = claude.propose({"auto_apply_threshold": 0.9, "kinds": {}, "history": []})

    command = seen["command"]
    assert command[command.index("--tools") + 1] == ""
    assert {"--restricted", "--no-session-persistence", "--strict-mcp-config", "--json-schema"} <= set(command)
    assert command[command.index("--model") + 1] == proposer.DEFAULT_MODEL
    assert "TYPESAFE_API_KEY" not in seen["env"]
    assert not str(seen["cwd"]).startswith(str(ROOT))
    assert "DATA (JSON)" in seen["input"]
    assert result.cost_usd == 0.12 and result.model == "claude-opus-5-5"
    assert result.predicted_fixes == ((HM, "c1", "Ship Dte"),)

    def failing(command, **kwargs):
        return type(
            "Done", (), {"returncode": 1, "stdout": json.dumps({"is_error": True, "subtype": "error_max_budget"})}
        )()

    with pytest.raises(proposer.ProposerError, match="error_max_budget"):
        proposer.ClaudeCliProposer(runner=failing).propose({"auto_apply_threshold": 0.9, "kinds": {}, "history": []})

    def missing(command, **kwargs):
        raise FileNotFoundError(command[0])

    with pytest.raises(proposer.ProposerError, match="not on PATH"):
        proposer.ClaudeCliProposer(runner=missing).propose({"auto_apply_threshold": 0.9, "kinds": {}, "history": []})


class _FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class _FakeAnthropic:
    def __init__(self, message):
        self.calls: list = []
        outer = self

        class Messages:
            def stream(self, **kwargs):
                outer.calls.append(kwargs)
                return _FakeStream(message)

        self.beta = type("Beta", (), {"messages": Messages()})()


def _message(stop_reason, text):
    block = type("Block", (), {"type": "text", "text": text})()
    return type("Message", (), {"stop_reason": stop_reason, "content": [block], "model": "claude-opus-5-5"})()


def test_proposer_failures_never_crash_the_run(tmp_path, fake):
    class Broken:
        name = "broken"

        def propose(self, brief):
            raise ConnectionError("socket closed")

    summary = loop.run_loop(
        ledger=_home(tmp_path), decider=fake, proposer=Broken(), config=loop.LoopConfig(generations=3)
    )

    assert summary["stopped"] == "proposer failed: ConnectionError"
    assert lab_outcomes(tmp_path) == ["no_proposal"]
    with pytest.raises(ValueError, match="margin"):
        loop.run_loop(
            ledger=_home(tmp_path / "n"), decider=fake, proposer=Broken(), config=loop.LoopConfig(margin=float("nan"))
        )


def lab_outcomes(tmp_path):
    return [g["outcome"] for g in ledger.Ledger(tmp_path / "lab", mode=ledger.FAKE).generations()]


def test_anthropic_sdk_proposer_uses_structured_output_and_refusal_fallback():
    body = json.dumps({"rationale": "r", HM: None, questions.FILE_CTE: None, "predicted_fixes": []})
    client = _FakeAnthropic(_message("end_turn", body))

    result = proposer.AnthropicSdkProposer(client=client).propose(
        {"auto_apply_threshold": 0.9, "kinds": {}, "history": []}
    )

    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["betas"] == [proposer.FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": proposer.PROPOSAL_SCHEMA}
    assert "thinking" not in call and "tool_choice" not in call
    assert result.backend == "anthropic-sdk" and result.patches[HM] is None

    refused = _FakeAnthropic(_message("refusal", ""))
    with pytest.raises(proposer.ProposerError, match="declined"):
        proposer.AnthropicSdkProposer(client=refused).propose({"auto_apply_threshold": 0.9, "kinds": {}, "history": []})

    class Overloaded(_FakeAnthropic):
        def __init__(self):
            super().__init__(None)

            class Messages:
                def stream(self, **kwargs):
                    raise RuntimeError("529 overloaded")

            self.beta = type("Beta", (), {"messages": Messages()})()

    with pytest.raises(proposer.ProposerError, match="the Claude API call failed: RuntimeError"):
        proposer.AnthropicSdkProposer(client=Overloaded()).propose(
            {"auto_apply_threshold": 0.9, "kinds": {}, "history": []}
        )


def test_claude_cli_proposer_is_refused_before_any_jev_request_when_claude_is_missing(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")

    with pytest.raises(proposer.ProposerError, match="not on PATH"):
        proposer.build_proposer(proposer.CLAUDE_CLI)


def test_noise_floor_and_foresight():
    a = [
        _obs(HM, "c", "x", "train", correct=True, confidence=0.6),
        _obs(HM, "d", "y", "train", correct=False, confidence=0.4),
    ]
    b = [
        _obs(HM, "c", "x", "train", correct=True, confidence=0.6),
        _obs(HM, "d", "y", "train", correct=True, confidence=0.7),
    ]

    noise = loop.noise_floor(a, b, {HM: 8})
    seen = loop.foresight([(HM, "d", "y"), (HM, "c", "x")], a, b)

    assert noise[HM]["flip_rate"] == 0.5 and noise[HM]["allowed_flips"] == 4
    assert noise[HM]["brier_sd"] > 0 and noise[HM]["noise_margin"] > 0
    assert seen == {"predicted": 2, "came_true": 1, "hit_rate": 0.5, "unpredicted_fixes": 0, "breaks": 0}
