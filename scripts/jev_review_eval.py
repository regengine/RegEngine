#!/usr/bin/env python3
"""Bounded historical-control replay and synthetic holdout evaluation; opt-in live calls."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
from shared.jev.review_policy import QUESTION_SETS, QUESTIONS_VERSION, adjudicate_evidence, summarize_diagnostic
from shared.jev.review_validation import ReviewContractError, validate_review_answers

RATE = 0.042 / 1_000_000  # docs.typesafe.ai/models, verified 2026-10-29; output is free.
RESERVATION = 64_000 * RATE  # Default documented maximum input tokens per request.
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODELS = ("jev-1.14.0", "jev-1.13.0")


def load_cases(original_path: Path, heldout_path: Path) -> list[dict]:
    cases = []
    for packet in json.loads(original_path.read_text()):
        for question in packet["questions"]:
            if question["kind"] != "control":
                continue
            source_id = packet["id"]
            cases.append(
                {
                    "id": question["id"],
                    "mode": "mode_b",
                    "cohort": "original_controls",
                    "expected": {"label": question["pre_registered_expected"]},
                    "evidence_flags": {"authoritative_scope_verified": True},
                    "state": {
                        "fixture_notice": "Historical analyst paraphrase; not current production evidence.",
                        "claim_under_test": question["claim"],
                        "claim_context": {
                            "scope": "supplied_historical_evidence_snapshot",
                            "retrieved": packet["retrieved"],
                            "primary_evidence_source_ids": [source_id],
                        },
                        "curated_sources": [
                            {
                                "source_id": source_id,
                                "type": packet["evidence_type"],
                                "source_url": packet["url"],
                                "excerpt": packet["evidence"],
                            }
                        ],
                    },
                }
            )
    if len(cases) != 24:
        raise ValueError("Expected exactly the original 24 controls")
    heldout = json.loads(heldout_path.read_text())
    if isinstance(heldout, dict):
        heldout = heldout["cases"]
    for case in heldout:
        cases.append({**case, "cohort": "synthetic_holdout"})
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate case identifiers")
    return cases


def build_plan(cases: list[dict]) -> list[dict]:
    plan = []
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case["id"]) for case in cases):
        raise ValueError("Unsafe case identifier")
    for model in MODELS:
        for case in cases:
            # Reorder only Choice options, with identical state and batch membership.
            variants = ("base", "reordered") if case["cohort"] == "original_controls" else ("base",)
            for variant in variants:
                questions = copy.deepcopy(QUESTION_SETS[case["mode"]])
                if variant == "reordered":
                    for question in questions.values():
                        if question["type"] == "choice":
                            question["criteria"] = dict(reversed(list(question["criteria"].items())))
                payload = {"model": model, "state": case["state"], "questions": questions}
                body = json.dumps(payload, ensure_ascii=False).encode()
                if len(body) > 32_000:
                    raise ValueError("Fixture exceeds this evaluator's conservative request bound")
                plan.append(
                    {
                        "name": f"{model}-{case['id']}-{variant}",
                        "case": case,
                        "variant": variant,
                        "payload": payload,
                        "sha256": hashlib.sha256(body).hexdigest(),
                    }
                )
    return plan


def score_result(item: dict, response: dict) -> dict:
    case, answers = item["case"], response["answers"]
    if case["mode"] == "mode_b":
        decision = adjudicate_evidence(
            answers,
            authoritative_scope_verified=case.get("evidence_flags", {}).get("authoritative_scope_verified") is True,
        )
        matches = {"label": decision["label"] == case["expected"]["label"]}
    else:
        decision = summarize_diagnostic(answers, evidence_flags=case.get("evidence_flags", {}))
        answer_ids = {
            "owner_choice": "correction_owner_role",
            "tlc_source_choice": "tlc_source_assessment",
            "origin_choice": "data_gap_origin",
        }
        matches = {
            key: answers[answer_ids[key]]["choice"] == expected
            for key, expected in case["expected"].items()
            if key in answer_ids
        }
    return {"decision": decision, "matches": matches}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("API redirects are not permitted")


def run(plan: list[dict], output: Path, budget: float) -> dict:
    if not 0 < budget <= 1:
        raise ValueError("Evaluation budget must be positive and at most $1")
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY is not configured; nothing sent")
    output.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(NoRedirect)
    with (output / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ledger_path = output / "ledger.json"
        ledger = (
            json.loads(ledger_path.read_text())
            if ledger_path.exists()
            else {
                "budget_usd": budget,
                "reserved_usd": 0,
                "input_tokens": 0,
                "estimated_usage_usd": 0,
                "rate_usd_per_million_input_tokens": 0.042,
                "questions_version": QUESTIONS_VERSION,
                "attempts": [],
            }
        )
        if ledger["budget_usd"] != budget:
            raise RuntimeError("Existing ledger has a different budget")

        def save():
            temporary = output / "ledger.tmp"
            temporary.write_text(json.dumps(ledger, indent=2) + "\n")
            temporary.replace(ledger_path)

        for item in plan:
            previous = next((row for row in ledger["attempts"] if row["name"] == item["name"]), None)
            if previous:
                if previous["sha256"] != item["sha256"] or previous["status"] not in {"complete", "contract_rejected"}:
                    raise RuntimeError("Changed or ambiguous prior request; automatic replay prohibited")
                if not (output / (item["name"] + ".json")).is_file():
                    raise RuntimeError("Saved response missing; automatic replay prohibited")
                continue
            if ledger["reserved_usd"] + RESERVATION > budget:
                raise RuntimeError("Budget exhausted before next request")
            record = {"name": item["name"], "sha256": item["sha256"], "reserved_usd": RESERVATION, "status": "pending"}
            ledger["attempts"].append(record)
            ledger["reserved_usd"] += RESERVATION
            save()
            request = urllib.request.Request(
                ENDPOINT,
                data=json.dumps(item["payload"], ensure_ascii=False).encode(),
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            )
            try:
                started = time.monotonic()
                with opener.open(request, timeout=30) as result:
                    raw = json.load(result)
                    request_id = result.headers.get("x-typesafe-request-id")
                if raw.get("model") != item["payload"]["model"]:
                    raise ValueError("Returned model does not match pinned model")
                usage = raw.get("usage", {})
                if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
                    raise ValueError("Invalid token usage")
                if usage["input_tokens"] > 64_000:
                    raise ValueError("Usage exceeds reservation")
                ledger["input_tokens"] += usage["input_tokens"]
                ledger["estimated_usage_usd"] = ledger["input_tokens"] * RATE
                saved = {
                    "case_id": item["case"]["id"],
                    "cohort": item["case"]["cohort"],
                    "mode": item["case"]["mode"],
                    "variant": item["variant"],
                    "expected": item["case"]["expected"],
                    "request": item["payload"],
                    "response": {k: raw[k] for k in ("model", "answers", "usage")},
                    "request_id": request_id,
                    "elapsed_seconds": time.monotonic() - started,
                }
                try:
                    validate_review_answers(raw["answers"], item["payload"]["questions"])
                    saved.update(score_result(item, raw))
                    record["status"] = "complete"
                except ReviewContractError as exc:
                    saved["processing_error"] = str(exc)
                    record["status"] = "contract_rejected"
                (output / (item["name"] + ".json")).write_text(json.dumps(saved, indent=2) + "\n")
                save()
                print(item["name"], record["status"], flush=True)
            except Exception as exc:
                record.update(
                    status="failed_or_ambiguous", error_type=type(exc).__name__, http_status=getattr(exc, "code", None)
                )
                save()
                raise RuntimeError("Request failed; reservation retained; no retry") from None
    return ledger


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--heldout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget-usd", type=float, default=1.0)
    parser.add_argument("--live", action="store_true", help="Send the inspected synthetic/public fixtures to TypeSafe")
    args = parser.parse_args()
    if not 0 < args.budget_usd <= 1:
        parser.error("This evaluation is authorized for at most $1")
    plan = build_plan(load_cases(args.original, args.heldout))
    if len(plan) * RESERVATION > args.budget_usd:
        parser.error("Full plan does not fit conservative budget reservation")
    print(
        json.dumps(
            {"requests": len(plan), "max_reserved_usd": len(plan) * RESERVATION, "models": MODELS, "live": args.live}
        ),
        flush=True,
    )
    if args.live:
        run(plan, args.output, args.budget_usd)


if __name__ == "__main__":
    main()
