"""Ask a question set about the labelled cases, score it, and decide whether a rewrite is better.

Scoring follows ``scripts/jev_eval.py`` exactly: the same cases, the same
"is this answer acceptable" rule, the same skip rules (no file-CTE question
for a row with a per-row CTE column; only headers the parser does not read
are asked). For the production wording, :func:`evaluate` returns the same
answers as ``jev_eval.evaluate`` (pinned by the tests); it only adds what the
loop needs: the split, the top probabilities, and the order check of the
file-CTE question, which already rides in the same request.

Acceptance is conservative because the labelled set is small, and runs in
two stages so the held-out split is looked at as rarely as possible:

1. :func:`screen` on the training split: the candidate must lower the
   confidence Brier score and keep every correct answer. A candidate that
   fails here is never asked about held-out cases.
2. :func:`decide` on the held-out split: it must keep every correct answer,
   add no wrong answer and no order-inconsistent answer at or above the
   auto-apply threshold, lower the Brier score by at least ``margin``, not
   raise the calibration error or the confidence of wrong answers beyond a
   small slack, and improve more held-out subjects than it worsens.

"Confidence Brier" scores Jev's confidence as a forecast of "this answer is
right": the property the confidence bands rely on.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any

from app import csv_templates as route
from shared.jev import JevUnavailable, band_for_confidence, cte_classification as cte, header_mapping as hm
from shared.jev.routing import ConfidenceThresholds

from . import load_script
from .questions import FILE_CTE, HEADER_MAPPING, QuestionSet, cte_questions, header_questions

jev_eval = load_script("jev_eval")

TRAIN = "train"
HOLDOUT = "holdout"
SPLIT_SALT = "jev-lab-split-v1"
DEFAULT_HOLDOUT_FRACTION = 0.4
DEFAULT_MARGIN = 0.01
# Non-inferiority slack: a rewrite may trade a little calibration error or
# confidence on wrong answers for a Brier gain, but not more than this.
ECE_SLACK = 0.03
WRONG_CONFIDENCE_SLACK = 0.05
NO_ANSWER_LABELS = (cte.MIXED_OR_UNCLEAR, hm.NO_MATCH)
RELIABILITY_BINS = (0.0, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0)
PURPOSES = {HEADER_MAPPING: "jev_lab_header_mapping", FILE_CTE: "jev_lab_file_cte"}


@dataclass(frozen=True)
class Observation:
    """One labelled subject, Jev's answer to it, and whether the answer is acceptable."""

    kind: str
    case_id: str
    subject: str
    split: str
    expected: tuple[str, ...]
    answer: str | None
    confidence: float | None
    correct: bool
    status: str
    top: dict[str, float] = field(default_factory=dict)
    order_consistent: bool | None = None
    request_id: str | None = None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.case_id, self.subject)

    @property
    def answered(self) -> bool:
        return self.answer is not None and self.confidence is not None

    @property
    def acts(self) -> bool:
        return self.answer is not None and self.answer not in NO_ANSWER_LABELS

    def brier(self) -> float:
        confidence = self.confidence if self.confidence is not None else 0.0
        return (confidence - (1.0 if self.correct else 0.0)) ** 2

    def scored(self, thresholds: ConfidenceThresholds) -> jev_eval.Scored:
        band = None if self.confidence is None else band_for_confidence(self.confidence, thresholds).value
        return jev_eval.Scored(
            case_id=self.case_id,
            subject=self.subject,
            expected=self.expected,
            answer=self.answer,
            confidence=self.confidence,
            band=band,
            correct=self.correct,
            status=self.status,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["expected"] = list(self.expected)
        return data


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------


def _unit_hash(case_id: str, salt: str) -> float:
    digest = hashlib.sha256(f"{salt}:{case_id}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(16**12)


def split_cases(
    cases: Sequence[jev_eval.Case], *, holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION, salt: str = SPLIT_SALT
) -> dict[str, str]:
    """``case_id -> train | holdout``, decided per case by a salted hash.

    Whole cases go to one side, so two columns of the same header row never
    straddle the split. Cases are stratified by whether they carry column
    labels and by their CTE label, and every stratum with two or more cases
    gets at least one case on each side, so a rare label (``mixed_or_unclear``)
    is never only on one. A case keeps its side when others are added, except
    that a stratum growing from one case to two may move one of them to
    balance it.
    """
    split: dict[str, str] = {}
    strata: dict[tuple[bool, str], list[jev_eval.Case]] = {}
    for case in cases:
        label = sorted(case.cte)[0] if case.cte else "-"
        strata.setdefault((bool(case.mappings), label), []).append(case)
    for members in strata.values():
        ranked = sorted(members, key=lambda case: _unit_hash(case.id, salt))
        for case in ranked:
            split[case.id] = HOLDOUT if _unit_hash(case.id, salt) < holdout_fraction else TRAIN
        if len(ranked) >= 2:
            sides = {split[case.id] for case in ranked}
            if sides == {TRAIN}:
                split[ranked[0].id] = HOLDOUT
            elif sides == {HOLDOUT}:
                split[ranked[-1].id] = TRAIN
    return split


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------


def _top(probabilities: Mapping[str, float], limit: int = 3) -> dict[str, float]:
    ordered = sorted(probabilities.items(), key=lambda item: (-item[1], item[0]))
    return {label: round(float(p), 4) for label, p in ordered[:limit]}


def header_batches(
    all_headers: Sequence[str], columns: Sequence[str], qs: QuestionSet, *, max_chars: int = hm.MAX_REQUEST_CHARS
) -> list[list[str]]:
    """``hm.column_batches`` sized with ``qs``'s wording instead of production's."""
    batches: list[list[str]] = []
    current: list[str] = []
    for column in columns:
        candidate = [*current, column]
        size = len(json.dumps(hm.build_state(list(all_headers), candidate, None))) + len(
            json.dumps(header_questions(qs, candidate))
        )
        if current and size > max_chars:
            batches.append(current)
            current = [column]
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def _ask_columns(
    case: jev_eval.Case, columns: Sequence[str], qs: QuestionSet, decider: Any
) -> dict[str, tuple[Any, str | None]]:
    found: dict[str, tuple[Any, str | None]] = {}
    for batch in header_batches(case.headers, columns, qs):
        answers = decider.ask(
            hm.build_state(list(case.headers), batch, None),
            header_questions(qs, batch),
            purpose=PURPOSES[HEADER_MAPPING],
            questions_version=qs.label,
        )
        for local, header in enumerate(batch):
            choice = answers.choices.get(f"col_{local}")
            if choice is not None:
                found[header] = (choice, answers.evidence.request_id)
    return found


def _field(choice: Any) -> str:
    return choice.choice if choice.choice in hm.CANONICAL_FIELDS else hm.NO_MATCH


def _mapping_observations(
    case: jev_eval.Case, qs: QuestionSet, decider: Any, split: str, *, order_check_at: float | None = None
) -> list[Observation]:
    """The header-mapping question as ``suggest_header_mappings`` asks it, apply switched off.

    With ``order_check_at``, every labelled answer that names a field at or
    above that confidence is asked again with the options reversed, as
    production does before it lets an answer change rows; the observation
    records whether it held.
    """
    if not case.mappings:
        return []
    status = "ok"
    found: dict[str, tuple[Any, str | None]] = {}
    reversed_found: dict[str, tuple[Any, str | None]] = {}
    if not decider.enabled:
        status = "disabled"
    elif hm.malformed_header_reason(case.headers):
        status = hm.MALFORMED_HEADER
    else:
        columns = hm.unrecognized_headers(case.headers, route._RECOGNIZED_COLUMNS)[: hm.MAX_COLUMNS_PER_UPLOAD]
        if not columns:
            status = "no_unrecognized_headers"
        try:
            found = _ask_columns(case, columns, qs, decider)
            if order_check_at is not None:
                to_check = [
                    header
                    for header in columns
                    if header in case.mappings
                    and header in found
                    and _field(found[header][0]) != hm.NO_MATCH
                    and float(found[header][0].confidence) >= order_check_at
                ]
                if to_check:
                    flipped = QuestionSet(qs.kind, qs.task, qs.guidance, hm.reversed_criteria(qs.criteria), qs.label)
                    reversed_found = _ask_columns(case, to_check, flipped, decider)
        except JevUnavailable as exc:
            status, found = f"unavailable:{exc.reason}", {}
    observations = []
    for header, expected in case.mappings.items():
        answer = confidence = request_id = None
        top: dict[str, float] = {}
        consistent: bool | None = None
        if header in found:
            choice, request_id = found[header]
            answer = _field(choice)
            confidence = float(choice.confidence)
            top = _top(choice.probabilities)
            if header in reversed_found:
                consistent = _field(reversed_found[header][0]) == answer
        observations.append(
            Observation(
                kind=HEADER_MAPPING,
                case_id=case.id,
                subject=header,
                split=split,
                expected=tuple(sorted(expected)),
                answer=answer,
                confidence=confidence,
                correct=answer in expected if answer is not None else False,
                status=status,
                top=top,
                order_consistent=consistent,
                request_id=request_id,
            )
        )
    return observations


def _cte_observation(case: jev_eval.Case, qs: QuestionSet, decider: Any, split: str) -> Observation | None:
    """The file-CTE question as ``suggest_file_cte_type`` asks it; skipped where the route skips it."""
    if case.cte is None or route._per_row_cte_column(case.headers) is not None:
        return None
    status, choice, twin, request_id = "ok", None, None, None
    cleaned = tuple((header or "").strip() for header in case.headers)
    if not decider.enabled:
        status = "disabled"
    elif hm.malformed_header_reason(case.headers):
        status = hm.MALFORMED_HEADER
    elif not any(cleaned):
        status = "no_headers"
    else:
        try:
            answers = decider.ask(
                cte.build_state(cleaned, None),
                cte_questions(qs),
                purpose=PURPOSES[FILE_CTE],
                questions_version=qs.label,
            )
            choice = answers.choices.get(cte.QUESTION_ID)
            twin = answers.choices.get(cte.REVERSED_QUESTION_ID)
            request_id = answers.evidence.request_id
            if choice is None:
                status = "no_answer"
        except JevUnavailable as exc:
            status = f"unavailable:{exc.reason}"
    answer = None
    if choice is not None:
        answer = choice.choice if choice.choice in cte.CTE_NAMES else cte.MIXED_OR_UNCLEAR
    consistent = None
    if choice is not None and twin is not None:
        consistent = (twin.choice if twin.choice in cte.CTE_NAMES else cte.MIXED_OR_UNCLEAR) == answer
    return Observation(
        kind=FILE_CTE,
        case_id=case.id,
        subject="(file)",
        split=split,
        expected=tuple(sorted(case.cte)),
        answer=answer,
        confidence=float(choice.confidence) if choice is not None else None,
        correct=answer in case.cte if answer is not None else False,
        status=status,
        top=_top(choice.probabilities) if choice is not None else {},
        order_consistent=consistent,
        request_id=request_id,
    )


def evaluate(
    cases: Sequence[jev_eval.Case],
    question_sets: Mapping[str, QuestionSet],
    decider: Any,
    *,
    split: Mapping[str, str],
    sides: Sequence[str] = (TRAIN, HOLDOUT),
    order_check_at: float | None = None,
    workers: int = 4,
    on_observation: Callable[[Observation], None] | None = None,
) -> list[Observation]:
    """Ask the cases on ``sides`` with ``question_sets`` (one per kind present), a few requests at a time.

    The order of the result is stable: all file-CTE observations in case
    order, then all header-mapping observations in case order.
    ``order_check_at`` turns on the header-mapping order check (see
    :func:`_mapping_observations`); the file-CTE twin always rides along.
    """

    def run(kind: str, case: jev_eval.Case) -> list[Observation]:
        side = split.get(case.id, TRAIN)
        if kind == FILE_CTE:
            found = _cte_observation(case, question_sets[FILE_CTE], decider, side)
            observations = [found] if found is not None else []
        else:
            observations = _mapping_observations(
                case, question_sets[HEADER_MAPPING], decider, side, order_check_at=order_check_at
            )
        if on_observation is not None:
            for observation in observations:
                on_observation(observation)
        return observations

    kinds = [kind for kind in (FILE_CTE, HEADER_MAPPING) if kind in question_sets]
    chosen = [case for case in cases if split.get(case.id, TRAIN) in sides]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(run, kind, case) for kind in kinds for case in chosen]
        return [observation for future in futures for observation in future.result()]


def parity_problems(cases: Sequence[jev_eval.Case]) -> list[str]:
    """Where the lab's scoring of the production wording differs from ``jev_eval``'s, on the offline fake.

    Free (nothing leaves the process) and run before every loop, so a change to
    production's ask path that the lab has not followed stops the loop instead
    of quietly optimising against the wrong questions.
    """
    from .jev_access import FAKE, build_decider
    from .questions import KINDS, baseline

    decider = build_decider(FAKE)
    try:
        cte_scored, map_scored = jev_eval.evaluate(cases, decider)
        expected = {
            (s.case_id, s.subject, "file" if s.subject == "(file)" else "map"): s for s in (*cte_scored, *map_scored)
        }
        thresholds = decider.settings.thresholds
        lab = evaluate(cases, {kind: baseline(kind) for kind in KINDS}, decider, split={})
    finally:
        decider.close()
    found = {(o.case_id, o.subject, "file" if o.kind == FILE_CTE else "map"): o.scored(thresholds) for o in lab}
    problems = [f"{key[0]} {key[1]}: only jev_eval scores it" for key in expected.keys() - found.keys()]
    problems += [f"{key[0]} {key[1]}: only the lab scores it" for key in found.keys() - expected.keys()]
    for key in expected.keys() & found.keys():
        if expected[key] != found[key]:
            problems.append(f"{key[0]} {key[1]}: jev_eval {expected[key].answer} vs lab {found[key].answer}")
    return sorted(problems)


def ask_headers(headers: Sequence[str], question_sets: Mapping[str, QuestionSet], decider: Any) -> dict[str, Any]:
    """Both production questions about one header row, worded by ``question_sets`` (the sandbox's header check).

    Raises ``ValueError`` for a header row production would refuse to send,
    and lets ``JevUnavailable`` through.
    """
    reason = hm.malformed_header_reason(headers)
    if reason:
        raise ValueError(reason)
    thresholds = decider.settings.thresholds
    cleaned = [(header or "").strip() for header in headers]
    recognized = [h for h in cleaned if h and hm.normalize_csv_header(h) in route._RECOGNIZED_COLUMNS]
    columns = hm.unrecognized_headers(headers, route._RECOGNIZED_COLUMNS)[: hm.MAX_COLUMNS_PER_UPLOAD]

    def described(choice: Any, labels: Any, fallback: str, request_id: str | None) -> dict[str, Any]:
        confidence = float(choice.confidence)
        return {
            "answer": choice.choice if choice.choice in labels else fallback,
            "confidence": round(confidence, 4),
            "band": band_for_confidence(confidence, thresholds).value,
            "top": _top(choice.probabilities),
            "request_id": request_id,
        }

    mapped = []
    for batch in header_batches(headers, columns, question_sets[HEADER_MAPPING]):
        answers = decider.ask(
            hm.build_state(list(headers), batch, None),
            header_questions(question_sets[HEADER_MAPPING], batch),
            purpose="jev_lab_sandbox",
            questions_version=question_sets[HEADER_MAPPING].label,
        )
        for local, header in enumerate(batch):
            choice = answers.choices.get(f"col_{local}")
            entry: dict[str, Any] = {"header": header}
            if choice is not None:
                entry.update(described(choice, hm.CANONICAL_FIELDS, hm.NO_MATCH, answers.evidence.request_id))
            mapped.append(entry)
    per_row = route._per_row_cte_column(headers)
    file_cte = None
    if per_row is None and any(cleaned):
        answers = decider.ask(
            cte.build_state(tuple(cleaned), None),
            cte_questions(question_sets[FILE_CTE]),
            purpose="jev_lab_sandbox",
            questions_version=question_sets[FILE_CTE].label,
        )
        choice = answers.choices.get(cte.QUESTION_ID)
        twin = answers.choices.get(cte.REVERSED_QUESTION_ID)
        if choice is not None:
            file_cte = described(choice, cte.CTE_NAMES, cte.MIXED_OR_UNCLEAR, answers.evidence.request_id)
            if twin is not None:
                twin_answer = twin.choice if twin.choice in cte.CTE_NAMES else cte.MIXED_OR_UNCLEAR
                file_cte["order_consistent"] = twin_answer == file_cte["answer"]
    return {
        "recognized": recognized,
        "columns": mapped,
        "file_cte": file_cte,
        "per_row_cte_column": per_row,
        "wording": {kind: qs.label for kind, qs in question_sets.items()},
    }


# ---------------------------------------------------------------------------
# Metrics and acceptance
# ---------------------------------------------------------------------------


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def metrics(observations: Sequence[Observation], *, auto_apply: float) -> dict[str, Any]:
    """Accuracy, calibration and safety figures for one kind on one split."""
    answered = [o for o in observations if o.answered]
    correct = [o for o in answered if o.correct]
    wrong = [o for o in answered if not o.correct]
    applicable = [o for o in observations if any(label not in NO_ANSWER_LABELS for label in o.expected)]
    confident = [o for o in answered if o.acts and o.confidence >= auto_apply]
    bins = []
    for low, high in zip(RELIABILITY_BINS, RELIABILITY_BINS[1:]):
        members = [o for o in answered if low <= o.confidence < high or (high == 1.0 and o.confidence == 1.0)]
        bins.append(
            {
                "low": low,
                "high": high,
                "n": len(members),
                "accuracy": _mean([1.0 if o.correct else 0.0 for o in members]),
                "mean_confidence": _mean([o.confidence for o in members]),
            }
        )
    ece = sum((row["n"] / len(answered)) * abs(row["accuracy"] - row["mean_confidence"]) for row in bins if row["n"])
    checked = [o.order_consistent for o in answered if o.order_consistent is not None]
    return {
        "subjects": len(observations),
        "answered": len(answered),
        "unanswered": len(observations) - len(answered),
        "correct": len(correct),
        "accuracy": _mean([1.0 if o.correct else 0.0 for o in answered]),
        "brier": _mean([o.brier() for o in answered]),
        "ece": round(ece, 4) if answered else None,
        "mean_confidence_correct": _mean([o.confidence for o in correct]),
        "mean_confidence_wrong": _mean([o.confidence for o in wrong]),
        "wrong_at_auto_apply": sum(1 for o in confident if not o.correct),
        "right_at_auto_apply": sum(1 for o in confident if o.correct),
        "safe_coverage": round(sum(1 for o in confident if o.correct) / len(applicable), 4) if applicable else None,
        "order_consistency": _mean([1.0 if flag else 0.0 for flag in checked]),
        "order_inconsistent_at_auto_apply": sum(1 for o in confident if o.order_consistent is False),
        "reliability": bins,
    }


def by_split(observations: Sequence[Observation], kind: str, side: str) -> list[Observation]:
    return [o for o in observations if o.kind == kind and o.split == side]


def screen(
    kind: str, incumbent: Sequence[Observation], candidate: Sequence[Observation], *, auto_apply: float
) -> tuple[list[str], dict[str, Any]]:
    """Stage 1, training split only: ``(reasons it fails, train metrics)``. No held-out case is read."""
    inc, cand = by_split(incumbent, kind, TRAIN), by_split(candidate, kind, TRAIN)
    train = {"incumbent": metrics(inc, auto_apply=auto_apply), "candidate": metrics(cand, auto_apply=auto_apply)}
    reasons: list[str] = []
    incomplete = [o for o in cand if not o.answered]
    if incomplete:
        reasons.append(f"{len(incomplete)} training subject(s) unanswered ({incomplete[0].status})")
    t_inc, t_cand = train["incumbent"], train["candidate"]
    if t_cand["correct"] < t_inc["correct"]:
        reasons.append(f"training correct answers fell {t_inc['correct']} -> {t_cand['correct']}")
    if t_inc["brier"] is not None and t_cand["brier"] is not None and t_cand["brier"] >= t_inc["brier"]:
        reasons.append(f"training Brier did not improve ({t_inc['brier']:.4f} -> {t_cand['brier']:.4f})")
    if t_cand["wrong_at_auto_apply"] > t_inc["wrong_at_auto_apply"]:
        reasons.append(
            "training wrong answers at auto-apply rose "
            f"{t_inc['wrong_at_auto_apply']} -> {t_cand['wrong_at_auto_apply']}"
        )
    return reasons, train


@dataclass(frozen=True)
class Decision:
    kind: str
    accepted: bool
    reasons: tuple[str, ...]
    holdout: dict[str, Any]
    paired: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "reasons": list(self.reasons)}


