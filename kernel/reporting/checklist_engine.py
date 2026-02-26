#!/usr/bin/env python3
"""
RegEngine Compliance Checklist Engine

Loads YAML checklist definitions and validates customer configurations
against regulatory requirements, returning yes/no pass/fail status for each item.
"""

import os
import yaml
import structlog
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = structlog.get_logger("compliance-checklist")


class ValidationStatus(Enum):
    """Validation result status"""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ValidationType(Enum):
    """Types of validation checks"""
    BOOLEAN = "boolean"
    NUMERIC_THRESHOLD = "numeric_threshold"
    PERCENTAGE_THRESHOLD = "percentage_threshold"
    CONDITIONAL = "conditional"
    STRING_MATCH = "string_match"


@dataclass
class ValidationResult:
    """Result of a single checklist item validation"""
    requirement_id: str
    requirement: str
    regulation: str
    status: ValidationStatus
    evidence: Optional[str] = None
    remediation: Optional[str] = None
    confidence: float = 1.0  # 0.0-1.0


@dataclass
class ChecklistResult:
    """Result of full checklist validation"""
    checklist_id: str
    checklist_name: str
    industry: str
    jurisdiction: str
    overall_status: ValidationStatus
    pass_rate: float  # 0.0-1.0
    items: List[ValidationResult]
    next_steps: List[str]


