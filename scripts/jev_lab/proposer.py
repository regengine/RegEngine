"""The Claude side of the loop: read Jev's training-split misses and propose a rewrite of the wording.

Claude receives data only (:func:`build_brief`): the current wording, Jev's
misses and uncertain answers on the *training* split, and the outcome of
earlier attempts. It never sees held-out cases, never gets tools, and its
answer is a JSON patch (:data:`PROPOSAL_SCHEMA`) that :func:`parse_proposal`
checks before :func:`jev_lab.questions.validate` checks the wording itself.

Backends:

* ``claude-cli`` (default): the local Claude Code CLI, ``claude -p`` with
  structured output, no tools, no session saved, run in an empty temporary
  directory with ``TYPESAFE_API_KEY`` removed from its environment. It uses
  the CLI's own login, so no extra key is needed.
* ``anthropic-sdk``: the official ``anthropic`` Python SDK with
  ``ANTHROPIC_API_KEY``. The package is not in ``requirements.lock``; install
  it in your own virtualenv to use this backend.
* ``offline``: a deterministic heuristic that teaches abbreviations, for
  ``--fake`` runs and tests. It is not Claude.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import privacy
from .fake_jev import tokens
from .questions import FILE_CTE, HEADER_MAPPING, KINDS, MAX_EXAMPLES, QuestionSet
from .scoring import TRAIN, Observation, by_split, metrics

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_MAX_CHANGES = 6
MAX_BRIEF_ITEMS = 40
CLAUDE_CLI = "claude-cli"
ANTHROPIC_SDK = "anthropic-sdk"
OFFLINE = "offline"
BACKENDS = (CLAUDE_CLI, ANTHROPIC_SDK, OFFLINE)
# The CLI's own system prompt is about coding in a repository; the proposer needs none of it.
SYSTEM_PROMPT = (
    "You rewrite the wording of multiple-choice questions for a classifier. You have no tools. "
    "Answer only with the JSON object the schema describes."
)
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Never handed to the Claude subprocess.
_WITHHELD_ENV = re.compile(r"^(TYPESAFE_|REGENGINE_JEV_|JEV_LAB_TOKEN)")

_CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "option": {"type": "string"},
        "what": {"type": ["string", "null"]},
        "not_for": {"type": ["string", "null"]},
        "examples": {"type": ["array", "null"], "items": {"type": "string"}},
    },
    "required": ["option", "what", "not_for", "examples"],
    "additionalProperties": False,
}
_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": ["string", "null"]},
        "guidance": {"type": ["string", "null"]},
        "criteria": {"type": "array", "items": _CHANGE_SCHEMA},
    },
    "required": ["task", "guidance", "criteria"],
    "additionalProperties": False,
}
_PREDICTION_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": [HEADER_MAPPING, FILE_CTE]},
        "case": {"type": "string"},
        "subject": {"type": "string"},
    },
    "required": ["kind", "case", "subject"],
    "additionalProperties": False,
}
PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        HEADER_MAPPING: {"anyOf": [_PATCH_SCHEMA, {"type": "null"}]},
        FILE_CTE: {"anyOf": [_PATCH_SCHEMA, {"type": "null"}]},
        "predicted_fixes": {"type": "array", "items": _PREDICTION_SCHEMA},
    },
    "required": ["rationale", HEADER_MAPPING, FILE_CTE, "predicted_fixes"],
    "additionalProperties": False,
}

PROMPT = """\
You improve the wording of the questions RegEngine asks TypeSafe Jev. Jev is a classifier: it answers a
multiple-choice question about a piece of state with probabilities over the options and a confidence
(how concentrated the probabilities are). It reads literally. RegEngine asks two questions about
supplier CSV files that are about to be ingested as FSMA 204 traceability records:

- header_mapping: one question per CSV column the parser does not recognise: which canonical field
  does it hold, or no_match.