def decide(
    kind: str,
    incumbent: Sequence[Observation],
    candidate: Sequence[Observation],
    *,
    margin: float = DEFAULT_MARGIN,
    auto_apply: float,
) -> Decision:
    """Stage 2, held-out split: whether ``candidate`` replaces ``incumbent``. ``reasons`` lists every failed gate."""
    inc_hold, cand_hold = by_split(incumbent, kind, HOLDOUT), by_split(candidate, kind, HOLDOUT)
    holdout = {
        "incumbent": metrics(inc_hold, auto_apply=auto_apply),
        "candidate": metrics(cand_hold, auto_apply=auto_apply),
    }
    before = {o.key: o for o in inc_hold}
    deltas = [o.brier() - before[o.key].brier() for o in cand_hold if o.key in before]
    wins = sum(1 for delta in deltas if delta < -1e-9)
    losses = sum(1 for delta in deltas if delta > 1e-9)
    paired = {
        "subjects": len(deltas),
        "wins": wins,
        "losses": losses,
        "ties": len(deltas) - wins - losses,
        "mean_delta": round(sum(deltas) / len(deltas), 4) if deltas else None,
    }

    reasons: list[str] = []
    if not cand_hold:
        reasons.append("no held-out subjects for this kind")
    incomplete = [o for o in cand_hold if not o.answered]
    if incomplete:
        reasons.append(f"{len(incomplete)} held-out subject(s) unanswered ({incomplete[0].status})")
    h_inc, h_cand = holdout["incumbent"], holdout["candidate"]
    if h_cand["correct"] < h_inc["correct"]:
        reasons.append(f"held-out correct answers fell {h_inc['correct']} -> {h_cand['correct']}")
    if h_cand["wrong_at_auto_apply"] > h_inc["wrong_at_auto_apply"]:
        reasons.append(
            "wrong answers at auto-apply confidence rose "
            f"{h_inc['wrong_at_auto_apply']} -> {h_cand['wrong_at_auto_apply']}"
        )
    if h_cand["order_inconsistent_at_auto_apply"] > h_inc["order_inconsistent_at_auto_apply"]:
        reasons.append(
            "order-inconsistent answers at auto-apply confidence rose "
            f"{h_inc['order_inconsistent_at_auto_apply']} -> {h_cand['order_inconsistent_at_auto_apply']}"
        )
    if h_inc["brier"] is not None and h_cand["brier"] is not None:
        gain = h_inc["brier"] - h_cand["brier"]
        if gain < margin:
            reasons.append(f"held-out Brier gain {gain:+.4f} is below the margin {margin:.4f}")
    if h_inc["ece"] is not None and h_cand["ece"] is not None and h_cand["ece"] > h_inc["ece"] + ECE_SLACK:
        reasons.append(f"held-out calibration error rose {h_inc['ece']:.4f} -> {h_cand['ece']:.4f}")
    wrong_inc, wrong_cand = h_inc["mean_confidence_wrong"], h_cand["mean_confidence_wrong"]
    if wrong_inc is not None and wrong_cand is not None and wrong_cand > wrong_inc + WRONG_CONFIDENCE_SLACK:
        reasons.append(f"held-out wrong answers grew more confident {wrong_inc:.4f} -> {wrong_cand:.4f}")
    if losses > wins:
        reasons.append(f"more held-out subjects got worse ({losses}) than better ({wins})")
    return Decision(kind, not reasons, tuple(reasons), holdout, paired)
