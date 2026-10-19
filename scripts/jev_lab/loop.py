"""The Claude <-> Jev loop: ask, score, propose, re-ask, keep only what generalises.

One run:

1. **Preflight.** Load the labelled cases (the seven templates,
   ``jev_eval_cases.json`` and the sandbox's ``cases.local.json``). The split
   epoch fixes which cases are training and which are held out the first
   time it is used; any case added later is *fresh* and stays out of the loop
   until the split is rotated. On the offline fake, check that the lab still
   asks and scores the production wording exactly as ``jev_eval`` does
   (:func:`jev_lab.scoring.parity_problems`). A mismatch stops the run.
2. **Incumbent.** Ask Jev every case with the incumbent wording (production
   until a rewrite is accepted in this epoch). Ask the training split a
   second time without the cache: how far Jev's own answers move between two
   identical requests is the noise floor (:func:`noise_floor`). It sets the
   held-out margin and how many right answers may turn wrong by chance.
3. **Each generation.** Claude gets the training split's misses and
   uncertain answers and a history of earlier attempts that says only how the
   *training* split moved and whether the held-out check kept it
   (:func:`public_history`). The brief is checked for held-out cases and
   held-out headers before it leaves. Its patch is checked
   (:func:`jev_lab.questions.validate`), the candidate is asked on the
   training split (:func:`jev_lab.scoring.screen`), and only a candidate that
   improves there is judged on the held-out split
   (:func:`jev_lab.scoring.decide`). Each held-out judgement counts against
   the epoch's cap. A candidate that copies a held-out or fresh header into an
   example is turned away through that same held-out channel, so Claude
   cannot tell it apart from an ordinary rejection. Claude's predicted fixes
   are scored on the training split (``foresight``) and returned to it next
   generation.
4. Stop after ``generations``, after ``patience`` generations in a row with
   nothing accepted, when the Jev budget cannot cover another evaluation, when
   the held-out split is worn out, when the split is rotated underneath the
   run, or when asked to stop.

Every generation is a ledger row and accepted wording becomes the incumbent
for later runs in the same epoch. Nothing here edits the repository.
"""

from __future__ import annotations

import json
import math
import os
import re
import statistics
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from shared.jev import JevUnavailable

from . import load_script, privacy
from .jev_access import Uncached
from .ledger import MAX_HOLDOUT_LOOKS, EpochChanged, LabStateError, Ledger
from .proposer import ProposerError, brief_case_ids, build_brief
from .questions import KINDS, QuestionSet, apply_patch, baseline, changed_options, normalize_phrase, validate
from .scoring import (
    DEFAULT_MARGIN,
    HOLDOUT,
    TRAIN,
    Observation,
    by_split,
    decide,
    evaluate,
    metrics,
    parity_problems,
    screen,
    split_cases,
)

jev_eval = load_script("jev_eval")

Emit = Callable[[str, Mapping[str, Any]], None]
MIN_FRESH_SUBJECTS = 5


@dataclass(frozen=True)
class LoopConfig:
    generations: int = 5
    margin: float = DEFAULT_MARGIN
    patience: int = 3
    workers: int = 4
    include_templates: bool = True
    noise_check: bool = True
    parity_check: bool = True


# ---------------------------------------------------------------------------
# Cases and the epoch's split
# ---------------------------------------------------------------------------