- file_cte: one question per file: which critical tracking event does every row record, or
  mixed_or_unclear.

Goal: on new, unseen supplier headers, Jev picks an acceptable option more often, and its confidence
tracks whether it is right (high when right, low when wrong). RegEngine applies an answer without a
person only at confidence {auto_apply:.2f} or higher, so a wrong answer at that confidence is the
worst outcome.

You see the training split only. A held-out split you cannot see decides whether your rewrite is
kept, so fix the pattern behind a miss, not the one header.

Rules. A rewrite that breaks one is discarded:
1. Option names are fixed. Never add, remove, rename or reorder options. Change only `what`,
   `not_for`, `examples` and the `task` / `guidance` text.
2. Never copy a header from the data into `examples` and never quote one in any text. Describe the
   pattern instead, for example "abbreviations such as Dt or Dte for date".
3. Keep the instructions explaining the state keys (`column`, `csv_headers` and `file_cte_type` for
   header_mapping; `csv_headers` for file_cte) and saying when to choose no_match or
   mixed_or_unclear.
4. Limits: `what` up to 400 characters, `not_for` up to 300, up to 12 examples of up to 40
   characters, `task` and `guidance` up to 800 characters each, total wording at most 1.5 times
   the production size.
5. Change at most {max_changes} options per kind. Every change must address a miss or an uncertain
   answer in the data. List only the options you change; send null for a field you keep.
6. Send null for a kind to leave it unchanged. `history` lists earlier attempts: what changed, how
   the training split moved, and whether the held-out check kept it. Do not repeat a rejected
   change.

`rationale`: for each change, one sentence on which misses it addresses and why it generalises.
`predicted_fixes`: the misses (kind, case, and subject: the column, or "(file)") you expect your
rewrite to turn into correct answers. Your predictions are scored against what Jev answers, and
the hit rate is shown to you next time as `foresight`.

