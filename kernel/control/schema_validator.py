"""
Schema Validation Module
========================
Validates vertical.yaml and obligations.yaml against JSON schemas.

Ensures schema completeness before code generation.

Hardening (#1343)
-----------------
* Every object-level schema sets ``additionalProperties: false`` so typos
  like ``regulatorss`` fail loudly instead of silently misconfiguring.
* ``decision_types`` / ``risk_dimensions`` items now enforce identifier
  patterns matching the codegen allowlist (#1285), so adversarial values
  get rejected here rather than at codegen emission.
* Multi-error reporting: schema validators iterate over every error rather
  than surfacing only the first, so authors fix the whole file in one pass.
* ``validate_snapshot_contract_functions_exist`` validates
  ``vertical_name`` against the same identifier pattern and uses an AST
  walk rather than substring matching.
"""

from pathlib import Path
from typing import Dict, List, Any
import ast
import re

import jsonschema
from jsonschema import Draft7Validator, validate, ValidationError


# ============================================
# VERTICAL SCHEMA DEFINITION
# ============================================

# Identifier patterns shared between schema validation and codegen. Keep in
# sync with ``kernel.control.codegen._IDENT_RE`` / ``_ENUM_LIKE_RE``.
_IDENT_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
_ENUM_PATTERN = r"^[A-Z][A-Z0-9_]{0,31}$"
_CITATION_PATTERN = r"^[A-Za-z0-9 .\-/()§]{1,128}$"


VERTICAL_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "name",
        "version",
        "regulators",
        "regulatory_domains",
        "decision_types",
        "risk_dimensions",
        "evidence_contract",
        "snapshot_contract",
        "scoring_weights",
    ],
    "properties": {
        "name": {
            "type": "string",
            "pattern": _IDENT_PATTERN,
            "description": "Vertical name (lowercase identifier)",
        },
        "version": {
            "type": "string",
            "pattern": r"^\d+\.\d+\.\d+$",
            "description": "Semantic version (e.g., 1.0.0)",
        },
        "regulators": {
            "type": "array",
            "items": {"type": "string", "pattern": _ENUM_PATTERN},
            "minItems": 1,
            "description": "List of regulatory agencies (e.g., OCC, CFPB, FDA)",
        },
        "regulatory_domains": {
            "type": "array",
            "items": {"type": "string", "pattern": _ENUM_PATTERN},
            "minItems": 1,
            "description": "List of regulatory domains (e.g., FSMA)",
        },
        "decision_types": {
            "type": "array",
            "items": {"type": "string", "pattern": _IDENT_PATTERN},
            "minItems": 1,
            "description": "List of decision types (lowercase identifiers)",
        },
        "risk_dimensions": {
            "type": "array",
            "items": {"type": "string", "pattern": _IDENT_PATTERN},
            "minItems": 1,
            "description": "Risk dimensions (lowercase identifiers)",
        },
        "evidence_contract": {
            "type": "object",
            "description": "Required evidence fields per decision type",
            "patternProperties": {
                _IDENT_PATTERN: {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["required"],
                    "properties": {
                        "required": {
                            "type": "array",
                            "items": {"type": "string", "pattern": _IDENT_PATTERN},
                        }
                    },
                }
            },
            "additionalProperties": False,
        },
        "snapshot_contract": {
            "type": "object",
            "additionalProperties": False,
            "required": ["function", "inputs", "outputs"],
            "properties": {
                "function": {"type": "string", "pattern": _IDENT_PATTERN},
                "inputs": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _IDENT_PATTERN},
                },
                "outputs": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _IDENT_PATTERN},
                },
            },
            "description": "Snapshot computation contract",
        },
        "scoring_weights": {
            "type": "object",
            "description": "Scoring component weights (must sum to 1.0)",
            "patternProperties": {
                _IDENT_PATTERN: {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                }
            },
            "additionalProperties": False,
        },
    },
}


# ============================================
# OBLIGATION SCHEMA DEFINITION
# ============================================