def validate_cases(
    ledger: Ledger, raw: Sequence[Mapping[str, Any]], *, source: str | None = None
) -> list[jev_eval.Case]:
    """``raw`` case objects validated exactly as ``jev_eval.load_cases`` validates a cases file.

    Each call uses its own temporary file, so concurrent callers (the page's
    status polls, a run, a confirm) never read each other's rows. With
    ``source`` (the file the rows came from), a row that fails validation is
    a :class:`LabStateError` naming that file and the row, to fix or delete.
    """
    rows = [{key: case[key] for key in ("id", "headers", "cte", "mappings") if key in case} for case in raw]
    if not rows:
        return []
    refuse_tainted_cases(rows, source=ledger.cases_path.name)
    ledger.ensure()
    handle, name = tempfile.mkstemp(dir=ledger.state_dir, prefix=".cases-", suffix=".json")
    path = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"cases": rows}, stream)
        try:
            return jev_eval.load_cases(path, templates=False)
        except jev_eval._UsageError as exc:
            if source is None:
                raise
            detail = str(exc).replace(str(path), source).replace(path.name, source)
            raise LabStateError(f"{detail}: fix or delete the row") from None
    finally:
        path.unlink(missing_ok=True)


# The id the page gives a labelled row: a hash of its headers, which holds digits by design.
PAGE_ID = re.compile(r"local-[0-9a-f]{12}")


def refuse_tainted_cases(rows: Sequence[Mapping[str, Any]], *, source: str) -> None:
    """Refuse a labelled row that must not leave the machine, before anything is asked about it.

    The sandbox checks a row when it is labelled, but ``cases.local.json`` can
    be edited by hand or restored from an older copy. Every field of every row
    (the id and the label too, which a validation message would repeat) is
    checked again each time it is loaded, so a secret, a person's details or a
    row of values in that file never reaches Jev, Claude, a log or the page.
    The reasons name the case and the kind of content, never the content.
    """
    reasons: list[str] = []
    for index, row in enumerate(rows, start=1):
        checked = {key: row.get(key) for key in ("id", "headers", "cte", "mappings")}
        found = privacy.findings(checked)
        headers = checked["headers"]
        if isinstance(headers, list) and all(isinstance(h, str) for h in headers):
            found += privacy.data_row_findings(headers)
        # A label, a mapping or an id that reads as a row value (a lot code, an SSCC, a date) is
        # refused too: jev_eval would otherwise repeat it as an unknown label or a missing header.
        found += privacy.value_findings({"cte": checked["cte"], "mappings": checked["mappings"]})
        page_id = isinstance(checked["id"], str) and bool(PAGE_ID.fullmatch(checked["id"]))
        found += privacy.value_findings({"id": checked["id"]}, codes=not page_id)
        # A reason names the case by its id, unless the id is itself a finding: then by position.
        clean_id = isinstance(checked["id"], str) and not any(reason.endswith(" at $.id") for reason in found)
        where = f"case {checked['id']!r}" if clean_id else f"case <row {index}>"
        reasons += [f"{source} {where}: {reason}" for reason in found]
    if reasons:
        raise privacy.Refused(reasons)


def header_key(headers: Sequence[str]) -> tuple[str, ...]:
    """A header row as compared for duplicates: each header folded by :func:`normalize_phrase`."""
    return tuple(normalize_phrase(header) for header in headers)


def every_case(ledger: Ledger, *, templates: bool = True) -> list[jev_eval.Case]:
    """Repository cases plus the sandbox's labelled rows, validated by ``jev_eval.load_cases``.

    A labelled row with the same headers as an earlier case is dropped: twins
    on opposite sides of the split would hand Claude a copy of a held-out case.
    """
    cases = jev_eval.load_cases(jev_eval.DEFAULT_CASES, templates=templates)
    seen = {header_key(case.headers) for case in cases}
    known = {case.id for case in cases}
    rows = ledger.local_cases()  # each an object with a string id, or the ledger has refused the file
    # Checked before any row is dropped, so a position in a reason is the row's position in the file.
    refuse_tainted_cases(rows, source=ledger.cases_path.name)
    local = [c for c in rows if c["id"] not in known]
    for case in validate_cases(ledger, local, source=ledger.cases_path.name):
        if header_key(case.headers) not in seen:
            seen.add(header_key(case.headers))
            cases.append(case)
    return cases


