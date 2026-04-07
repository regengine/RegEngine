"""
Schema Validation Module
========================
Validates vertical.yaml and obligations.yaml against JSON schemas.

Ensures schema completeness before code generation.
"""

from typing import Dict, List, Any
import jsonschema
from jsonschema import validate, ValidationError


# ============================================
# VERTICAL SCHEMA DEFINITION
# ============================================

VERTICAL_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": [
        "name",
        "version",
        "regulators",
        "regulatory_domains",
        "decision_types",
        "risk_dimensions",
        "evidence_contract",
        "snapshot_contract",
        "scoring_weights"
    ],
    "properties": {
        "name": {
            "type": "string",
            "pattern": "^[a-z_]+$",
            "description": "Vertical name (lowercase with underscores)"
        },
        "version": {
            "type": "string",
            "pattern": "^\\d+\\.\\d+\\.\\d+$",
            "description": "Semantic version (e.g., 1.0.0)"
        },
        "regulators": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "List of regulatory agencies (e.g., OCC, CFPB)"
        },
        "regulatory_domains": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "List of regulatory domains (e.g., FSMA)"
        },
        "decision_types": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "List of decision types (e.g., credit_approval)"
        },
        "risk_dimensions": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "Risk dimensions (e.g., bias_risk, drift_risk)"
        },
        "evidence_contract": {
            "type": "object",
            "description": "Required evidence fields per decision type",
            "patternProperties": {
                ".*": {
                    "type": "object",
                    "required": ["required"],
                    "properties": {
                        "required": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    }
                }
            }
        },
        "snapshot_contract": {
            "type": "object",
            "required": ["function", "inputs", "outputs"],
            "properties": {
                "function": {"type": "string"},
                "inputs": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "outputs": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "description": "Snapshot computation contract"
        },
        "scoring_weights": {
            "type": "object",
            "description": "Scoring component weights (must sum to 1.0)",
            "patternProperties": {
                ".*": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0
                }
            }
        }
    }
}


# ============================================
# OBLIGATION SCHEMA DEFINITION
# ============================================

OBLIGATION_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["obligations"],
    "properties": {
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "citation",
                    "regulator",
                    "domain",
                    "description",
                    "triggering_conditions",
                    "required_evidence"
                ],
                "properties": {
                    "id": {
                        "type": "string",
                        "pattern": "^[A-Z_0-9]+$",
                        "description": "Obligation ID (uppercase with underscores)"
                    },
                    "citation": {
                        "type": "string",
                        "description": "Legal citation (e.g., 12 CFR 1002.9)"
                    },
                    "regulator": {
                        "type": "string",
                        "description": "Regulatory agency (e.g., CFPB)"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Regulatory domain (e.g., FSMA)"
                    },
                    "description": {
                        "type": "string",
                        "minLength": 10,
                        "description": "Obligation description"
                    },
                    "triggering_conditions": {
                        "type": "object",
                        "description": "Conditions that trigger this obligation"
                    },
                    "required_evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "Required evidence fields"
                    }
                }
            }
        }
    }
}


# ============================================
# VALIDATION FUNCTIONS
# ============================================

def validate_vertical_schema(vertical_data: Dict[str, Any]) -> List[str]:
    """
    Validate vertical.yaml against schema.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    try:
        validate(instance=vertical_data, schema=VERTICAL_SCHEMA)
    except ValidationError as e:
        errors.append(f"Schema validation failed: {e.message} at {e.json_path}")
    except Exception as e:
        errors.append(f"Unexpected validation error: {str(e)}")
    
    return errors


def validate_obligations_schema(obligations_data: List[Dict[str, Any]]) -> List[str]:
    """
    Validate obligations.yaml against schema.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    try:
        validate(instance={"obligations": obligations_data}, schema=OBLIGATION_SCHEMA)
    except ValidationError as e:
        errors.append(f"Schema validation failed: {e.message} at {e.json_path}")
    except Exception as e:
        errors.append(f"Unexpected validation error: {str(e)}")
    
    return errors


def validate_snapshot_contract_functions_exist(
    vertical_name: str,
    snapshot_contract: Dict[str, Any]
) -> List[str]:
    """
    Validate that snapshot contract function exists in snapshot_logic.py.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check if snapshot_logic.py exists
    snapshot_logic_path = f"verticals/{vertical_name}/snapshot_logic.py"
    
    try:
        with open(snapshot_logic_path, encoding="utf-8") as f:
            content = f.read()
        
        # Check if function is defined
        function_name = snapshot_contract.get("function")
        if function_name and function_name not in content:
            errors.append(
                f"Snapshot function '{function_name}' not found in {snapshot_logic_path}"
            )
    except FileNotFoundError:
        errors.append(f"snapshot_logic.py not found at {snapshot_logic_path}")
    except Exception as e:
        errors.append(f"Error reading snapshot_logic.py: {str(e)}")
    
    return errors
