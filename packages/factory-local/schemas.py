"""Deontic intermediate representation (IR) for statutory rules.

The IR is the single source both the Rego compiler and the Z3 verifier read,
so anything that is not representable here cannot reach a deployed policy.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Union

from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator, model_validator

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Words that are keywords or builtin terms in Rego v1. A reference such as
# input.default does not parse, so these are rejected as path segments.
REGO_RESERVED = frozenset(
    {
        "as", "contains", "data", "default", "else", "every", "false", "if",
        "import", "in", "input", "not", "null", "package", "some", "true", "with",
    }
)


def is_safe_identifier(name: str) -> bool:
    return bool(_IDENT.match(name)) and name not in REGO_RESERVED


def is_safe_path(path: str) -> bool:
    """A dotted path such as org.fte_count where every segment is safe."""
    return bool(path) and all(is_safe_identifier(seg) for seg in path.split("."))


class Operator(str, Enum):
    GREATER_THAN = "GREATER_THAN"
    LESS_THAN = "LESS_THAN"
    EQUALS = "EQUALS"


class Modality(str, Enum):
    OBLIGATION = "OBLIGATION"
    PROHIBITION = "PROHIBITION"


class DeonticPredicate(BaseModel):
    fact: str = Field(description="Input fact path, dotted for nested facts, e.g. fte_count or org.size")
    operator: Operator
    # Strict types keep True from being coerced to 1 and "5" from becoming 5.
    value: Union[StrictBool, StrictInt, StrictFloat, StrictStr]

    @field_validator("fact")
    @classmethod
    def _fact_is_safe(cls, v: str) -> str:
        if not is_safe_path(v):
            raise ValueError(f"unsafe fact path: {v!r}")
        return v

    @model_validator(mode="after")
    def _ordering_needs_number(self) -> "DeonticPredicate":
        numeric = isinstance(self.value, (int, float)) and not isinstance(self.value, bool)
        if self.operator != Operator.EQUALS and not numeric:
            raise ValueError(f"{self.operator.value} requires a numeric value, got {self.value!r}")
        return self


class DeonticIR(BaseModel):
    rule_id: str
    citation: str
    modality: Modality
    applicability_predicates: list[DeonticPredicate]
    action_required: str = Field(description="Control key under input.controls that satisfies the rule")
    safe_harbor_control: str = "nist_ai_rmf_aligned"
    max_penalty_usd: Union[StrictInt, StrictFloat]
    private_right_of_action: bool

    @field_validator("max_penalty_usd")
    @classmethod
    def _penalty_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("max_penalty_usd must be >= 0")
        return v

    @field_validator("action_required", "safe_harbor_control")
    @classmethod
    def _control_is_safe(cls, v: str) -> str:
        if not is_safe_identifier(v):
            raise ValueError(f"unsafe control name: {v!r}")
        return v

    @field_validator("rule_id")
    @classmethod
    def _rule_id_is_safe(cls, v: str) -> str:
        if not _IDENT.match(v):
            raise ValueError(f"unsafe rule_id: {v!r}")
        return v