def epoch_split(ledger: Ledger, *, templates: bool = True) -> tuple[str, dict[str, str], list[jev_eval.Case]]:
    """``(salt, case id -> side, every case)``. The first call in an epoch fixes the assignment."""
    epoch = ledger.epoch()
    cases = every_case(ledger, templates=templates)
    assignment = epoch.get("assignment") or ledger.assign(split_cases(cases, salt=epoch["salt"]), salt=epoch["salt"])
    return epoch["salt"], dict(assignment), cases


def load_all_cases(ledger: Ledger, *, templates: bool = True) -> list[jev_eval.Case]:
    """The cases in this epoch's split: what the loop asks about."""
    _, assignment, cases = epoch_split(ledger, templates=templates)
    return [case for case in cases if case.id in assignment]


def fresh_cases(ledger: Ledger) -> list[jev_eval.Case]:
    """Cases outside this epoch's split: never seen by the loop, used only by :func:`confirm`."""
    _, assignment, cases = epoch_split(ledger)
    return [case for case in cases if case.id not in assignment]


def run_estimate(cases: Sequence[jev_eval.Case], split: Mapping[str, str], *, generations: int = 5) -> dict[str, Any]:
    """Upper bounds on what a run sends, before the cache: Jev requests and Claude calls.

    Per case: one file-CTE request, one header-mapping request (more only for
    very wide rows) and at most one order-check request. A run asks every case
    once, the training cases again for the noise floor, and per generation the
    training cases and then, only when they improve, the held-out cases.
    """

    def cost(side: str | None) -> int:
        chosen = [case for case in cases if case.id in split and (side is None or split[case.id] == side)]
        return sum((1 if case.cte else 0) + (2 if case.mappings else 0) for case in chosen)

    per_generation = cost(TRAIN) + cost(HOLDOUT)
    return {
        "generations": generations,
        "jev_requests_max": cost(None) + cost(TRAIN) + generations * per_generation,
        "jev_requests_per_generation_max": per_generation,
        "claude_calls_max": generations,
    }


def jev_failure(observations: Sequence[Observation]) -> str | None:
    """The first ``unavailable:<reason>`` / ``disabled`` status: Jev did not answer, which is no verdict on wording."""
    return next((o.status for o in observations if o.status.startswith("unavailable:") or o.status == "disabled"), None)


def raise_if_unavailable(observations: Sequence[Observation], purpose: str) -> None:
    failure = jev_failure(observations)
    if failure is not None:
        raise JevUnavailable(failure.removeprefix("unavailable:"), purpose=purpose)


def confirm(ledger: Ledger, decider: Any, candidate: QuestionSet) -> dict[str, Any]:
    """Production against ``candidate`` on fresh cases only: a check on data no generation was selected on.

    Raises ``JevUnavailable`` when Jev did not answer: that is no verdict.
    """
    cases = fresh_cases(ledger)
    auto_apply = decider.settings.auto_apply_confidence
    split = {case.id: HOLDOUT for case in cases}
    kind = candidate.kind
    production = evaluate(cases, {kind: baseline(kind)}, decider, split=split, order_check_at=auto_apply)
    rewrite = evaluate(cases, {kind: candidate}, decider, split=split, order_check_at=auto_apply)
    raise_if_unavailable([*production, *rewrite], "jev_lab_confirm")
    subjects = len(by_split(production, kind, HOLDOUT))
    decision = decide(kind, production, rewrite, margin=0.0, auto_apply=auto_apply).to_dict() if subjects else None
    return {
        "kind": kind,
        "mode": ledger.mode,
        "candidate": {"label": candidate.label, "digest": candidate.digest},
        "fresh_cases": len(cases),
        "fresh_subjects": subjects,
        "sufficient": subjects >= MIN_FRESH_SUBJECTS,
        "production": metrics(by_split(production, kind, HOLDOUT), auto_apply=auto_apply),
        "rewrite": metrics(by_split(rewrite, kind, HOLDOUT), auto_apply=auto_apply),
        "decision": decision,
        "jev": decider.stats(),
    }


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


