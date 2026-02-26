#!/usr/bin/env python3
"""Domain-specific FSMA 204 compliance engine"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import statistics
import yaml

# Add shared module to path for validators
from shared import validators as val_module
from shared.fsma_rules import TimeArrowRule, TraceEvent as SharedTraceEvent

validate_gln = val_module.validate_gln
validate_fda_reg = val_module.validate_fda_reg
validate_location_identifiers = val_module.validate_location_identifiers
ValidationSeverity = val_module.ValidationSeverity
BatchValidationResult = val_module.BatchValidationResult


class RiskLevel(Enum):
    """Risk tier for FSMA compliance readiness"""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class DimensionScore:
    """Score and metadata for a control dimension"""

    id: str
    name: str
    weight: float
    score: float
    status: RiskLevel
    rationale: str
    gaps: List[str] = field(default_factory=list)
    integrity_failures: List[str] = field(default_factory=list)


@dataclass
class FSMAComplianceReport:
    """Aggregate FSMA 204 compliance output"""

    rule_metadata: Dict[str, Any]
    facility_name: str
    overall_score: float
    risk_level: RiskLevel
    dimension_scores: List[DimensionScore]
    remediation_actions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Return JSON-serializable representation"""
        return {
            "rule_metadata": self.rule_metadata,
            "facility_name": self.facility_name,
            "overall_score": round(self.overall_score, 3),
            "risk_level": self.risk_level.value,
            "dimension_scores": [
                {
                    "id": d.id,
                    "name": d.name,
                    "weight": d.weight,
                    "score": round(d.score, 3),
                    "status": d.status.value,
                    "rationale": d.rationale,
                    "gaps": d.gaps,
                    "integrity_failures": d.integrity_failures,
                }
                for d in self.dimension_scores
            ],
            "remediation_actions": self.remediation_actions,
        }