OBLIGATION_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "required": ["obligations"],
    "properties": {
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "citation",
                    "regulator",
                    "domain",
                    "description",
                    "triggering_conditions",
                    "required_evidence",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": r"^[A-Z][A-Z0-9_]{0,63}$",
                        "description": "Obligation ID (uppercase identifier)",
                    },
                    "citation": {
                        "type": "string",
                        "pattern": _CITATION_PATTERN,
                        "description": "Legal citation (e.g., 21 CFR 1.1320)",
                    },
                    "regulator": {
                        "type": "string",
                        "pattern": _ENUM_PATTERN,
                        "description": "Regulatory agency (e.g., FDA)",
                    },
                    "domain": {
                        "type": "string",
                        "pattern": _ENUM_PATTERN,
                        "description": "Regulatory domain (e.g., FSMA)",
                    },
                    "description": {
                        "type": "string",
                        "minLength": 10,
                        "description": "Obligation description",
                    },
                    "triggering_conditions": {
                        "type": "object",
                        "description": "Conditions that trigger this obligation",
                    },
                    "required_evidence": {
                        "type": "array",
                        "items": {"type": "string", "pattern": _IDENT_PATTERN},
                        "minItems": 1,
                        "description": "Required evidence fields",
                    },
                },
            },
        }
    },
}


# ============================================
# VALIDATION FUNCTIONS
# ============================================

def _collect_errors(instance: Any, schema: Dict[str, Any]) -> List[str]:
    """Iterate every jsonschema validation error, not just the first one."""
    validator = Draft7Validator(schema)
    errors: List[str] = []
    for err in validator.iter_errors(instance):
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{path}: {err.message}")
    return errors


def validate_vertical_schema(vertical_data: Dict[str, Any]) -> List[str]:
    """
    Validate vertical.yaml against schema.

    Returns:
        List of validation errors (empty if valid). All errors are returned,
        not just the first.
    """
    return _collect_errors(vertical_data, VERTICAL_SCHEMA)


def validate_obligations_schema(obligations_data: List[Dict[str, Any]]) -> List[str]:
    """
    Validate obligations.yaml against schema.

    Returns:
        List of validation errors (empty if valid). All errors are returned,
        not just the first.
    """
    return _collect_errors(
        {"obligations": obligations_data}, OBLIGATION_SCHEMA
    )


def validate_snapshot_contract_functions_exist(
    vertical_name: str,
    snapshot_contract: Dict[str, Any],
    *,
    verticals_root: Path | None = None,
) -> List[str]:
    """
    Validate that snapshot contract function exists in snapshot_logic.py.

    Hardening (#1343):

    * ``vertical_name`` is validated against the identifier allowlist before
      it is ever joined into a filesystem path — no more path traversal via
      ``../etc/passwd``.
    * The resolved path is asserted to stay inside ``verticals_root``.
    * Presence is checked by parsing the file with :mod:`ast` and looking
      for a real ``def <function_name>(...)`` at module scope, not a
      substring match.

    Args:
        vertical_name: Vertical identifier (must match ``_IDENT_PATTERN``).
        snapshot_contract: The ``snapshot_contract`` dict from vertical.yaml.
        verticals_root: Optional base path for the ``verticals/`` tree.
            Defaults to the repo-relative ``./verticals`` directory.

    Returns:
        List of validation errors (empty if valid).
    """
    errors: List[str] = []

    if not isinstance(vertical_name, str) or not re.match(
        _IDENT_PATTERN, vertical_name
    ):
        errors.append(
            f"vertical_name {vertical_name!r} is not a safe identifier "
            f"(expected {_IDENT_PATTERN})"
        )
        return errors

    root = (verticals_root or Path("./verticals")).resolve()
    snapshot_logic_path = (root / vertical_name / "snapshot_logic.py").resolve()

    # Defence in depth: after the identifier check the resolved path must
    # still live inside ``root``.
    try:
        snapshot_logic_path.relative_to(root)
    except ValueError:
        errors.append(
            f"resolved snapshot_logic path {snapshot_logic_path} escapes "
            f"verticals root {root}"
        )
        return errors

    try:
        content = snapshot_logic_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"snapshot_logic.py not found at {snapshot_logic_path}")
        return errors
    except Exception as e:
        errors.append(f"Error reading snapshot_logic.py: {e}")
        return errors

    function_name = snapshot_contract.get("function")
    if not function_name:
        errors.append("snapshot_contract is missing 'function'")
        return errors

    try:
        tree = ast.parse(content, filename=str(snapshot_logic_path))
    except SyntaxError as exc:
        errors.append(f"snapshot_logic.py is not valid Python: {exc}")
        return errors

    defined_functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if function_name not in defined_functions:
        errors.append(
            f"Snapshot function '{function_name}' is not defined at module "
            f"scope in {snapshot_logic_path}"
        )

    return errors