def summary_metrics(observations: Sequence[Observation], *, auto_apply: float) -> dict[str, Any]:
    return {
        kind: {side: metrics(by_split(observations, kind, side), auto_apply=auto_apply) for side in (TRAIN, HOLDOUT)}
        for kind in KINDS
    }


def noise_floor(
    first: Sequence[Observation], second: Sequence[Observation], holdout_subjects: Mapping[str, int] | None = None
) -> dict[str, Any]:
    """Per kind, how much two identical evaluations disagree, and what that allows on the held-out split.

    The spread of the per-subject Brier differences, scaled to the held-out
    split's size, is the standard error of a held-out Brier difference made of
    noise alone; the margin is twice it. ``allowed_flips`` is how many
    held-out right answers the observed answer-flip rate would turn wrong by
    chance (0 when Jev repeats itself exactly, as the fake does).
    """
    result = {}
    for kind in KINDS:
        a = {o.key: o for o in first if o.kind == kind}
        b = {o.key: o for o in second if o.kind == kind}
        keys = [key for key in a if key in b and a[key].answered and b[key].answered]
        n_hold = (holdout_subjects or {}).get(kind) or len(keys)
        if not keys:
            result[kind] = {"subjects": 0, "brier_sd": 0.0, "flip_rate": 0.0, "noise_margin": 0.0, "allowed_flips": 0}
            continue
        deltas = [a[k].brier() - b[k].brier() for k in keys]
        spread = statistics.pstdev(deltas) if len(deltas) > 1 else abs(deltas[0])
        flips = sum(1 for k in keys if a[k].answer != b[k].answer)
        result[kind] = {
            "subjects": len(keys),
            "brier_sd": round(spread, 4),
            "flip_rate": round(flips / len(keys), 4),
            "noise_margin": round(2 * spread / math.sqrt(max(1, n_hold)), 4),
            "allowed_flips": math.ceil(flips / len(keys) * n_hold) if flips else 0,
        }
    return result


def holdout_leaks(brief: Mapping[str, Any], secret_phrases: set[str]) -> list[str]:
    """Strings in the brief's data (not its wording) that equal a header only held-out or fresh cases carry."""
    data = {
        "kinds": {
            kind: {k: v for k, v in section.items() if k != "wording"} for kind, section in brief["kinds"].items()
        },
        "history": brief.get("history"),
    }
    return sorted({text for _, text in privacy.strings(data) if normalize_phrase(text) in secret_phrases})


def copies_secret_header(candidate: QuestionSet, incumbent: QuestionSet, secret_phrases: set[str]) -> bool:
    """Whether the candidate adds an example equal to a held-out or fresh header."""
    for name, value in candidate.criteria.items():
        before = {normalize_phrase(str(e)) for e in (incumbent.criteria.get(name, {}).get("examples") or ())}
        for example in value.get("examples") or ():
            folded = normalize_phrase(str(example))
            if folded in secret_phrases and folded not in before:
                return True
    return False


def foresight(
    predicted: Sequence[tuple[str, str, str]], before: Sequence[Observation], after: Sequence[Observation]
) -> dict[str, Any]:
    """How many of Claude's predicted fixes came true on the training split, and what else moved."""
    old = {o.key: o for o in before if o.split == TRAIN}
    new = {o.key: o for o in after if o.split == TRAIN}
    fixed = {key for key in new if key in old and not old[key].correct and new[key].correct}
    broken = {key for key in new if key in old and old[key].correct and not new[key].correct}
    keys = [key for key in predicted if key in old]
    hits = [key for key in keys if key in fixed]
    return {
        "predicted": len(keys),
        "came_true": len(hits),
        "hit_rate": round(len(hits) / len(keys), 4) if keys else None,
        "unpredicted_fixes": len(fixed - set(keys)),
        "breaks": len(broken),
    }