DATA (JSON):
{brief}
"""


class ProposerError(RuntimeError):
    """The proposer gave no usable proposal. The loop records it and moves on."""


@dataclass(frozen=True)
class Proposal:
    patches: Mapping[str, Mapping[str, Any] | None]
    rationale: str
    backend: str
    model: str | None = None
    cost_usd: float | None = None
    notes: tuple[str, ...] = field(default=())
    predicted_fixes: tuple[tuple[str, str, str], ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            "patches": {kind: self.patches.get(kind) for kind in KINDS},
            "rationale": self.rationale,
            "backend": self.backend,
            "model": self.model,
            "cost_usd": self.cost_usd,
            "notes": list(self.notes),
            "predicted_fixes": [{"kind": k, "case": c, "subject": s} for k, c, s in self.predicted_fixes],
        }


def _item(observation: Observation, headers: Sequence[str]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "case": observation.case_id,
        "expected": list(observation.expected),
        "jev_answer": observation.answer,
        "confidence": round(observation.confidence or 0.0, 3),
        "top_probabilities": observation.top,
    }
    if observation.kind == HEADER_MAPPING:
        item["column"] = observation.subject
    item["csv_headers"] = list(headers)
    return item


def build_brief(
    incumbents: Mapping[str, QuestionSet],
    observations: Sequence[Observation],
    case_headers: Mapping[str, Sequence[str]],
    history: Sequence[Mapping[str, Any]],
    *,
    auto_apply: float,
) -> dict[str, Any]:
    """Everything Claude gets, from training-split observations only."""
    kinds: dict[str, Any] = {}
    for kind, qs in incumbents.items():
        train = by_split(observations, kind, TRAIN)
        misses = [o for o in train if o.answered and not o.correct]
        uncertain = [o for o in train if o.answered and o.correct and o.confidence < auto_apply]
        misses.sort(key=lambda o: (-(o.confidence or 0.0), o.case_id, o.subject))
        uncertain.sort(key=lambda o: (o.confidence or 0.0, o.case_id, o.subject))
        summary = metrics(train, auto_apply=auto_apply)
        kinds[kind] = {
            "wording": qs.wording(),
            "training_metrics": {key: summary[key] for key in ("subjects", "accuracy", "brier", "wrong_at_auto_apply")},
            "misses": [_item(o, case_headers[o.case_id]) for o in misses[:MAX_BRIEF_ITEMS]],
            "uncertain": [_item(o, case_headers[o.case_id]) for o in uncertain[:MAX_BRIEF_ITEMS]],
        }
    return {"auto_apply_threshold": auto_apply, "kinds": kinds, "history": list(history)[-8:]}


def brief_case_ids(brief: Mapping[str, Any]) -> set[str]:
    return {item["case"] for kind in brief["kinds"].values() for key in ("misses", "uncertain") for item in kind[key]}


def render_prompt(brief: Mapping[str, Any], *, max_changes: int = DEFAULT_MAX_CHANGES) -> str:
    return PROMPT.format(
        auto_apply=float(brief["auto_apply_threshold"]),
        max_changes=max_changes,
        brief=json.dumps(brief, indent=1, ensure_ascii=False),
    )


def parse_proposal(
    data: Any, *, backend: str, model: str | None = None, cost_usd: float | None = None, max_changes: int
) -> Proposal:
    """A :class:`Proposal` from the backend's JSON, or :class:`ProposerError` for the wrong shape."""
    if not isinstance(data, Mapping):
        raise ProposerError("the proposal is not a JSON object")
    patches: dict[str, Mapping[str, Any] | None] = {}
    for kind in KINDS:
        patch = data.get(kind)
        if patch is None:
            patches[kind] = None
            continue
        if not isinstance(patch, Mapping) or not isinstance(patch.get("criteria", []), list):
            raise ProposerError(f"{kind}: the patch is not an object with a criteria list")
        changes = patch.get("criteria") or []
        if len(changes) > max_changes:
            raise ProposerError(f"{kind}: {len(changes)} option changes (limit {max_changes})")
        for change in changes:
            if not isinstance(change, Mapping) or not isinstance(change.get("option"), str):
                raise ProposerError(f"{kind}: a change has no option name")
            if change.get("examples") is not None and not isinstance(change["examples"], list):
                raise ProposerError(f"{kind}: examples of {change['option']} is not a list")
            for key in ("what", "not_for"):
                if change.get(key) is not None and not isinstance(change[key], str):
                    raise ProposerError(f"{kind}: {key} of {change['option']} is not text")
        for key in ("task", "guidance"):
            if patch.get(key) is not None and not isinstance(patch[key], str):
                raise ProposerError(f"{kind}: {key} is not text")
        patches[kind] = {"task": patch.get("task"), "guidance": patch.get("guidance"), "criteria": list(changes)}
    rationale = data.get("rationale")
    predictions = []
    for item in data.get("predicted_fixes") or ():
        if isinstance(item, Mapping) and all(isinstance(item.get(key), str) for key in ("kind", "case", "subject")):
            predictions.append((item["kind"], item["case"], item["subject"]))
    return Proposal(
        patches,
        rationale if isinstance(rationale, str) else "",
        backend,
        model,
        cost_usd,
        predicted_fixes=tuple(dict.fromkeys(predictions)),
    )


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class ClaudeCliProposer:
    """``claude -p`` with structured output and no tools, in an empty temporary directory."""

    name = CLAUDE_CLI

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        executable: str = "claude",
        timeout: float = 600.0,
        max_budget_usd: float = 2.0,
        max_changes: int = DEFAULT_MAX_CHANGES,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.model = model
        self.executable = executable
        self.timeout = timeout
        self.max_budget_usd = max_budget_usd
        self.max_changes = max_changes
        self._runner = runner

    def command(self) -> list[str]:
        return [
            self.executable,
            "-p",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(PROPOSAL_SCHEMA),
            "--tools",
            "",
            "--restricted",
            "--system-prompt",
            SYSTEM_PROMPT,
            "--no-session-persistence",
            "--strict-mcp-config",
            "--max-budget-usd",
            f"{self.max_budget_usd:.2f}",
            "--model",
            self.model,
        ]

    def propose(self, brief: Mapping[str, Any]) -> Proposal:
        privacy.check(brief)
        prompt = render_prompt(brief, max_changes=self.max_changes)
        env = {key: value for key, value in os.environ.items() if not _WITHHELD_ENV.match(key)}
        with tempfile.TemporaryDirectory(prefix="jev-lab-claude-") as workdir:
            try:
                completed = self._runner(
                    self.command(),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=workdir,
                    env=env,
                )
            except FileNotFoundError:
                raise ProposerError(
                    f"{self.executable!r} is not on PATH: install Claude Code, or use --proposer anthropic-sdk"
                ) from None
            except subprocess.TimeoutExpired:
                raise ProposerError(f"claude did not answer within {self.timeout:.0f} s") from None
        try:
            result = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            raise ProposerError(f"claude exited {completed.returncode} without a JSON result") from None
        if completed.returncode != 0 or result.get("is_error"):
            raise ProposerError(f"claude exited {completed.returncode}: {result.get('subtype') or 'error'}")
        structured = result.get("structured_output")
        if structured is None:
            try:
                structured = json.loads(result.get("result") or "")
            except json.JSONDecodeError:
                raise ProposerError("claude returned no structured output") from None
        models = list((result.get("modelUsage") or {}).keys())
        return parse_proposal(
            structured,
            backend=self.name,
            model=models[0] if models else self.model,
            cost_usd=result.get("total_cost_usd"),
            max_changes=self.max_changes,
        )


