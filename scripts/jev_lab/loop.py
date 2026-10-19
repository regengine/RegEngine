"""The Claude <-> Jev loop: ask, score, propose, re-ask, keep only what generalises.

One run:

1. **Preflight.** Load the labelled cases (the seven templates,
   ``jev_eval_cases.json`` and the sandbox's ``cases.local.json``), split them
   with the current epoch's salt, and check on the offline fake that the lab
   still scores the production wording exactly as ``jev_eval`` does
   (:func:`jev_lab.scoring.parity_problems`). A mismatch stops the run.
2. **Incumbent.** Ask Jev every case with the incumbent wording (production
   until a rewrite is accepted in this epoch). Ask the training split a
   second time without the cache: how far Jev's own answers move between two
   identical requests is the noise floor, and the required held-out gain is
   at least twice it.
3. **Each generation.** Claude gets the training split's misses and
   uncertain answers and a history of earlier attempts that says only how the
   *training* split moved and whether the held-out check kept it
   (:func:`public_history`). The brief is checked for held-out cases and
   held-out headers before it leaves. Its patch is checked
   (:func:`jev_lab.questions.validate`), the candidate is asked on the
   training split (:func:`jev_lab.scoring.screen`), and only a candidate that
   improves there is asked on the held-out split
   (:func:`jev_lab.scoring.decide`). Each held-out judgement counts against
   the epoch's cap. Claude's predicted fixes are scored on the training split
   (``foresight``) and returned to it next generation.
4. Stop after ``generations``, after ``patience`` generations in a row with
   nothing accepted, when the Jev budget cannot cover another evaluation, when
   the held-out split is worn out, or when asked to stop.

Every generation is a ledger row and accepted wording becomes the incumbent
for later runs in the same epoch. Nothing here edits the repository.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import load_script, privacy
from .jev_access import Uncached
from .ledger import MAX_HOLDOUT_LOOKS, Ledger
from .proposer import ProposerError, brief_case_ids, build_brief
from .questions import KINDS, QuestionSet, apply_patch, baseline, changed_options, normalize_phrase, validate
from .scoring import (
    DEFAULT_HOLDOUT_FRACTION,
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
_COPIED_EXAMPLE = re.compile(r"^(?P<option>[^:]+): example (?P<example>.+) copies a labelled header$")


@dataclass(frozen=True)
class LoopConfig:
    generations: int = 5
    margin: float = DEFAULT_MARGIN
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION
    patience: int = 3
    workers: int = 4
    include_templates: bool = True
    noise_check: bool = True
    parity_check: bool = True


def _validated(ledger: Ledger, raw: Sequence[Mapping[str, Any]], known: set[str]) -> list[jev_eval.Case]:
    rows = [{key: case[key] for key in ("id", "headers", "cte", "mappings") if key in case} for case in raw]
    rows = [row for row in rows if row.get("id") not in known]
    if not rows:
        return []
    ledger.ensure()
    path = ledger.home / ".cases.validated.json"
    path.write_text(json.dumps({"cases": rows}), encoding="utf-8")
    try:
        return jev_eval.load_cases(path, templates=False)
    finally:
        path.unlink(missing_ok=True)


def load_all_cases(ledger: Ledger, *, templates: bool = True) -> list[jev_eval.Case]:
    """Repository cases plus the sandbox rows labelled before this epoch, validated by ``jev_eval.load_cases``."""
    cases = jev_eval.load_cases(jev_eval.DEFAULT_CASES, templates=templates)
    return cases + _validated(ledger, ledger.local_cases(fresh=False), {case.id for case in cases})


def fresh_cases(ledger: Ledger) -> list[jev_eval.Case]:
    """Sandbox rows labelled after this epoch began: never seen by the loop, used only by :func:`confirm`."""
    repository = {case.id for case in jev_eval.load_cases(jev_eval.DEFAULT_CASES, templates=True)}
    return _validated(ledger, ledger.local_cases(fresh=True), repository)


def run_estimate(cases: Sequence[jev_eval.Case], salt: str, *, generations: int = 5) -> dict[str, Any]:
    """Upper bounds on what a run sends, before the cache: Jev requests and Claude calls.

    Per case: one file-CTE request, one header-mapping request (more only for
    very wide rows) and at most one order-check request. A run asks every case
    once, the training cases again for the noise floor, and per generation the
    training cases and then, only when they improve, the held-out cases.
    """
    split = split_cases(cases, salt=salt)

    def cost(side: str | None) -> int:
        chosen = [case for case in cases if side is None or split.get(case.id) == side]
        return sum((1 if case.cte else 0) + (2 if case.mappings else 0) for case in chosen)

    per_generation = cost(TRAIN) + cost(HOLDOUT)
    return {
        "generations": generations,
        "jev_requests_max": cost(None) + cost(TRAIN) + generations * per_generation,
        "jev_requests_per_generation_max": per_generation,
        "claude_calls_max": generations,
    }


MIN_FRESH_SUBJECTS = 5


def confirm(ledger: Ledger, decider: Any, candidate: QuestionSet) -> dict[str, Any]:
    """Production against ``candidate`` on fresh rows only: a check on data no generation was selected on."""
    cases = fresh_cases(ledger)
    auto_apply = decider.settings.auto_apply_confidence
    split = {case.id: HOLDOUT for case in cases}
    kind = candidate.kind
    production = evaluate(cases, {kind: baseline(kind)}, decider, split=split, order_check_at=auto_apply)
    rewrite = evaluate(cases, {kind: candidate}, decider, split=split, order_check_at=auto_apply)
    subjects = len(by_split(production, kind, HOLDOUT))
    decision = decide(kind, production, rewrite, margin=0.0, auto_apply=auto_apply).to_dict() if subjects else None
    return {
        "kind": kind,
        "candidate": {"label": candidate.label, "digest": candidate.digest},
        "fresh_cases": len(cases),
        "fresh_subjects": subjects,
        "sufficient": subjects >= MIN_FRESH_SUBJECTS,
        "production": metrics(by_split(production, kind, HOLDOUT), auto_apply=auto_apply),
        "rewrite": metrics(by_split(rewrite, kind, HOLDOUT), auto_apply=auto_apply),
        "decision": decision,
        "jev": decider.stats(),
    }


def summary_metrics(observations: Sequence[Observation], *, auto_apply: float) -> dict[str, Any]:
    return {
        kind: {side: metrics(by_split(observations, kind, side), auto_apply=auto_apply) for side in (TRAIN, HOLDOUT)}
        for kind in KINDS
    }


def noise_floor(first: Sequence[Observation], second: Sequence[Observation]) -> dict[str, Any]:
    """Per kind: the Brier difference and the share of changed answers between two identical evaluations."""
    result = {}
    for kind in KINDS:
        a = {o.key: o for o in first if o.kind == kind}
        b = {o.key: o for o in second if o.kind == kind}
        keys = [key for key in a if key in b and a[key].answered and b[key].answered]
        if not keys:
            result[kind] = {"subjects": 0, "brier_delta": 0.0, "flip_rate": 0.0}
            continue
        brier_a = sum(a[k].brier() for k in keys) / len(keys)
        brier_b = sum(b[k].brier() for k in keys) / len(keys)
        flips = sum(1 for k in keys if a[k].answer != b[k].answer)
        result[kind] = {
            "subjects": len(keys),
            "brier_delta": round(abs(brier_a - brier_b), 4),
            "flip_rate": round(flips / len(keys), 4),
        }
    return result


def public_problem(problem: str, train_phrases: set[str]) -> str:
    """A validation problem as Claude may see it: an example matching a held-out header is not named."""
    match = _COPIED_EXAMPLE.match(problem)
    if match and normalize_phrase(match.group("example").strip("'\"")) not in train_phrases:
        return f"{match.group('option')}: an example copies a labelled header"
    return problem


def holdout_leaks(brief: Mapping[str, Any], holdout_only: set[str]) -> list[str]:
    """Strings in the brief's data (not its wording) that equal a header only held-out cases carry."""
    data = {
        "kinds": {
            kind: {k: v for k, v in section.items() if k != "wording"} for kind, section in brief["kinds"].items()
        },
        "history": brief.get("history"),
    }
    return sorted({text for _, text in privacy.strings(data) if normalize_phrase(text) in holdout_only})


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
    train_phrases: set[str],
) -> dict[str, Any]:
    """What Claude is told about a generation: training-split movement and one bit per kind from the held-out check."""
    kinds: dict[str, Any] = {}
    for kind, result in results.items():
        stage = result.get("stage")
        entry: dict[str, Any] = {"changed": result.get("changed", [])}
        if stage == "invalid":
            entry["invalid"] = [public_problem(p, train_phrases) for p in result.get("reasons", [])][:6]
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
    stop = stop or threading.Event()
    run_id = uuid.uuid4().hex[:12]
    auto_apply = decider.settings.auto_apply_confidence
    epoch = ledger.epoch()
    cases = load_all_cases(ledger, templates=config.include_templates)
    split = split_cases(cases, holdout_fraction=config.holdout_fraction, salt=epoch["salt"])
    case_headers = {case.id: list(case.headers) for case in cases}
    train_ids = {cid for cid, side in split.items() if side == TRAIN}
    forbidden = [header for case in cases for header in case.headers]
    train_phrases = {normalize_phrase(h) for case in cases if case.id in train_ids for h in case.headers}
    # Option names and production's own examples are public vocabulary, even
    # where a template uses one as a header.
    production_phrases = {
        normalize_phrase(str(phrase))
        for kind in KINDS
        for name, value in baseline(kind).criteria.items()
        for phrase in (name, *value.get("examples", []))
    }
    holdout_phrases = {normalize_phrase(h) for case in cases if case.id not in train_ids for h in case.headers}
    holdout_only = holdout_phrases - train_phrases - production_phrases
    incumbents: dict[str, QuestionSet] = ledger.incumbents()
    references = {kind: baseline(kind) for kind in KINDS}
    margins = {kind: config.margin for kind in KINDS}
    state = {"stopped": "generations", "generation": 0, "accepted": 0}

    def observe(generation: int, role: str) -> Callable[[Observation], None]:
        return lambda o: emit("observation", {"generation": generation, "role": role, **o.to_dict()})

    def finish(current: Sequence[Observation], extra: Mapping[str, Any]) -> dict[str, Any]:
        summary = {
            "run_id": run_id,
            "generations": state["generation"],
            "accepted": state["accepted"],
            "stopped": state["stopped"],
            "incumbents": {kind: {"label": qs.label, "digest": qs.digest} for kind, qs in incumbents.items()},
            "metrics": summary_metrics(current, auto_apply=auto_apply),
            "margins": margins,
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
            "config": asdict(config),
            "cases": len(cases),
            "epoch": {"created": epoch["created"], "looks": epoch.get("looks", {}), "cap": MAX_HOLDOUT_LOOKS},
            "split": {side: sorted(cid for cid, s in split.items() if s == side) for side in (TRAIN, HOLDOUT)},
            "incumbents": {kind: {"label": qs.label, "digest": qs.digest} for kind, qs in incumbents.items()},
            "jev": decider.stats(),
            "proposer": getattr(proposer, "name", "unknown"),
        },
    )
    if config.parity_check:
        problems = parity_problems(cases)
        emit("parity", {"ok": not problems, "problems": problems[:20]})
        if problems:
            state["stopped"] = "parity check failed: the lab no longer scores like scripts/jev_eval.py"
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
    failed = next((o for o in current if o.status.startswith("unavailable:") or o.status == "disabled"), None)
    if failed is not None:
        state["stopped"] = f"jev {failed.status}"
        return finish(current, {})
    emit(
        "evaluated", {"generation": 0, "role": "incumbent", "metrics": summary_metrics(current, auto_apply=auto_apply)}
    )
    train_cost = 1
    if config.noise_check:
        sent = decider.stats()["sent"]
        repeat = evaluate(cases, incumbents, Uncached(decider), split=split, sides=(TRAIN,), workers=config.workers)
        train_cost = max(1, decider.stats()["sent"] - sent)
        noise = noise_floor([o for o in current if o.split == TRAIN], repeat)
        margins = {kind: round(max(config.margin, 2 * noise[kind]["brier_delta"]), 4) for kind in KINDS}
        emit("noise", {"noise": noise, "margins": margins})
        ledger.append({"type": "noise", "run_id": run_id, "noise": noise, "margins": margins})

    history: list[dict[str, Any]] = []
    idle = 0
    claude_cost = 0.0
    foresight_total = {"predicted": 0, "came_true": 0}
    while state["generation"] < config.generations:
        looks = ledger.epoch().get("looks", {})
        open_kinds = [kind for kind in KINDS if int(looks.get(kind, 0)) < MAX_HOLDOUT_LOOKS]
        if stop.is_set():
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
        leaked = sorted(brief_case_ids(brief) - train_ids) + holdout_leaks(brief, holdout_only)
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
            problems = validate(candidate, reference=references[kind], forbidden_phrases=forbidden)
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
        screened = []
        for kind in candidates:
            reasons, train = screen(kind, current, evaluated, auto_apply=auto_apply)
            results[kind].update({"train": train})
            if reasons:
                results[kind].update({"accepted": False, "stage": "screen", "reasons": reasons})
            else:
                screened.append(kind)
        if screened:
            evaluated += evaluate(
                cases,
                {kind: candidates[kind] for kind in screened},
                decider,
                split=split,
                sides=(HOLDOUT,),
                order_check_at=auto_apply,
                workers=config.workers,
                on_observation=observe(generation, "candidate"),
            )
        for kind in screened:
            ledger.record_holdout_look(kind)
            decision = decide(kind, current, evaluated, margin=margins[kind], auto_apply=auto_apply)
            results[kind].update({**decision.to_dict(), "stage": "holdout"})
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
        for kind in accepted:
            incumbents[kind] = candidates[kind]
            ledger.record_incumbent(candidates[kind], generation=generation, run_id=run_id)
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
        history.append(public_history(generation, outcome, proposal, results, seen, train_phrases))
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
    """Score the incumbent wording without proposing anything (the lab's ``score`` command)."""
    cases = load_all_cases(ledger)
    split = split_cases(cases, salt=ledger.epoch()["salt"])
    auto_apply = decider.settings.auto_apply_confidence
    observations = evaluate(cases, ledger.incumbents(), decider, split=split, order_check_at=auto_apply)
    return {"metrics": summary_metrics(observations, auto_apply=auto_apply), "jev": decider.stats()}


def ensure_home(home: Path) -> Ledger:
    ledger = Ledger(home)
    ledger.ensure()
    return ledger