class FSMA204ComplianceEngine:
    """Domain-specific rules engine for FSMA 204"""

    def __init__(self, definition_file: Optional[str] = None):
        if definition_file is None:
            # Default to plugin directory relative to this file
            _plugins_dir = Path(__file__).parent / "plugins"
            definition_path = _plugins_dir / "food_beverage" / "fsma_204.yaml"
        else:
            definition_path = Path(definition_file)
        
        if not definition_path.exists():
            raise FileNotFoundError(f"FSMA definition file not found: {definition_path}")

        with open(definition_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)

        self.rule_metadata = data.get("metadata", {})
        self.key_data_elements = data.get("key_data_elements", [])
        self.critical_tracking_events = data.get("critical_tracking_events", [])
        self.control_dimensions = data.get("control_dimensions", {})
        self.validation_rules = data.get("validation_rules", [])
        self._definition_path = definition_path

        # Build quick lookup tables for KDEs per event
        self._kde_lookup: Dict[str, List[str]] = {
            cte["id"]: cte.get("required_kdes", []) for cte in self.critical_tracking_events
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate(self, operation_profile: Dict[str, Any]) -> FSMAComplianceReport:
        """Evaluate a facility profile and return a structured report"""

        # Run integrity validation on identifiers first
        integrity_result = self._validate_integrity(operation_profile)

        if integrity_result:
            integrity_valid, integrity_failures, _ = integrity_result
            if not integrity_valid:
                remediation = [
                    f"Resolve integrity failure: {failure}" for failure in integrity_failures
                ] or ["Resolve identifier integrity issues before FSMA scoring."]

                return FSMAComplianceReport(
                    rule_metadata=self.rule_metadata,
                    facility_name=operation_profile.get(
                        "facility_name", "Unknown Facility"
                    ),
                    overall_score=0.0,
                    risk_level=RiskLevel.CRITICAL,
                    dimension_scores=[],
                    remediation_actions=remediation,
                )

        dimension_scores = [
            self._evaluate_traceability_plan(operation_profile),
            self._evaluate_kde_capture(
                operation_profile,
                integrity_result,
                integrity_flag=bool(integrity_result[0]) if integrity_result else True,
            ),
            self._evaluate_cte_coverage(operation_profile),
            self._evaluate_recordkeeping(operation_profile),
            self._evaluate_technology_stack(operation_profile),
        ]

        total_weight = sum(d.weight for d in dimension_scores)
        weighted_sum = sum(d.score * d.weight for d in dimension_scores)
        overall_score = weighted_sum / total_weight if total_weight else 0.0
        risk_level = self._risk_from_score(overall_score)

        if integrity_result:
            integrity_valid, integrity_failures, _ = integrity_result
            if not integrity_valid and integrity_failures:
                risk_level = RiskLevel.CRITICAL

        remediation = self._build_remediation_plan(dimension_scores)

        return FSMAComplianceReport(
            rule_metadata=self.rule_metadata,
            facility_name=operation_profile.get("facility_name", "Unknown Facility"),
            overall_score=overall_score,
            risk_level=risk_level,
            dimension_scores=dimension_scores,
            remediation_actions=remediation,
        )

    # ------------------------------------------------------------------
    # Dimension evaluators
    # ------------------------------------------------------------------
    def _evaluate_traceability_plan(self, profile: Dict[str, Any]) -> DimensionScore:
        config = self.control_dimensions.get("traceability_plan", {})
        plan = profile.get("traceability_plan", {}) or {}
        required_fields: List[str] = config.get("required_fields", [])
        missing = [field for field in required_fields if not plan.get(field)]
        base_score = 1 - len(missing) / len(required_fields) if required_fields else 0.0
        base_score = max(base_score, 0.0)

        premium_fields = config.get("premium_fields", [])
        if premium_fields:
            premium_hits = sum(1 for field in premium_fields if plan.get(field))
            base_score += 0.1 * (premium_hits / len(premium_fields))

        base_score = min(base_score, 1.0)
        status = self._status_from_dimension_score(base_score)

        rationale = (
            f"{len(required_fields) - len(missing)} of {len(required_fields)} core elements present"
            if required_fields
            else "No traceability plan metadata configured"
        )
        gaps = [f"Add or document '{field}'" for field in missing]

        return DimensionScore(
            id="traceability_plan",
            name=config.get("name", "Traceability Plan"),
            weight=config.get("weight", 0.2),
            score=base_score,
            status=status,
            rationale=rationale,
            gaps=gaps,
        )

    def _evaluate_kde_capture(
        self,
        profile: Dict[str, Any],
        integrity_result: Optional[Tuple[bool, List[str], List[str]]] = None,
        *,
        integrity_flag: bool = True,
    ) -> DimensionScore:
        config = self.control_dimensions.get("kde_capture", {})
        kde_capture = profile.get("kde_capture", {}) or {}
        event_requirements: Dict[str, Dict[str, float]] = config.get("event_requirements", {})

        event_scores: List[float] = []
        gaps: List[str] = []
        rationales: List[str] = []
        integrity_failures: List[str] = []

        for event, requirement in event_requirements.items():
            required_kdes = set(self._kde_lookup.get(event, []))
            recorded_kdes = set(kde_capture.get(event, []))
            coverage = (len(recorded_kdes & required_kdes) / len(required_kdes)) if required_kdes else 0.0
            target = requirement.get("minimum_percentage", 1.0)
            normalized_score = min(coverage / target, 1.0) if target else coverage
            event_scores.append(normalized_score)

            rationales.append(
                f"{event}: {len(recorded_kdes & required_kdes)}/{len(required_kdes)} KDEs tracked"
            )
            if coverage < target:
                percentage = int(coverage * 100)
                target_pct = int(target * 100)
                missing_kdes = sorted(required_kdes - recorded_kdes)
                gap = f"{event} coverage at {percentage}% (target {target_pct}%), missing {missing_kdes}"
                gaps.append(gap)

        score = statistics.mean(event_scores) if event_scores else 0.0
        status = self._status_from_dimension_score(score)

        # Apply integrity validation results - downgrade to CRITICAL if invalid identifiers found
        if not integrity_flag:
            integrity_failures = integrity_result[1] if integrity_result else []
            score = 0.0
            status = RiskLevel.CRITICAL
            if integrity_failures:
                rationales.append(
                    f"INTEGRITY FAILURE: {len(integrity_failures)} invalid identifier(s)"
                )

        rationale = ", ".join(rationales) if rationales else "No KDE mappings supplied"

        return DimensionScore(
            id="kde_capture",
            name=config.get("name", "Key Data Elements"),
            weight=config.get("weight", 0.25),
            score=score,
            status=status,
            rationale=rationale,
            gaps=gaps,
            integrity_failures=integrity_failures,
        )

    def _evaluate_cte_coverage(self, profile: Dict[str, Any]) -> DimensionScore:
        config = self.control_dimensions.get("cte_coverage", {})
        expected_events = set(config.get("expected_events", []))
        provided_events = set(profile.get("critical_tracking_events", []))
        missing = sorted(expected_events - provided_events)
        coverage = 1 - len(missing) / len(expected_events) if expected_events else 0.0
        coverage = max(min(coverage, 1.0), 0.0)
        status = self._status_from_dimension_score(coverage)

        rationale = (
            f"{len(expected_events) - len(missing)} of {len(expected_events)} events mapped"
            if expected_events
            else "No expected events configured"
        )
        gaps = [f"Add process coverage for '{event}' CTE" for event in missing]

        return DimensionScore(
            id="cte_coverage",
            name=config.get("name", "Critical Tracking Events"),
            weight=config.get("weight", 0.2),
            score=coverage,
            status=status,
            rationale=rationale,
            gaps=gaps,
        )

    def _evaluate_recordkeeping(self, profile: Dict[str, Any]) -> DimensionScore:
        config = self.control_dimensions.get("recordkeeping", {})
        recordkeeping = profile.get("recordkeeping", {}) or {}
        retention_years = recordkeeping.get("retention_years", 0)
        retrieval_time = recordkeeping.get("retrieval_time_hours", 999)
        digital_system = recordkeeping.get("digital_system", False)

        retention_score = min(retention_years / config.get("min_retention_years", 1), 1.0)
        retrieval_score = 1.0 if retrieval_time <= config.get("max_retrieval_hours", 24) else 0.4
        digital_score = 1.0 if digital_system else 0.5

        score = statistics.mean([retention_score, retrieval_score, digital_score])
        status = self._status_from_dimension_score(score)
        gaps: List[str] = []

        if retention_years < config.get("min_retention_years", 1):
            gaps.append(
                f"Increase record retention to {config.get('min_retention_years', 1)} years"
            )
        if retrieval_time > config.get("max_retrieval_hours", 24):
            gaps.append(
                f"Improve retrieval SLA to ≤ {config.get('max_retrieval_hours', 24)} hours"
            )
        if not digital_system:
            gaps.append("Digitize traceability records or centralize in system of record")

        rationale = (
            f"Retention: {retention_years} yrs, Retrieval: {retrieval_time} hrs, Digital: {'yes' if digital_system else 'no'}"
        )

        return DimensionScore(
            id="recordkeeping",
            name=config.get("name", "Recordkeeping"),
            weight=config.get("weight", 0.15),
            score=score,
            status=status,
            rationale=rationale,
            gaps=gaps,
        )

    def _evaluate_technology_stack(self, profile: Dict[str, Any]) -> DimensionScore:
        config = self.control_dimensions.get("technology_enablement", {})
        technology = profile.get("technology", {}) or {}
        capabilities = set(technology.get("capabilities", []))
        required = set(config.get("required_capabilities", []))
        bonus = set(config.get("bonus_capabilities", []))

        required_score = (
            len(capabilities & required) / len(required) if required else 0.0
        )
        bonus_score = (
            len(capabilities & bonus) / len(bonus) if bonus else 0.0
        )

        score = min(required_score + 0.1 * bonus_score, 1.0)
        status = self._status_from_dimension_score(score)

        gaps = [f"Implement capability '{cap}'" for cap in sorted(required - capabilities)]
        rationale = f"Capabilities enabled: {sorted(capabilities)}"

        return DimensionScore(
            id="technology_enablement",
            name=config.get("name", "Technology"),
            weight=config.get("weight", 0.15),
            score=score,
            status=status,
            rationale=rationale,
            gaps=gaps,
        )

    # ------------------------------------------------------------------
    # Integrity Validation
    # ------------------------------------------------------------------
    def _validate_integrity(
        self,
        profile: Dict[str, Any],
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate data integrity of identifiers in the profile.
        
        Checks:
        - GLN (Global Location Numbers) for valid GS1 checksums
        - FDA registration numbers for valid format
        
        Args:
            profile: Operation profile containing KDE capture data

        Returns:
            Tuple of (is_valid, failure_messages, warning_messages)
        """
        if any(
            validator is None
            for validator in (validate_gln, validate_fda_reg, validate_location_identifiers)
        ):
            raise RuntimeError("Validator functions are not initialized; cannot validate integrity.")

        failures: List[str] = []
        warnings: List[str] = []
        
        # Collect all location identifiers from kde_capture
        kde_capture = profile.get("kde_capture", {}) or {}
        
        # Also check facility-level identifiers
        facility_gln = profile.get("facility_gln") or profile.get("gln")
        if facility_gln:
            result = validate_gln(str(facility_gln))
            if not result.is_valid:
                for error in result.errors:
                    failures.append(f"facility_gln: {error.message}")
            if result.warnings:
                warnings.extend(result.warnings)
        
        # Check FDA registration if present
        fda_reg = profile.get("fda_registration_number") or profile.get("fda_reg")
        if fda_reg:
            result = validate_fda_reg(str(fda_reg))
            if not result.is_valid:
                for error in result.errors:
                    failures.append(f"fda_registration: {error.message}")
            if result.warnings:
                warnings.extend(result.warnings)
        
        # Check traceability plan for identifiers
        plan = profile.get("traceability_plan", {}) or {}
        plan_locations = [
            ("origin_gln", plan.get("origin_gln")),
            ("ship_from_gln", plan.get("ship_from_gln")),
            ("ship_to_gln", plan.get("ship_to_gln")),
        ]
        
        for field_name, value in plan_locations:
            if value:
                result = validate_gln(str(value))
                if not result.is_valid:
                    for error in result.errors:
                        failures.append(f"traceability_plan.{field_name}: {error.message}")
                if result.warnings:
                    warnings.extend(result.warnings)
        
        # Check location_identifier fields in event KDE data
        # These may be nested in custom structures
        for event_type, kde_list in kde_capture.items():
            if isinstance(kde_list, dict):
                # Handle dict structure with location_identifier
                loc_id = kde_list.get("location_identifier")
                if loc_id:
                    result = validate_gln(str(loc_id))
                    if not result.is_valid:
                        for error in result.errors:
                            failures.append(
                                f"kde_capture.{event_type}.location_identifier: {error.message}"
                            )
        
        is_valid = len(failures) == 0
        return (is_valid, failures, warnings)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _status_from_dimension_score(self, score: float) -> RiskLevel:
        if score >= 0.85:
            return RiskLevel.LOW
        if score >= 0.7:
            return RiskLevel.MODERATE
        if score >= 0.5:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    def _risk_from_score(self, score: float) -> RiskLevel:
        return self._status_from_dimension_score(score)

    def _build_remediation_plan(self, dimensions: List[DimensionScore]) -> List[str]:
        gaps: List[str] = []
        for dimension in dimensions:
            for gap in dimension.gaps:
                gaps.append(f"[{dimension.name}] {gap}")
        if not gaps:
            return ["Maintain FSMA 204 controls and schedule quarterly review meetings."]
        return gaps[:10]

    # ------------------------------------------------------------------
    # TLC Validation
    # ------------------------------------------------------------------
    def validate_tlc(self, tlc: str) -> Tuple[bool, Optional[str]]:
        """
        Validate Traceability Lot Code format per FSMA 204 specification.
        
        Expected format: GTIN-14 (14 digits) + variable alphanumeric lot code
        Regex: ^\\d{14}[A-Za-z0-9\\-\\.]+$
        
        Args:
            tlc: Traceability Lot Code to validate
            
        Returns:
            Tuple of (is_valid, error_message or None)
        """
        import re
        
        if not tlc:
            return (False, "Traceability Lot Code is missing. This is a critical FSMA 204 requirement.")
        
        # Get validation rules from config (use stored rules)
        tlc_rule = next((r for r in self.validation_rules if r.get("id") == "invalid_tlc_format"), None)
        
        if tlc_rule and tlc_rule.get("regex"):
            pattern = tlc_rule["regex"]
            if not re.match(pattern, tlc):
                return (False, tlc_rule.get("error_message", "TLC format is invalid."))
        else:
            # Fallback to hardcoded pattern
            if not re.match(r"^\d{14}[A-Za-z0-9\-\.]+$", tlc):
                return (False, "TLC format is invalid. Expected: GTIN-14 (14 digits) followed by alphanumeric lot code.")
        
        return (True, None)

    def _get_validation_rules(self) -> List[Dict[str, Any]]:
        """
        Get validation rules from the FSMA 204 YAML configuration.
        
        Returns:
            List of validation rule dictionaries
        """
        return self.validation_rules

    def validate_event_tlcs(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate TLCs for a list of FSMA events.
        
        Args:
            events: List of FSMA event dictionaries with 'tlc' field
            
        Returns:
            List of validation results: [{"tlc": str, "valid": bool, "error": str|None}]
        """
        results = []
        for event in events:
            tlc = event.get("tlc") or event.get("traceability_lot_code")
            is_valid, error = self.validate_tlc(tlc)
            results.append({
                "tlc": tlc,
                "valid": is_valid,
                "error": error,
            })
        return results

    def validate_time_arrow(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate temporal ordering of an event list using the canonical shared rule.
        
        This enables the Compliance Service to serve as the Source of Truth for
        temporal validation logic.

        Args:
            events: List of event dictionaries (must contain 'event_id', 'event_date', 'type')
        
        Returns:
            Dict with 'valid' (bool) and 'violations' (list)
        """
        trace_events = []
        violations = []
        
        for e in events:
            if e.get("event_id") and e.get("event_date"):
                try:
                    trace_events.append(SharedTraceEvent(
                        event_id=e["event_id"],
                        tlc=e.get("tlc") or e.get("traceability_lot_code") or "N/A",
                        event_date=e["event_date"],
                        event_type=e.get("type")
                    ))
                except ValueError as err:
                    violations.append({
                         "violation_type": "INVALID_EVENT_DATA",
                         "event_id": e.get("event_id"),
                         "error": str(err)
                    })
        
        if violations:
            return {"valid": False, "violations": violations}
            
        rule = TimeArrowRule()
        result = rule.validate(trace_events)
        
        output_violations = []
        for v in result.violations:
            details = v.details or {}
            output_violations.append({
                 "violation_type": "TIME_ARROW",
                 "description": v.description,
                 "prev_event_id": v.event_ids[0] if v.event_ids else None,
                 "curr_event_id": v.event_ids[1] if len(v.event_ids) > 1 else None,
                 "details": details
            })
            
        return {
            "valid": result.passed,
            "violations": output_violations
        }



class FSMAApplicabilityEngine:
    """
    Engine for FSMA 204 applicability and exemption evaluation.

    Covers all 23 FTL categories per 21 CFR Part 1 Subpart S and all 6
    exemption pathways per 21 CFR §1.1305.

    CFR Section Reference:
      §1.1325 = Harvesting AND Cooling
      §1.1330 = Initial Packing (RAC, not from fishing vessel)
      §1.1335 = First Land-Based Receiving (from fishing vessel)
      §1.1340 = Shipping
      §1.1345 = Receiving
      §1.1350 = Transformation
    """

    # -------------------------------------------------------------------------
    # Authoritative FTL category list — 23 categories
    # Verified against 21 CFR Part 1 Subpart S
    # -------------------------------------------------------------------------
    FTL_CATEGORIES: List[Dict[str, Any]] = [
        {
            "id": "leafy-greens-fresh",
            "name": "Leafy Greens (fresh, intact)",
            "examples": "Whole leaf lettuce, spinach bunches, kale, arugula, chard, collard greens",
            "exclusions": "Does not include whole head cabbages or banana/grape/tree leaves.",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "TLC Source Location or Reference", "Cooling Location Identifier", "Field Identification",
            ],
        },
        {
            "id": "leafy-greens-fresh-cut",
            "name": "Leafy Greens (fresh-cut)",
            "examples": "Bagged salad mix, spring mix, pre-washed spinach, chopped romaine, salad kits",
            "exclusions": "Does not include dried or frozen leafy greens.",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Input TLCs", "New TLC Assigned",
            ],
        },
        {
            "id": "tomatoes",
            "name": "Tomatoes",
            "examples": "Fresh tomatoes (not canned or dried)",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "TLC Source Location or Reference", "Cooling Location Identifier", "Field Identification",
            ],
        },
        {
            "id": "peppers",
            "name": "Peppers",
            "examples": "Bell peppers, jalapeños, chili peppers (fresh)",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "TLC Source Location or Reference", "Cooling Location Identifier", "Field Identification",
            ],
        },
        {
            "id": "cucumbers",
            "name": "Cucumbers",
            "examples": "Fresh cucumbers",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "TLC Source Location or Reference", "Cooling Location Identifier", "Field Identification",
            ],
        },
        {
            "id": "herbs",
            "name": "Fresh Herbs",
            "examples": "Cilantro, parsley, basil (fresh cut)",
            "exclusions": "Herbs in 21 CFR 112.2(a)(1), such as dill, are exempt under §1.1305(e).",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "TLC Source Location or Reference", "Cooling Location Identifier", "Field Identification",
            ],
        },
        {
            "id": "melons",
            "name": "Melons",
            "examples": "Cantaloupe, honeydew, watermelon",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "TLC Source Location or Reference", "Cooling Location Identifier", "Field Identification",
            ],
        },
        {
            "id": "tropical-fruits",
            "name": "Tropical Tree Fruits",
            "examples": "Mangoes, papayas, mamey, guava",
            "exclusions": "Does not include bananas, pineapple, dates, coconut, avocado, or citrus.",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "TLC Source Location or Reference", "Field Identification",
            ],
        },
        {
            "id": "sprouts",
            "name": "Sprouts",
            "examples": "Alfalfa, bean, broccoli sprouts",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Harvesting", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Seed Source", "Growing Location",
            ],
        },
        {
            "id": "fresh-cut-fruits",
            "name": "Fresh-Cut Fruits",
            "examples": "Pre-cut fruit mixes, fruit cups",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Input TLCs", "New TLC Assigned",
            ],
        },
        {
            "id": "fresh-cut-vegetables",
            "name": "Fresh-Cut Vegetables (non-leafy)",
            "examples": "Veggie trays, pre-cut carrots, celery sticks, broccoli florets",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Input TLCs", "New TLC Assigned",
            ],
        },
        {
            "id": "deli-salads",
            "name": "Ready-to-Eat Deli Salads",
            "examples": "Egg salad, seafood salad, pasta salad, potato salad",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Input TLCs", "New TLC Assigned",
            ],
        },
        {
            "id": "finfish-histamine",
            "name": "Finfish — Scombrotoxin/Histamine-Forming",
            "examples": "Tuna, mackerel, mahi-mahi, bluefish, amberjack, bonito",
            "exclusions": "Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g).",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Vessel Name", "Harvest Area", "Landing Port",
            ],
        },
        {
            "id": "finfish-ciguatoxin",
            "name": "Finfish — Ciguatoxin-Associated",
            "examples": "Barracuda, grouper, snapper, moray eel (tropical reef species)",
            "exclusions": "Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g).",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Vessel Name", "Harvest Area", "Landing Port",
            ],
        },
        {
            "id": "finfish-other",
            "name": "Finfish — Other (fresh/frozen/previously frozen)",
            "examples": "Salmon, cod, halibut, tilapia, trout, bass, swordfish",
            "exclusions": "Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g).",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Vessel Name", "Harvest Area", "Landing Port",
            ],
        },
        {
            "id": "finfish-smoked",
            "name": "Smoked Finfish",
            "examples": "Smoked salmon, lox, kippered herring, smoked trout, smoked whitefish",
            "exclusions": "Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g).",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Input TLCs", "New TLC Assigned",
            ],
        },
        {
            "id": "crustaceans",
            "name": "Crustaceans",
            "examples": "Shrimp, crab, lobster, crawfish",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Harvest Area", "Vessel or Container ID",
            ],
        },
        {
            "id": "molluscan-shellfish",
            "name": "Molluscan Shellfish (bivalves)",
            "examples": "Oysters, clams, mussels, scallops",
            "exclusions": "Except when product consists entirely of shucked adductor muscle. Raw bivalves under NSSP may be exempt per §1.1305(f).",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Harvest Area", "Harvest Tag", "NSSP Dealer Certificate",
            ],
        },
        {
            "id": "eggs",
            "name": "Shell Eggs",
            "examples": "Whole shell eggs (chicken, duck)",
            "exclusions": "Farms with fewer than 3,000 laying hens are exempt per §1.1305(a)(2).",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Shipping", "Receiving"],
            "cfr_sections": "§1.1340, §1.1345",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "TLC Source Location or Reference", "Farm/Flock Identifier",
            ],
        },
        {
            "id": "nut-butters",
            "name": "Nut Butters",
            "examples": "Peanut butter, almond butter",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Input TLCs", "New TLC Assigned",
            ],
        },
        {
            "id": "cheese-fresh-soft",
            "name": "Fresh Soft Cheese",
            "examples": "Queso fresco, ricotta, mascarpone, cottage cheese, cream cheese, panela",
            "exclusions": "Hard cheeses per 21 CFR 133.150 (e.g., cheddar, parmesan, aged cotija) are excluded.",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Input TLCs", "New TLC Assigned",
            ],
        },
        {
            "id": "cheese-soft-ripened",
            "name": "Soft Ripened & Semi-Soft Cheese",
            "examples": "Brie, camembert, monterey jack, muenster, gouda, havarti, oaxaca, feta",
            "exclusions": "Hard cheeses per 21 CFR 133.150 are excluded. Semi-soft includes cheeses with moisture content >39%.",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Input TLCs", "New TLC Assigned",
            ],
        },
        {
            "id": "cheese-unpasteurized",
            "name": "Cheese Made from Unpasteurized Milk (non-hard)",
            "examples": "Raw-milk brie, raw-milk feta, raw-milk camembert, artisanal raw-milk soft cheeses",
            "exclusions": "Hard cheeses aged 60+ days per 21 CFR 133.150 are excluded even if made from unpasteurized milk.",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)", "Location Identifier (GLN)", "Date/Time",
                "Quantity & UOM", "Product Description", "Reference Document Type & Number",
                "Input TLCs", "New TLC Assigned",
            ],
        },
    ]

    # -------------------------------------------------------------------------
    # Exemption definitions — 6 pathways per 21 CFR §1.1305
    # -------------------------------------------------------------------------
    EXEMPTION_DEFINITIONS: List[Dict[str, Any]] = [
        {
            "id": "small-producer",
            "name": "Small Producer / Very Small Business",
            "citation": "21 CFR §1.1305(a)",
            "exemption_type": "FULL",
            "description": (
                "Produce farms or RAC producers averaging less than $25,000 in annual food sales "
                "over the past 3 years. Shell egg producers with fewer than 3,000 laying hens also qualify. "
                "Threshold is inflation-adjusted using 2020 as baseline."
            ),
        },
        {
            "id": "kill-step",
            "name": "Kill Step Applied",
            "citation": "21 CFR §1.1305(d)",
            "exemption_type": "FULL",
            "description": (
                "Your facility applies a kill step (cooking, pasteurization) that eliminates pathogens "
                "before the food reaches consumers. You must still keep receiving records (§1.1345) "
                "and a record of the kill step application."
            ),
        },
        {
            "id": "direct-to-consumer",
            "name": "Direct-to-Consumer Sales Only",
            "citation": "21 CFR §1.1305(b)",
            "exemption_type": "FULL",
            "description": (
                "You sell ONLY directly to consumers (farm stand, farmers market, CSA). "
                "Applies to food produced on the farm and sold/donated directly to consumers "
                "by the owner, operator, or agent."
            ),
        },
        {
            "id": "small-retail",
            "name": "Small Retail / Restaurant",
            "citation": "21 CFR §1.1305(i)",
            "exemption_type": "FULL",
            "description": (
                "Retail food establishment or restaurant averaging less than $250,000 in annual food "
                "sales over the past 3 years. Threshold is inflation-adjusted using 2020 as baseline. "
                "Most small restaurants and independent grocers qualify."
            ),
        },
        {
            "id": "rarely-consumed-raw",
            "name": "Rarely Consumed Raw",
            "citation": "21 CFR §1.1305(e)",
            "exemption_type": "FULL",
            "description": (
                "You ONLY handle produce on the FDA 'Rarely Consumed Raw' list "
                "(asparagus, potatoes, beets, etc.) as defined in 21 CFR 112.2(a)(1). "
                "These items are excluded from the FTL entirely."
            ),
        },
        {
            "id": "usda-jurisdiction",
            "name": "Exclusive USDA Jurisdiction",
            "citation": "21 CFR §1.1305(g)",
            "exemption_type": "FULL",
            "description": (
                "Your product is under exclusive USDA jurisdiction (Federal Meat Inspection Act, "
                "Poultry Products Inspection Act, or Egg Products Inspection Act). "
                "Includes Siluriformes (catfish family)."
            ),
        },
    ]

    # Set of exemption IDs for O(1) lookup
    _FULL_EXEMPT_IDS: set = {
        "small-producer", "kill-step", "direct-to-consumer",
        "small-retail", "rarely-consumed-raw", "usda-jurisdiction",
    }

    def __init__(self) -> None:
        # Build lookup dict for fast access
        self._category_map: Dict[str, Dict[str, Any]] = {
            c["id"]: c for c in self.FTL_CATEGORIES
        }
        self._exemption_map: Dict[str, Dict[str, Any]] = {
            e["id"]: e for e in self.EXEMPTION_DEFINITIONS
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_ftl_categories(self) -> List[Dict[str, Any]]:
        """Return the full list of 23 FTL categories with CTE/KDE metadata."""
        return self.FTL_CATEGORIES

    def get_exemption_definitions(self) -> List[Dict[str, Any]]:
        """Return all 6 exemption definitions."""
        return self.EXEMPTION_DEFINITIONS

    # Legacy alias kept for backward compatibility
    def get_applicability_checklist(self) -> List[Dict[str, Any]]:
        """Return list of FTL categories for selection (legacy alias)."""
        return self.get_ftl_categories()

    def evaluate_applicability(self, selections: List[str]) -> Dict[str, Any]:
        """
        Check if any selected category IDs are on the FTL.

        Args:
            selections: List of FTL category IDs (e.g. ["leafy-greens-fresh", "eggs"])

        Returns:
            dict with keys:
              - is_applicable (bool)
              - covered_categories (list of matched category dicts)
              - not_covered_categories (list of unrecognised IDs)
              - high_outbreak_count (int)
              - reason (str)
        """
        if not selections:
            return {
                "is_applicable": False,
                "covered_categories": [],
                "not_covered_categories": [],
                "high_outbreak_count": 0,
                "reason": "No categories selected",
            }

        covered = [self._category_map[sid] for sid in selections if sid in self._category_map]
        not_covered = [sid for sid in selections if sid not in self._category_map]
        high_outbreak = [c for c in covered if c.get("outbreak_frequency") == "HIGH"]

        is_applicable = len(covered) > 0
        return {
            "is_applicable": is_applicable,
            "covered_categories": covered,
            "not_covered_categories": not_covered,
            "high_outbreak_count": len(high_outbreak),
            "reason": (
                "Handles items on the FDA Food Traceability List" if is_applicable
                else "No FTL items handled"
            ),
        }

    def evaluate_exemptions(self, answers: Dict[str, bool]) -> Dict[str, Any]:
        """
        Evaluate FSMA 204 exemption status based on wizard answers.

        Args:
            answers: Dict mapping exemption IDs to boolean answers.
                     e.g. {"small-producer": False, "kill-step": True, ...}

        Returns:
            dict with keys:
              - status ("EXEMPT" | "NOT_EXEMPT")
              - is_exempt (bool)
              - active_exemptions (list of qualifying exemption dicts)
              - unanswered_count (int)
        """
        active: List[Dict[str, Any]] = []
        unanswered = 0

        for exemption_id, definition in self._exemption_map.items():
            answer = answers.get(exemption_id)
            if answer is None:
                unanswered += 1
            elif answer is True:
                active.append(definition)

        is_exempt = len(active) > 0
        if is_exempt:
            status = "EXEMPT"
        elif unanswered > 0:
            status = "UNKNOWN"
        else:
            status = "NOT_EXEMPT"

        return {
            "status": status,
            "is_exempt": is_exempt,
            "active_exemptions": active,
            "unanswered_count": unanswered,
        }


if __name__ == "__main__":
    sample_profile = {
        "facility_name": "Sample Fresh Foods Plant",
        "traceability_plan": {
            "plan_document": "s3://traceability/plan.pdf",
            "plan_owner": "Director, Food Safety",
            "update_frequency_months": 12,
            "training_program": "LMS-FSMA",
            "product_scope": ["fresh-cut fruits"],
            "digital_workflow": True,
            "kpi_dashboard": True,
        },
        "kde_capture": {
            "receiving": [
                "lot_code_source",
                "product_description",
                "quantity_uom",
                "location_identifier",
            ],
            "shipping": [
                "lot_code_source",
                "product_description",
                "quantity_uom",
                "location_identifier",
            ],
            "transformation": ["linked_lot_code", "quantity_uom", "product_description"],
        },
        "critical_tracking_events": ["receiving", "shipping", "transformation"],
        "recordkeeping": {
            "retention_years": 2,
            "retrieval_time_hours": 18,
            "digital_system": True,
        },
        "technology": {
            "capabilities": [
                "serialization",
                "api_access",
                "data_validation_rules",
                "audit_log_export",
                "streaming_events",
            ]
        },
    }

    engine = FSMA204ComplianceEngine()
    report = engine.evaluate(sample_profile)
    # Output is for CLI demonstration only
    import json
    import sys
    json.dump(report.to_dict(), sys.stdout, indent=2, default=str)