class AnthropicSdkProposer:
    """The official ``anthropic`` SDK (``ANTHROPIC_API_KEY``): streaming, structured output, refusal fallback."""

    name = ANTHROPIC_SDK

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        client: Any | None = None,
        max_tokens: int = 16000,
        effort: str = "high",
        max_changes: int = DEFAULT_MAX_CHANGES,
    ) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError:
                raise ProposerError(
                    "the anthropic package is not installed: pip install anthropic in your virtualenv, "
                    "or use --proposer claude-cli"
                ) from None
            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.max_changes = max_changes

    def propose(self, brief: Mapping[str, Any]) -> Proposal:
        privacy.check(brief)
        # A declined request is re-run server-side on Anthropic's recommended
        # fallback model; message.model records which model answered.
        with self._client.beta.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            system=SYSTEM_PROMPT,
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": PROPOSAL_SCHEMA}},
            messages=[{"role": "user", "content": render_prompt(brief, max_changes=self.max_changes)}],
        ) as stream:
            message = stream.get_final_message()
        if message.stop_reason == "refusal":
            raise ProposerError("Claude declined to answer, and so did the fallback model")
        if message.stop_reason == "max_tokens":
            raise ProposerError("the proposal was cut off at max_tokens")
        text = next((block.text for block in message.content if block.type == "text"), None)
        if text is None:
            raise ProposerError("Claude returned no text block")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise ProposerError("Claude returned text that is not JSON") from None
        return parse_proposal(data, backend=self.name, model=message.model, max_changes=self.max_changes)