def public_history(
    generation: int,
    outcome: str,
    proposal: Any,
    results: Mapping[str, Mapping[str, Any]],
    seen: Mapping[str, Any],
) -> dict[str, Any]:
    """What Claude is told about a generation: training-split movement and one bit per kind from the held-out check.

    Validation problems are included as written: they only ever name training
    headers, because copies of held-out or fresh headers are turned away by the
    held-out check (one bit) instead of by validation.
    """
    kinds: dict[str, Any] = {}
    for kind, result in results.items():
        stage = result.get("stage")
        entry: dict[str, Any] = {"changed": result.get("changed", [])}
        if stage == "invalid":
            entry["invalid"] = list(result.get("reasons", []))[:6]
        train = result.get("train")
        if train:
            before, after = train["incumbent"], train["candidate"]
            entry["training"] = {
                "brier": [before["brier"], after["brier"]],
                "correct": [before["correct"], after["correct"]],
                "wrong_at_auto_apply": [before["wrong_at_auto_apply"], after["wrong_at_auto_apply"]],
            }
        entry["held_out_check"] = {
            "screen": "not run: the training split did not improve",
            "holdout": "kept" if result.get("accepted") else "not kept",
            "invalid": "not run: invalid wording",
        }.get(str(stage), "not run: unchanged")
        kinds[kind] = entry
    return {
        "generation": generation,
        "outcome": outcome,
        "rationale": proposal.rationale[:600],
        "notes": list(proposal.notes),
        "kinds": kinds,
        "foresight": dict(seen),
    }