class ComplianceChecklistEngine:
    """
    Engine for loading and validating compliance checklists across industries
    """

    def __init__(self, plugin_directory: str = "industry_plugins"):
        """Initialize with path to industry plugin directory"""
        self.plugin_directory = Path(plugin_directory)
        self.checklists: Dict[str, Dict] = {}  # checklist_id -> checklist definition
        self._load_all_checklists()

    def _load_all_checklists(self):
        """Load all YAML checklists from all industry plugins"""
        for industry_dir in self.plugin_directory.iterdir():
            if not industry_dir.is_dir():
                continue

            checklist_file = industry_dir / "compliance_checklist.yaml"
            if not checklist_file.exists():
                continue

            with open(checklist_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                industry = data.get("industry")
                checklists = data.get("checklists", [])

                for checklist in checklists:
                    checklist_id = checklist["id"]
                    checklist["industry"] = industry  # Add industry to each checklist
                    self.checklists[checklist_id] = checklist

        logger.info(
            "checklists_loaded",
            checklist_count=len(self.checklists),
            industry_count=len(list(self.plugin_directory.iterdir()))
        )

    def get_checklist(self, checklist_id: str) -> Optional[Dict]:
        """Retrieve a specific checklist by ID"""
        return self.checklists.get(checklist_id)

    def list_checklists(self, industry: Optional[str] = None) -> List[Dict]:
        """List all available checklists, optionally filtered by industry"""
        checklists = self.checklists.values()
        if industry:
            checklists = [c for c in checklists if c.get("industry") == industry]
        return [
            {
                "id": c["id"],
                "name": c["name"],
                "industry": c.get("industry"),
                "jurisdiction": c.get("jurisdiction"),
                "description": c.get("description"),
            }
            for c in checklists
        ]

    def validate_checklist(
        self,
        checklist_id: str,
        customer_config: Dict[str, Any]
    ) -> ChecklistResult:
        """
        Validate customer configuration against a compliance checklist

        Args:
            checklist_id: ID of the checklist to validate against
            customer_config: Customer's configuration/answers to validation questions

        Returns:
            ChecklistResult with pass/fail status for each item
        """
        checklist = self.get_checklist(checklist_id)
        if not checklist:
            raise ValueError(f"Checklist not found: {checklist_id}")

        items = checklist.get("items", [])
        results = []

        for item in items:
            result = self._validate_item(item, customer_config)
            results.append(result)

        # Calculate overall status
        pass_count = sum(1 for r in results if r.status == ValidationStatus.PASS)
        total_count = len(results)
        pass_rate = pass_count / total_count if total_count > 0 else 0.0

        overall_status = (
            ValidationStatus.PASS if pass_rate == 1.0
            else ValidationStatus.WARNING if pass_rate >= 0.8
            else ValidationStatus.FAIL
        )

        # Generate next steps
        next_steps = self._generate_next_steps(results, checklist)

        return ChecklistResult(
            checklist_id=checklist_id,
            checklist_name=checklist["name"],
            industry=checklist.get("industry", "unknown"),
            jurisdiction=checklist.get("jurisdiction", "unknown"),
            overall_status=overall_status,
            pass_rate=pass_rate,
            items=results,
            next_steps=next_steps,
        )

    def _validate_item(
        self,
        item: Dict,
        customer_config: Dict[str, Any]
    ) -> ValidationResult:
        """Validate a single checklist item"""
        requirement_id = item["id"]
        validation_spec = item.get("validation", {})
        validation_type = validation_spec.get("type")

        # Get customer's response for this requirement
        customer_response = customer_config.get(requirement_id)

        # Perform validation based on type
        if validation_type == "boolean":
            status, evidence = self._validate_boolean(customer_response)
        elif validation_type == "numeric_threshold":
            status, evidence = self._validate_numeric_threshold(
                customer_response, validation_spec
            )
        elif validation_type == "percentage_threshold":
            status, evidence = self._validate_percentage_threshold(
                customer_response, validation_spec
            )
        elif validation_type == "conditional":
            status, evidence = self._validate_conditional(
                customer_response, validation_spec
            )
        else:
            status = ValidationStatus.WARNING
            evidence = f"Unknown validation type: {validation_type}"

        # Get remediation if failed
        remediation = item.get("remediation") if status == ValidationStatus.FAIL else None

        return ValidationResult(
            requirement_id=requirement_id,
            requirement=item["requirement"],
            regulation=item["regulation"],
            status=status,
            evidence=evidence,
            remediation=remediation,
        )

    def _validate_boolean(self, customer_response: Any) -> tuple:
        """Validate boolean yes/no question"""
        if customer_response is True or str(customer_response).lower() in ["yes", "true", "1"]:
            return ValidationStatus.PASS, "Requirement met"
        elif customer_response is False or str(customer_response).lower() in ["no", "false", "0"]:
            return ValidationStatus.FAIL, "Requirement not met"
        else:
            return ValidationStatus.WARNING, f"Invalid response: {customer_response}"

    def _validate_numeric_threshold(
        self,
        customer_response: Any,
        validation_spec: Dict
    ) -> tuple:
        """Validate numeric threshold (e.g., minimum capital requirement)"""
        try:
            value = float(customer_response)
        except (ValueError, TypeError):
            return ValidationStatus.WARNING, f"Invalid numeric value: {customer_response}"

        threshold = validation_spec.get("threshold", {})
        min_value = threshold.get("min")
        max_value = threshold.get("max")
        unit = threshold.get("unit", "")

        if min_value is not None and value < min_value:
            return ValidationStatus.FAIL, f"Value {value} {unit} is below minimum {min_value} {unit}"
        if max_value is not None and value > max_value:
            return ValidationStatus.FAIL, f"Value {value} {unit} exceeds maximum {max_value} {unit}"

        return ValidationStatus.PASS, f"Value {value} {unit} meets requirements"

    def _validate_percentage_threshold(
        self,
        customer_response: Any,
        validation_spec: Dict
    ) -> tuple:
        """Validate percentage threshold (e.g., capital adequacy ratio)"""
        # Same as numeric but ensures unit is percentage
        return self._validate_numeric_threshold(customer_response, validation_spec)

    def _validate_conditional(
        self,
        customer_response: Any,
        validation_spec: Dict
    ) -> tuple:
        """Validate conditional logic (if X, then requirement is Y)"""
        conditions = validation_spec.get("conditions", [])

        for condition in conditions:
            condition_expr = condition.get("if")
            requirement = condition.get("requirement")

            # Simple expression evaluation (can be extended)
            if self._evaluate_condition(condition_expr, customer_response):
                # This condition applies - return the requirement as evidence
                return ValidationStatus.PASS, f"Applicable requirement: {requirement}"

        return ValidationStatus.WARNING, "No matching condition found"

    def _evaluate_condition(self, condition: str, value: Any) -> bool:
        """Safe condition evaluator without using eval().
        
        Supports basic comparisons: >, <, >=, <=, ==, !=
        Examples: 'value >= 100', 'value == True', 'value < 0.5'
        """
        import operator
        import re
        
        ops = {
            '>': operator.gt,
            '<': operator.lt,
            '>=': operator.ge,
            '<=': operator.le,
            '==': operator.eq,
            '!=': operator.ne,
        }
        
        try:
            # Parse condition like "value >= 100" or "value == True"
            match = re.match(r'value\s*(>=|<=|==|!=|>|<)\s*(.+)', condition.strip())
            if not match:
                return False
            
            op_str, threshold_str = match.groups()
            op_func = ops.get(op_str)
            if not op_func:
                return False
            
            # Convert threshold to appropriate type
            threshold_str = threshold_str.strip()
            if threshold_str.lower() == 'true':
                threshold = True
            elif threshold_str.lower() == 'false':
                threshold = False
            elif '.' in threshold_str:
                threshold = float(threshold_str)
            else:
                try:
                    threshold = int(threshold_str)
                except ValueError:
                    threshold = threshold_str
            
            return op_func(value, threshold)
        except Exception:
            return False

    def _generate_next_steps(
        self,
        results: List[ValidationResult],
        checklist: Dict
    ) -> List[str]:
        """Generate next steps based on validation results"""
        next_steps = []

        # Count failures
        failures = [r for r in results if r.status == ValidationStatus.FAIL]

        if not failures:
            next_steps.append(f"✓ All requirements met for {checklist['name']}")
            next_steps.append("Schedule periodic review to ensure ongoing compliance")
        else:
            next_steps.append(f"✗ {len(failures)} requirement(s) not met")
            next_steps.append("Address failed requirements before launching product/service")

            # Add top 3 failures as action items
            for failure in failures[:3]:
                next_steps.append(f"→ {failure.requirement}: {failure.remediation}")

        return next_steps


def example_usage():
    """Example usage of the Compliance Checklist Engine"""

    # Initialize engine (loads all YAML checklists)
    app_home = os.environ.get("APP_HOME", os.getcwd())
    engine = ComplianceChecklistEngine(plugin_directory=os.path.join(app_home, "industry_plugins"))

    # List all available checklists
    print("Available checklists:")
    for checklist in engine.list_checklists():
        print(f"  - {checklist['id']}: {checklist['name']} ({checklist['industry']})")

    print("\n" + "=" * 80 + "\n")

    # Example 1: HIPAA Compliance Check
    print("Example 1: Healthcare - HIPAA Compliance Check")
    print("-" * 80)

    customer_config_hipaa = {
        "hipaa_001": True,  # Encrypt PHI at rest
        "hipaa_002": True,  # Encrypt PHI in transit
        "hipaa_003": True,  # RBAC
        "hipaa_004": False,  # Audit logs (FAIL)
        "hipaa_005": True,  # Breach notification < 500
        "hipaa_006": False,  # Breach notification >= 500 (FAIL)
        "hipaa_007": True,  # Business Associate Agreements
        "hipaa_008": True,  # Annual risk assessment
    }

    result = engine.validate_checklist("hipaa_compliance", customer_config_hipaa)

    print(f"Checklist: {result.checklist_name}")
    print(f"Industry: {result.industry}")
    print(f"Jurisdiction: {result.jurisdiction}")
    print(f"Overall Status: {result.overall_status.value}")
    print(f"Pass Rate: {result.pass_rate * 100:.1f}%")
    print(f"\nItem Results:")
    for item in result.items:
        status_symbol = "✓" if item.status == ValidationStatus.PASS else "✗"
        print(f"  {status_symbol} {item.requirement_id}: {item.requirement}")
        print(f"      Status: {item.status.value} - {item.evidence}")
        if item.remediation:
            print(f"      Remediation: {item.remediation}")

    print(f"\nNext Steps:")
    for step in result.next_steps:
        print(f"  {step}")

    print("\n" + "=" * 80 + "\n")

    # Example 2: Capital Requirements Check (Finance)
    print("Example 2: Finance - Capital Requirements Check")
    print("-" * 80)

    customer_config_finance = {
        "cap_001": 500000,  # Net capital: $500k (PASS - above $250k minimum)
        "cap_002": 7.5,     # Tier 1 capital ratio: 7.5% (PASS - above 6%)
        "cap_003": 95.0,    # Liquidity coverage ratio: 95% (FAIL - below 100%)
    }

    result = engine.validate_checklist("capital_requirements", customer_config_finance)

    print(f"Checklist: {result.checklist_name}")
    print(f"Overall Status: {result.overall_status.value}")
    print(f"Pass Rate: {result.pass_rate * 100:.1f}%")
    print(f"\nItem Results:")
    for item in result.items:
        status_symbol = "✓" if item.status == ValidationStatus.PASS else "✗"
        print(f"  {status_symbol} {item.requirement}: {item.evidence}")
        if item.remediation:
            print(f"      Remediation: {item.remediation}")

    print(f"\nNext Steps:")
    for step in result.next_steps:
        print(f"  {step}")


if __name__ == "__main__":
    example_usage()