# Abbreviations supplier exports use, and the words they can stand for. The
# offline proposer teaches an option an abbreviation of a word its description
# already uses; it is a stand-in so the loop can run with no key, not a model
# of what Claude proposes.
ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    "dt": ("date",),
    "dte": ("date",),
    "qty": ("quantity", "quantities"),
    "qtys": ("quantities", "quantity"),
    "no": ("number",),
    "num": ("number",),
    "nbr": ("number",),
    "recv": ("received", "receiving", "receive"),
    "rcv": ("received", "receiving", "receive"),
    "recd": ("received",),
    "desc": ("description",),
    "descr": ("description",),
    "cust": ("customer", "consignee"),
    "shpd": ("shipped",),
    "shp": ("ship", "shipped"),
    "prod": ("product", "production"),
    "loc": ("location",),
    "fac": ("facility",),
    "whse": ("warehouse", "facility"),
    "supp": ("supplier",),
    "vend": ("vendor", "supplier"),
    "txn": ("transaction",),
    "xform": ("transformation", "transformed"),
    "itm": ("item",),
    "uom": ("unit",),
}


class OfflineProposer:
    """Deterministic and offline: for a miss, teach the expected option the abbreviations the header uses."""

    name = OFFLINE

    def __init__(self, *, max_changes: int = 3) -> None:
        self.max_changes = max_changes

    def propose(self, brief: Mapping[str, Any]) -> Proposal:
        privacy.check(brief)
        tried = {note for entry in brief.get("history") or () for note in entry.get("notes") or ()}
        patches: dict[str, Mapping[str, Any] | None] = {}
        notes: list[str] = []
        predicted: list[tuple[str, str, str]] = []
        for kind in KINDS:
            section = (brief.get("kinds") or {}).get(kind)
            if not section:
                patches[kind] = None
                continue
            criteria = section["wording"]["criteria"]
            edits: dict[str, list[tuple[str, str]]] = {}
            for item in section["misses"]:
                target = next((label for label in item["expected"] if label in criteria), None)
                if target is None:
                    continue
                text = " ".join(
                    str(part) for part in (criteria[target].get("what"), *criteria[target].get("examples", []))
                )
                known = set(tokens(text))
                words = tokens(item["column"]) if kind == HEADER_MAPPING else tokens(" ".join(item["csv_headers"]))
                for short in words:
                    word = next((w for w in ABBREVIATIONS.get(short, ()) if w in known), None)
                    note = f"{kind}:{target}:{short}"
                    if word and short not in known and note not in tried:
                        pairs = edits.setdefault(target, [])
                        if (word, short) not in pairs:
                            pairs.append((word, short))
                            notes.append(note)
                        predicted.append((kind, item["case"], item.get("column", "(file)")))
            changes = []
            for target, pairs in list(edits.items())[: self.max_changes]:
                what = str(criteria[target].get("what", "")).rstrip()
                spelled = "; ".join(f"{word} may be written {short.capitalize()}" for word, short in pairs)
                change = {"option": target, "what": f"{what} In headers, {spelled}.", "not_for": None, "examples": None}
                if len(criteria[target].get("examples", [])) > MAX_EXAMPLES:
                    change["examples"] = list(criteria[target]["examples"])[:MAX_EXAMPLES]
                changes.append(change)
            patches[kind] = {"task": None, "guidance": None, "criteria": changes} if changes else None
        changed = {(kind, c["option"]) for kind, p in patches.items() if p for c in p["criteria"]}
        kept = [note for note in notes if tuple(note.split(":")[:2]) in changed]
        rationale = (
            "Teach abbreviations seen in training misses: " + ", ".join(kept)
            if kept
            else "No untried abbreviation fixes left."
        )
        return Proposal(patches, rationale, self.name, None, 0.0, tuple(kept), tuple(dict.fromkeys(predicted)))


def build_proposer(backend: str, *, model: str = DEFAULT_MODEL, max_changes: int = DEFAULT_MAX_CHANGES) -> Any:
    if backend == CLAUDE_CLI:
        return ClaudeCliProposer(model=model, max_changes=max_changes)
    if backend == ANTHROPIC_SDK:
        return AnthropicSdkProposer(model=model, max_changes=max_changes)
    if backend == OFFLINE:
        return OfflineProposer(max_changes=min(max_changes, 3))
    raise ValueError(f"unknown proposer backend {backend!r}; choose one of {', '.join(BACKENDS)}")
