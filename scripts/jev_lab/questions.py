"""Question sets as data: the production wording, and candidate rewrites of it.

A :class:`QuestionSet` is the part of a Jev question that wording can change:
the ``task`` and ``guidance`` instructions and each option's description
(``what`` / ``not_for`` / ``examples``). Option *names* are the contract with
the CSV parser and the validators, so a candidate can never add, drop, rename
or reorder them. The baseline is read from the production modules at runtime
(:func:`baseline`), so the lab always starts from what production asks today
and never writes to those modules.

The builders here produce request questions with exactly the production
structure; for the baseline they are equal to production's own
``build_questions`` output (pinned by the tests).
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from shared.jev import cte_classification as cte, header_mapping as hm

HEADER_MAPPING = "header_mapping"
FILE_CTE = "file_cte"
KINDS = (HEADER_MAPPING, FILE_CTE)

# Text limits for a candidate. Production descriptions run to ~150 characters
# and 6-8 examples; the caps leave room to clarify without letting a rewrite
# balloon the request (every header-mapping question carries the whole
# vocabulary, and TypeSafe caps a request at 64k tokens).
MAX_TASK_CHARS = 800
MAX_WHAT_CHARS = 400
MAX_NOT_FOR_CHARS = 300
MAX_EXAMPLES = 12
MAX_EXAMPLE_CHARS = 40
MAX_GROWTH = 1.5
DESCRIPTION_KEYS = ("what", "not_for", "examples")

# State keys each question's instructions must keep explaining, and the label
# that lets Jev say nothing fits.
REQUIRED_MENTIONS = {
    HEADER_MAPPING: ("`column`", "`csv_headers`", "`file_cte_type`"),
    FILE_CTE: ("`csv_headers`",),
}
NO_ANSWER = {HEADER_MAPPING: hm.NO_MATCH, FILE_CTE: cte.MIXED_OR_UNCLEAR}


@dataclass(frozen=True)
class QuestionSet:
    kind: str
    task: str
    guidance: str
    criteria: Mapping[str, Mapping[str, Any]]
    label: str = "baseline"
    parent: str | None = None
    notes: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "parent": self.parent,
            "task": self.task,
            "guidance": self.guidance,
            "criteria": {name: _description(value) for name, value in self.criteria.items()},
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> QuestionSet:
        return cls(
            kind=str(data["kind"]),
            task=str(data["task"]),
            guidance=str(data["guidance"]),
            criteria={str(name): _description(value) for name, value in dict(data["criteria"]).items()},
            label=str(data.get("label") or "baseline"),
            parent=data.get("parent"),
            notes=tuple(str(note) for note in data.get("notes") or ()),
        )

    def wording(self) -> dict[str, Any]:
        """What is sent to Jev, without the lab's bookkeeping."""
        data = self.to_dict()
        return {key: data[key] for key in ("task", "guidance", "criteria")}

    @property
    def digest(self) -> str:
        """SHA-256 of the wording: two sets with the same digest ask Jev the same thing."""
        return hashlib.sha256(json.dumps(self.wording(), sort_keys=False).encode("utf-8")).hexdigest()

    def with_label(self, label: str, *, parent: str | None, notes: Iterable[str] = ()) -> QuestionSet:
        return QuestionSet(self.kind, self.task, self.guidance, self.criteria, label, parent, tuple(notes))