def _no_emit(event: str, data: Mapping[str, Any]) -> None:
    return None


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def run_loop(
    *,
    ledger: Ledger,
    decider: Any,
    proposer: Any,
    config: LoopConfig = LoopConfig(),
    emit: Emit = _no_emit,
    stop: threading.Event | None = None,
) -> dict[str, Any]:
    """Run the loop once and return a summary. A Jev or Claude failure is recorded and ends the run."""
    if getattr(decider, "mode", ledger.mode) != ledger.mode:
        raise ValueError(f"a {decider.mode} Jev cannot write to the {ledger.mode} ledger")
    if not (math.isfinite(config.margin) and 0.0 <= config.margin <= 0.5):
        raise ValueError("margin must be a number from 0 to 0.5")
    stop = stop or threading.Event()
    run_id = uuid.uuid4().hex[:12]
    auto_apply = decider.settings.auto_apply_confidence
    epoch = ledger.epoch()
    salt, split, every = epoch_split(ledger, templates=config.include_templates)
    cases = [case for case in every if case.id in split]
    case_headers = {case.id: list(case.headers) for case in cases}
    train_ids = {cid for cid, side in split.items() if side == TRAIN}
    train_headers = [header for case in cases if case.id in train_ids for header in case.headers]
    train_phrases = {normalize_phrase(h) for h in train_headers}
    # Option names and production's own examples are public vocabulary, even
    # where a template uses one as a header.
    production_phrases = {
        normalize_phrase(str(phrase))
        for kind in KINDS
        for name, value in baseline(kind).criteria.items()
        for phrase in (name, *value.get("examples", []))
    }
    unseen_phrases = {normalize_phrase(h) for case in every if case.id not in train_ids for h in case.headers}
    secret_phrases = unseen_phrases - train_phrases - production_phrases
    incumbents: dict[str, QuestionSet] = ledger.incumbents()
    references = {kind: baseline(kind) for kind in KINDS}
    margins = {kind: config.margin for kind in KINDS}
    allowed_flips = {kind: 0 for kind in KINDS}
    state = {"stopped": "generations", "generation": 0, "accepted": 0}

    def observe(generation: int, role: str) -> Callable[[Observation], None]:
        return lambda o: emit("observation", {"generation": generation, "role": role, **o.to_dict()})

    def finish(current: Sequence[Observation], extra: Mapping[str, Any]) -> dict[str, Any]:
        summary = {
            "run_id": run_id,
            "mode": ledger.mode,
            "generations": state["generation"],
            "accepted": state["accepted"],
            "stopped": state["stopped"],
            "incumbents": {kind: {"label": qs.label, "digest": qs.digest} for kind, qs in incumbents.items()},
            "metrics": summary_metrics(current, auto_apply=auto_apply),
            "margins": margins,
            "allowed_flips": allowed_flips,
            "jev": decider.stats(),
            **extra,
        }
        ledger.append({"type": "run", **summary})
        emit("run_done", summary)
        return summary

    emit(
        "run_started",
        {
            "run_id": run_id,
            "mode": ledger.mode,
            "config": asdict(config),
            "cases": len(cases),
            "fresh_cases": len(every) - len(cases),
            "epoch": {"created": epoch["created"], "looks": epoch.get("looks", {}), "cap": MAX_HOLDOUT_LOOKS},
            "split": {side: sorted(cid for cid in case_headers if split[cid] == side) for side in (TRAIN, HOLDOUT)},
            "incumbents": {kind: {"label": qs.label, "digest": qs.digest} for kind, qs in incumbents.items()},
            "jev": decider.stats(),
            "proposer": getattr(proposer, "name", "unknown"),
        },
    )
    if config.parity_check:
        problems = parity_problems(cases)
        emit("parity", {"ok": not problems, "problems": problems[:20]})
        if problems:
            state["stopped"] = "parity check failed: the lab no longer asks or scores like scripts/jev_eval.py"
            return finish([], {"parity_problems": problems[:20]})

    current = evaluate(
        cases,
        incumbents,
        decider,
        split=split,
        order_check_at=auto_apply,
        workers=config.workers,
        on_observation=observe(0, "incumbent"),
    )
    failed = jev_failure(current)
    if failed is not None:
        state["stopped"] = f"jev {failed}"
        return finish(current, {})
    emit(
        "evaluated", {"generation": 0, "role": "incumbent", "metrics": summary_metrics(current, auto_apply=auto_apply)}
    )
    train_cost = 1
    if config.noise_check:
        sent = decider.stats()["sent"]
        repeat = evaluate(cases, incumbents, Uncached(decider), split=split, sides=(TRAIN,), workers=config.workers)
        train_cost = max(1, decider.stats()["sent"] - sent)
        holdout_subjects = {kind: len(by_split(current, kind, HOLDOUT)) for kind in KINDS}
        noise = noise_floor([o for o in current if o.split == TRAIN], repeat, holdout_subjects)
        margins = {kind: round(max(config.margin, noise[kind]["noise_margin"]), 4) for kind in KINDS}
        allowed_flips = {kind: noise[kind]["allowed_flips"] for kind in KINDS}
        emit("noise", {"noise": noise, "margins": margins, "allowed_flips": allowed_flips})
        ledger.append({"type": "noise", "run_id": run_id, "noise": noise, "margins": margins})

    history: list[dict[str, Any]] = []
    idle = 0
    claude_cost = 0.0
    foresight_total = {"predicted": 0, "came_true": 0}
    while state["generation"] < config.generations:
        epoch_now = ledger.epoch()
        looks = epoch_now.get("looks", {})
        open_kinds = [kind for kind in KINDS if int(looks.get(kind, 0)) < MAX_HOLDOUT_LOOKS]
        if epoch_now["salt"] != salt:
            state["stopped"] = "the split was rotated during the run"
        elif stop.is_set():
            state["stopped"] = "stop requested"
        elif idle >= config.patience:
            state["stopped"] = f"no improvement in {config.patience} generations"
        elif not open_kinds:
            state["stopped"] = f"held-out split used {MAX_HOLDOUT_LOOKS} times per kind: run `reset --rotate-split`"
        elif decider.stats()["remaining"] < 2 * train_cost:
            state["stopped"] = "Jev request budget"
        if state["stopped"] != "generations":
            break
        state["generation"] += 1
        generation = state["generation"]
        emit("generation_started", {"generation": generation})
        brief = build_brief(
            {kind: incumbents[kind] for kind in open_kinds}, current, case_headers, history, auto_apply=auto_apply
        )
        leaked = sorted(brief_case_ids(brief) - train_ids) + holdout_leaks(brief, secret_phrases)
        if leaked:  # build_brief reads only training observations; this is the belt to that brace.
            raise RuntimeError(f"held-out data reached the proposer brief: {leaked[:5]}")
        row: dict[str, Any] = {"type": "generation", "run_id": run_id, "generation": generation}
        try:
            proposal = proposer.propose(brief)
        except (ProposerError, privacy.Refused) as exc:
            reason = f"proposer: {exc}"
            ledger.append({**row, "outcome": "no_proposal", "reason": reason})
            emit("generation_done", {"generation": generation, "outcome": "no_proposal", "reason": reason})
            history.append({"generation": generation, "outcome": "no_proposal", "reason": reason})
            idle += 1
            continue
        except Exception as exc:  # noqa: BLE001 - an unexpected proposer failure ends the run, on the record
            reason = f"proposer failed: {type(exc).__name__}"
            ledger.append({**row, "outcome": "no_proposal", "reason": reason})
            emit("generation_done", {"generation": generation, "outcome": "no_proposal", "reason": reason})
            state["stopped"] = reason
            break
        claude_cost += float(proposal.cost_usd or 0.0)
        emit("proposal", {"generation": generation, **proposal.to_dict()})

        candidates: dict[str, QuestionSet] = {}
        results: dict[str, dict[str, Any]] = {}
        for kind in KINDS:
            patch = proposal.patches.get(kind) if kind in open_kinds else None
            if not patch:
                results[kind] = {"accepted": False, "stage": "unchanged", "reasons": ["unchanged"]}
                continue
            label = f"lab-{run_id}-g{generation}-{kind}"
            candidate = apply_patch(incumbents[kind], patch).with_label(label, parent=incumbents[kind].digest)
            problems = validate(candidate, reference=references[kind], forbidden_phrases=train_headers)
            if problems:
                results[kind] = {"accepted": False, "stage": "invalid", "reasons": problems}
            elif candidate.digest == incumbents[kind].digest:
                results[kind] = {"accepted": False, "stage": "unchanged", "reasons": ["unchanged"]}
            else:
                ledger.save_set(candidate)
                candidates[kind] = candidate
                results[kind] = {"changed": changed_options(incumbents[kind], candidate)}

        evaluated: list[Observation] = []
        if candidates:
            evaluated = evaluate(
                cases,
                candidates,
                decider,
                split=split,
                sides=(TRAIN,),
                order_check_at=auto_apply,
                workers=config.workers,
                on_observation=observe(generation, "candidate"),
            )
        failed = jev_failure(evaluated)
        if failed is not None:
            # Jev did not answer: no verdict on the wording, no held-out look spent.
            ledger.append({**row, "outcome": "jev_unavailable", "reason": failed, "proposal": proposal.to_dict()})
            emit("generation_done", {"generation": generation, "outcome": "jev_unavailable", "reason": f"jev {failed}"})
            state["stopped"] = f"jev {failed}"
            break
        screened = []
        for kind in candidates:
            reasons, train = screen(kind, current, evaluated, auto_apply=auto_apply, allowed_flips=allowed_flips[kind])
            results[kind].update({"train": train})
            if reasons:
                results[kind].update({"accepted": False, "stage": "screen", "reasons": reasons})
            else:
                screened.append(kind)
        # A candidate that copies a held-out or fresh header is turned away by
        # the held-out check without being asked, and costs a look like any
        # other held-out judgement: Claude sees the same "not kept".
        copied = [kind for kind in screened if copies_secret_header(candidates[kind], incumbents[kind], secret_phrases)]
        judged = [kind for kind in screened if kind not in copied]
        if judged:
            held_out = evaluate(
                cases,
                {kind: candidates[kind] for kind in judged},
                decider,
                split=split,
                sides=(HOLDOUT,),
                order_check_at=auto_apply,
                workers=config.workers,
                on_observation=observe(generation, "candidate"),
            )
            failed = jev_failure(held_out)
            if failed is not None:
                ledger.append({**row, "outcome": "jev_unavailable", "reason": failed, "proposal": proposal.to_dict()})
                emit(
                    "generation_done",
                    {"generation": generation, "outcome": "jev_unavailable", "reason": f"jev {failed}"},
                )
                state["stopped"] = f"jev {failed}"
                break
            evaluated += held_out
        try:
            for kind in screened:
                ledger.record_holdout_look(kind, salt=salt)
                if kind in copied:
                    reason = "an example copies a held-out or fresh header"
                    results[kind].update({"accepted": False, "stage": "holdout", "reasons": [reason]})
                    continue
                decision = decide(
                    kind,
                    current,
                    evaluated,
                    margin=margins[kind],
                    auto_apply=auto_apply,
                    allowed_flips=allowed_flips[kind],
                )
                results[kind].update({**decision.to_dict(), "stage": "holdout"})
        except EpochChanged:
            state["stopped"] = "the split was rotated during the run"
            break
        if evaluated:
            emit(
                "evaluated",
                {
                    "generation": generation,
                    "role": "candidate",
                    "metrics": summary_metrics(evaluated, auto_apply=auto_apply),
                },
            )

        seen = foresight([p for p in proposal.predicted_fixes if p[0] in candidates], current, evaluated)
        accepted = [kind for kind in KINDS if results[kind].get("accepted")]
        try:
            for kind in accepted:
                ledger.record_incumbent(candidates[kind], generation=generation, run_id=run_id, salt=salt)
        except EpochChanged:
            state["stopped"] = "the split was rotated during the run"
            break
        for kind in accepted:
            incumbents[kind] = candidates[kind]
        if accepted:
            idle = 0
            state["accepted"] += len(accepted)
            current = [o for o in evaluated if o.kind in accepted] + [o for o in current if o.kind not in accepted]
        else:
            idle += 1
        foresight_total["predicted"] += seen["predicted"]
        foresight_total["came_true"] += seen["came_true"]
        outcome = "accepted" if accepted else "rejected"
        ledger.append(
            {
                **row,
                "outcome": outcome,
                "accepted": accepted,
                "proposal": proposal.to_dict(),
                "candidates": {kind: qs.digest for kind, qs in candidates.items()},
                "decisions": results,
                "foresight": seen,
                "jev": decider.stats(),
            }
        )
        history.append(public_history(generation, outcome, proposal, results, seen))
        emit(
            "generation_done",
            {
                "generation": generation,
                "outcome": outcome,
                "accepted": accepted,
                "decisions": results,
                "foresight": seen,
            },
        )

    totals: dict[str, Any] = dict(foresight_total)
    totals["hit_rate"] = round(totals["came_true"] / totals["predicted"], 4) if totals["predicted"] else None
    return finish(current, {"claude_cost_usd": round(claude_cost, 4), "foresight": totals})


def evaluate_once(ledger: Ledger, decider: Any) -> dict[str, Any]:
    """Score the incumbent wording without proposing anything (the lab's ``score`` command).

    Raises ``JevUnavailable`` when Jev did not answer.
    """
    _, split, every = epoch_split(ledger)
    cases = [case for case in every if case.id in split]
    auto_apply = decider.settings.auto_apply_confidence
    observations = evaluate(cases, ledger.incumbents(), decider, split=split, order_check_at=auto_apply)
    raise_if_unavailable(observations, "jev_lab_score")
    return {"metrics": summary_metrics(observations, auto_apply=auto_apply), "jev": decider.stats()}


def ensure_home(home: Path, *, mode: str = "live") -> Ledger:
    ledger = Ledger(home, mode=mode)
    ledger.ensure()
    return ledger