def _description(value: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in DESCRIPTION_KEYS:
        if key in value and value[key] is not None:
            out[key] = list(value[key]) if key == "examples" else str(value[key])
    return out


def baseline(kind: str) -> QuestionSet:
    """The question set production asks today, read from the production modules."""
    if kind == HEADER_MAPPING:
        instructions = hm.build_questions(["column"])["col_0"]["instructions"]
        criteria, label = hm.CANONICAL_FIELDS, hm.QUESTIONS_VERSION
    elif kind == FILE_CTE:
        instructions = cte.build_questions()[cte.QUESTION_ID]["instructions"]
        criteria, label = cte.CTE_CRITERIA, cte.QUESTIONS_VERSION
    else:
        raise ValueError(f"unknown question kind {kind!r}")
    return QuestionSet(
        kind=kind,
        task=instructions["task"],
        guidance=instructions["guidance"],
        criteria={name: _description(value) for name, value in copy.deepcopy(criteria).items()},
        label=label,
    )


def header_questions(qs: QuestionSet, columns: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Production's header-mapping questions for ``columns``, worded by ``qs``."""
    questions = hm.build_questions(columns, criteria=qs.criteria)
    for question in questions.values():
        question["instructions"] = {**question["instructions"], "task": qs.task, "guidance": qs.guidance}
    return questions


def cte_questions(qs: QuestionSet) -> dict[str, dict[str, Any]]:
    """Production's file-CTE question and its reversed-order twin, worded by ``qs``."""
    criteria = dict(qs.criteria)
    question = {"type": "choice", "instructions": {"task": qs.task, "guidance": qs.guidance}, "criteria": criteria}
    return {
        cte.QUESTION_ID: question,
        cte.REVERSED_QUESTION_ID: {**question, "criteria": dict(reversed(list(criteria.items())))},
    }


def normalize_phrase(text: str) -> str:
    """Case, spacing and punctuation folded, so ``Lot No.`` and ``lot-no`` compare equal."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def apply_patch(qs: QuestionSet, patch: Mapping[str, Any] | None) -> QuestionSet:
    """``qs`` with a proposer's patch applied. Unknown options are kept for :func:`validate` to report.

    A patch is ``{"task": str|None, "guidance": str|None, "criteria": [{"option": name,
    "what": str|None, "not_for": str|None, "examples": [str]|None}, ...]}``; ``None``
    leaves a value unchanged.
    """
    if not patch:
        return qs
    criteria = {name: dict(value) for name, value in qs.criteria.items()}
    for change in patch.get("criteria") or ():
        name = str(change.get("option", ""))
        target = criteria.setdefault(name, {})
        for key in DESCRIPTION_KEYS:
            value = change.get(key)
            if value is not None:
                target[key] = [str(item) for item in value] if key == "examples" else str(value)
    task = patch.get("task")
    guidance = patch.get("guidance")
    return QuestionSet(
        kind=qs.kind,
        task=qs.task if task is None else str(task),
        guidance=qs.guidance if guidance is None else str(guidance),
        criteria=criteria,
        label=qs.label,
        parent=qs.parent,
    )


def validate(candidate: QuestionSet, *, reference: QuestionSet, forbidden_phrases: Iterable[str] = ()) -> list[str]:
    """Every reason ``candidate`` may not be asked; an empty list means it may.

    ``reference`` is the production baseline of the same kind: the option names
    and their order must match it exactly. ``forbidden_phrases`` are the
    labelled headers; an example that copies one would inflate every later
    evaluation, so it is refused.
    """
    problems: list[str] = []
    if candidate.kind != reference.kind:
        return [f"kind {candidate.kind!r} does not match {reference.kind!r}"]
    names, expected = list(candidate.criteria), list(reference.criteria)
    if names != expected:
        added = sorted(set(names) - set(expected))
        missing = sorted(set(expected) - set(names))
        if added:
            problems.append(f"unknown option(s): {', '.join(added)}")
        if missing:
            problems.append(f"missing option(s): {', '.join(missing)}")
        if not added and not missing:
            problems.append("options are reordered")
    for key, text in (("task", candidate.task), ("guidance", candidate.guidance)):
        if not text.strip():
            problems.append(f"{key} is empty")
        elif len(text) > MAX_TASK_CHARS:
            problems.append(f"{key} is {len(text)} characters (limit {MAX_TASK_CHARS})")
    instructions = f"{candidate.task}\n{candidate.guidance}"
    for mention in REQUIRED_MENTIONS[candidate.kind]:
        if mention not in instructions:
            problems.append(f"instructions no longer explain {mention}")
    if NO_ANSWER[candidate.kind] not in candidate.guidance:
        problems.append(f"guidance no longer says when to choose {NO_ANSWER[candidate.kind]}")
    forbidden = {normalize_phrase(phrase) for phrase in forbidden_phrases if normalize_phrase(phrase)}
    for name, description in candidate.criteria.items():
        what = description.get("what")
        if not isinstance(what, str) or not what.strip():
            problems.append(f"{name}: 'what' is empty")
        elif len(what) > MAX_WHAT_CHARS:
            problems.append(f"{name}: 'what' is {len(what)} characters (limit {MAX_WHAT_CHARS})")
        not_for = description.get("not_for")
        if not_for is not None and len(str(not_for)) > MAX_NOT_FOR_CHARS:
            problems.append(f"{name}: 'not_for' is {len(str(not_for))} characters (limit {MAX_NOT_FOR_CHARS})")
        examples = list(description.get("examples") or ())
        if len(examples) > MAX_EXAMPLES:
            problems.append(f"{name}: {len(examples)} examples (limit {MAX_EXAMPLES})")
        # Production's own examples stay allowed: the templates use them as headers.
        grandfathered = {normalize_phrase(str(e)) for e in (reference.criteria.get(name, {}).get("examples") or ())}
        seen: set[str] = set()
        for example in examples:
            folded = normalize_phrase(str(example))
            spelled = " ".join(str(example).lower().split())
            if not folded or len(str(example)) > MAX_EXAMPLE_CHARS:
                problems.append(f"{name}: example {str(example)[:MAX_EXAMPLE_CHARS]!r} is empty or too long")
            elif spelled in seen:
                problems.append(f"{name}: duplicate example {example!r}")
            elif folded in forbidden and folded not in grandfathered:
                problems.append(f"{name}: example {example!r} copies a labelled header")
            seen.add(spelled)
        if set(description) - set(DESCRIPTION_KEYS):
            problems.append(f"{name}: unknown description key(s)")
    size = len(json.dumps(candidate.wording()))
    limit = int(len(json.dumps(reference.wording())) * MAX_GROWTH)
    if size > limit:
        problems.append(f"wording is {size} characters, over {MAX_GROWTH}x the production size ({limit})")
    return problems


def changed_options(old: QuestionSet, new: QuestionSet) -> list[str]:
    """Names of options whose description differs, plus ``task`` / ``guidance`` when they changed."""
    changed = [key for key in ("task", "guidance") if getattr(old, key) != getattr(new, key)]
    changed += [
        name for name in new.criteria if _description(old.criteria.get(name, {})) != _description(new.criteria[name])
    ]
    return changed
