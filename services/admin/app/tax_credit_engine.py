"""
CA Film Tax Credit 4.0 Rules Engine

Evaluates budget data against CA FTC 4.0 eligibility and spend qualification rules.
Produces detailed breakdown of qualified vs non-qualified spend and estimated credit.
"""

import yaml
import structlog
from pathlib import Path
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field

logger = structlog.get_logger(__name__)


@dataclass
class SpendCategory:
    """Represents a category of spend with qualification status."""
    code: str
    name: str
    total: Decimal = Decimal("0")
    qualified: Decimal = Decimal("0")
    non_qualified: Decimal = Decimal("0")
    status: str = "mixed"  # qualified, non_qualified, mixed, excluded
    reason: str = ""
    line_item_ids: List[str] = field(default_factory=list)
    applicable_rules: List[str] = field(default_factory=list)


@dataclass
class EligibilityResult:
    """Result of eligibility check for a tax credit program."""
    program_code: str
    program_name: str
    program_year: int
    is_eligible: bool
    eligibility_score: Decimal
    requirements_met: Dict[str, bool]
    requirements_notes: Dict[str, str]
    disqualifying_reasons: List[str]


@dataclass
class CreditCalculation:
    """Full credit calculation with breakdown."""
    base_rate: Decimal
    uplift_rate: Decimal
    total_rate: Decimal
    qualified_spend: Decimal
    non_qualified_spend: Decimal
    excluded_spend: Decimal
    estimated_credit: Decimal
    spend_categories: List[SpendCategory]
    uplifts_applied: List[str]


@dataclass
class TaxCreditAnalysis:
    """Complete tax credit analysis result."""
    eligibility: EligibilityResult
    calculation: Optional[CreditCalculation]
    evaluated_at: datetime
    rule_pack_version: str
    warnings: List[str] = field(default_factory=list)


class CATaxCreditEngine:
    """
    California Film Tax Credit 4.0 Rules Engine.
    
    Implements eligibility checks, spend categorization, and credit calculation
    based on CA Film Commission guidelines and Revenue & Tax Code §17053.98.
    """
    
    PROGRAM_CODE = "CA_FTC_4.0"
    PROGRAM_NAME = "California Film & Television Tax Credit Program 4.0"
    PROGRAM_YEAR = 2024
    RULE_PACK_VERSION = "4.0.1"
    
    # Budget department mappings to spend categories
    DEPARTMENT_CATEGORIES = {
        # Above-the-line (ATL) - excluded
        "10": ("labor_atl_story", "Story & Rights", "excluded"),
        "11": ("labor_atl_producer", "Producers", "excluded"),
        "12": ("labor_atl_director", "Directors", "excluded"),
        "13": ("labor_atl_star", "Cast - Principal", "excluded"),
        "14": ("labor_atl_cast", "Cast - Supporting", "qualified"),
        
        # Below-the-line (BTL) - generally qualified
        "20": ("labor_btl_production", "Production Staff", "qualified"),
        "21": ("labor_btl_camera", "Camera", "qualified"),
        "22": ("labor_btl_art", "Art Department", "qualified"),
        "23": ("labor_btl_set", "Set Operations", "qualified"),
        "24": ("labor_btl_electric", "Electrical", "qualified"),
        "25": ("labor_btl_grip", "Grip", "qualified"),
        "26": ("labor_btl_sound", "Sound", "qualified"),
        "27": ("labor_btl_transport", "Transportation", "qualified"),
        "28": ("labor_btl_location", "Location", "qualified"),
        "29": ("labor_btl_makeup", "Makeup & Hair", "qualified"),
        "30": ("labor_btl_wardrobe", "Wardrobe", "qualified"),
        
        # Production costs
        "40": ("materials_set", "Set Construction", "qualified"),
        "41": ("materials_props", "Props", "qualified"),
        "42": ("materials_fx", "Special Effects", "qualified"),
        "43": ("materials_wardrobe", "Wardrobe Purchases", "qualified"),
        "44": ("materials_animals", "Animals", "qualified"),
        
        # Equipment & rentals
        "50": ("equipment_camera", "Camera Equipment", "qualified"),
        "51": ("equipment_lighting", "Lighting Equipment", "qualified"),
        "52": ("equipment_grip", "Grip Equipment", "qualified"),
        "53": ("equipment_sound", "Sound Equipment", "qualified"),
        "54": ("equipment_vehicles", "Picture Vehicles", "qualified"),
        
        # Post-production
        "60": ("post_editorial", "Editorial", "qualified"),
        "61": ("post_music", "Music", "qualified"),
        "62": ("post_sound", "Post Sound", "qualified"),
        "63": ("post_vfx", "Visual Effects", "qualified"),
        
        # Other
        "70": ("overhead_insurance", "Insurance", "mixed"),
        "71": ("overhead_legal", "Legal & Accounting", "non_qualified"),
        "72": ("overhead_publicity", "Publicity", "non_qualified"),
        "73": ("overhead_office", "Production Office", "qualified"),
        
        # Fringes
        "80": ("fringes_btl", "BTL Fringes", "qualified"),
        "81": ("fringes_atl", "ATL Fringes", "excluded"),
    }
    
    # Roles that are ATL (excluded from qualified spend)
    ATL_ROLES = {
        "producer", "executive producer", "line producer", "co-producer",
        "director", "writer", "star", "lead actor", "principal cast",
        "showrunner", "creator"
    }
    
    def __init__(self, db_rules: Optional[List[Dict]] = None):
        """
        Initialize the tax credit engine.
        
        Args:
            db_rules: Optional list of rule definitions from database.
                     If not provided, uses built-in rules.
        """
        self.rules = self._load_rules(db_rules)
        logger.info(
            "tax_credit_engine_initialized",
            program=self.PROGRAM_CODE,
            rule_count=len(self.rules)
        )
    
    def _load_rules(self, db_rules: Optional[List[Dict]]) -> Dict[str, Dict]:
        """Load and index rules by category and code."""
        rules_by_code = {}
        
        if db_rules:
            for rule in db_rules:
                if rule.get("is_active", True):
                    rules_by_code[rule["rule_code"]] = rule
        else:
            # Built-in rules (fallback)
            rules_by_code = self._get_builtin_rules()
        
        return rules_by_code
    
    def _get_builtin_rules(self) -> Dict[str, Dict]:
        """Return built-in CA FTC 4.0 rules."""
        return {
            "MIN_BUDGET": {
                "rule_code": "MIN_BUDGET",
                "rule_name": "Minimum Budget Requirement",
                "rule_category": "eligibility",
                "rule_definition": {
                    "type": "threshold",
                    "field": "budget_total",
                    "operator": ">=",
                    "value": 1000000
                },
                "description": "Feature films must have minimum budget of $1M"
            },
            "CA_FILMING_PCT": {
                "rule_code": "CA_FILMING_PCT",
                "rule_name": "California Filming Percentage",
                "rule_category": "eligibility",
                "rule_definition": {
                    "type": "threshold",
                    "field": "ca_filming_days_pct",
                    "operator": ">=",
                    "value": 75
                },
                "description": "At least 75% of principal photography in CA"
            },
            "BASE_CREDIT_RATE": {
                "rule_code": "BASE_CREDIT_RATE",
                "rule_name": "Base Credit Rate",
                "rule_category": "credit_rate",
                "rule_definition": {
                    "type": "rate",
                    "base_rate": 20.0
                }
            },
            "INDIE_UPLIFT": {
                "rule_code": "INDIE_UPLIFT",
                "rule_name": "Independent Film Uplift",
                "rule_category": "uplift",
                "rule_definition": {
                    "type": "conditional_rate",
                    "condition": {"field": "is_independent", "operator": "==", "value": True},
                    "uplift": 5.0
                }
            },
            "RELOCATION_UPLIFT": {
                "rule_code": "RELOCATION_UPLIFT",
                "rule_name": "Relocation Uplift",
                "rule_category": "uplift",
                "rule_definition": {
                    "type": "conditional_rate",
                    "condition": {"field": "is_relocating", "operator": "==", "value": True},
                    "uplift": 5.0
                }
            },
            "JOBS_RATIO_UPLIFT": {
                "rule_code": "JOBS_RATIO_UPLIFT",
                "rule_name": "Jobs Ratio Uplift",
                "rule_category": "uplift",
                "rule_definition": {
                    "type": "conditional_rate",
                    "condition": {"field": "ca_jobs_ratio", "operator": ">=", "value": 0.85},
                    "uplift": 5.0
                }
            }
        }
    
    def analyze(
        self,
        budget_total: Decimal,
        line_items: List[Dict],
        project_info: Optional[Dict] = None
    ) -> TaxCreditAnalysis:
        """
        Perform complete tax credit analysis on a budget.
        
        Args:
            budget_total: Total budget amount
            line_items: List of budget line items with department, amount, role, etc.
            project_info: Optional project metadata for eligibility checks
        
        Returns:
            TaxCreditAnalysis with eligibility and credit calculation
        """
        project_info = project_info or {}
        
        # Step 1: Check eligibility
        eligibility = self._check_eligibility(budget_total, project_info)
        
        # Step 2: Categorize spend
        spend_categories = self._categorize_spend(line_items)
        
        # Step 3: Calculate credit (if eligible)
        calculation = None
        if eligibility.is_eligible or eligibility.eligibility_score >= Decimal("50"):
            calculation = self._calculate_credit(
                budget_total,
                spend_categories,
                project_info
            )
        
        # Build warnings
        warnings = self._generate_warnings(eligibility, spend_categories, budget_total)
        
        return TaxCreditAnalysis(
            eligibility=eligibility,
            calculation=calculation,
            evaluated_at=datetime.utcnow(),
            rule_pack_version=self.RULE_PACK_VERSION,
            warnings=warnings
        )
    
    def _check_eligibility(
        self,
        budget_total: Decimal,
        project_info: Dict
    ) -> EligibilityResult:
        """Check all eligibility requirements."""
        requirements_met = {}
        requirements_notes = {}
        disqualifying = []
        
        # Check minimum budget
        min_budget_met = budget_total >= Decimal("1000000")
        requirements_met["min_budget"] = min_budget_met
        if min_budget_met:
            requirements_notes["min_budget"] = f"Budget ${budget_total:,.0f} meets $1M minimum"
        else:
            requirements_notes["min_budget"] = f"Budget ${budget_total:,.0f} below $1M minimum"
            disqualifying.append("Budget does not meet $1M minimum requirement")
        
        # Check CA filming percentage (default to assuming 100% if not provided)
        ca_pct = project_info.get("ca_filming_days_pct", 100)
        ca_filming_met = ca_pct >= 75
        requirements_met["ca_filming_75pct"] = ca_filming_met
        if ca_filming_met:
            requirements_notes["ca_filming_75pct"] = f"{ca_pct}% CA filming meets 75% requirement"
        else:
            requirements_notes["ca_filming_75pct"] = f"{ca_pct}% CA filming below 75% requirement"
            disqualifying.append("Less than 75% of filming scheduled in California")
        
        # Check CA company registration (assume true if not specified)
        is_ca_registered = project_info.get("is_ca_registered", True)
        requirements_met["ca_registered"] = is_ca_registered
        if is_ca_registered:
            requirements_notes["ca_registered"] = "Production company registered in CA"
        else:
            requirements_notes["ca_registered"] = "Production company not registered in CA"
            disqualifying.append("Production company must be registered in California")
        
        # Calculate eligibility score
        met_count = sum(1 for v in requirements_met.values() if v)
        total_count = len(requirements_met)
        eligibility_score = Decimal(str(met_count / total_count * 100)) if total_count > 0 else Decimal("0")
        
        is_eligible = len(disqualifying) == 0
        
        return EligibilityResult(
            program_code=self.PROGRAM_CODE,
            program_name=self.PROGRAM_NAME,
            program_year=self.PROGRAM_YEAR,
            is_eligible=is_eligible,
            eligibility_score=eligibility_score.quantize(Decimal("0.01")),
            requirements_met=requirements_met,
            requirements_notes=requirements_notes,
            disqualifying_reasons=disqualifying
        )
    
    def _categorize_spend(self, line_items: List[Dict]) -> List[SpendCategory]:
        """Categorize line items into qualified/non-qualified spend categories."""
        categories: Dict[str, SpendCategory] = {}
        
        for item in line_items:
            dept = str(item.get("department", "99"))[:2]
            amount = Decimal(str(item.get("total_cost", 0) or 0))
            item_id = str(item.get("id", ""))
            role = (item.get("role") or item.get("description") or "").lower()
            
            # Get category info
            cat_info = self.DEPARTMENT_CATEGORIES.get(
                dept,
                ("other", "Other Costs", "mixed")
            )
            cat_code, cat_name, default_status = cat_info
            
            # Check if role is ATL (override to excluded)
            is_atl = any(atl in role for atl in self.ATL_ROLES)
            status = "excluded" if is_atl else default_status
            
            # Get or create category
            if cat_code not in categories:
                categories[cat_code] = SpendCategory(
                    code=cat_code,
                    name=cat_name,
                    status=status
                )
            
            cat = categories[cat_code]
            cat.total += amount
            cat.line_item_ids.append(item_id)
            
            # Allocate to qualified/non-qualified
            if status == "qualified":
                cat.qualified += amount
            elif status == "excluded" or status == "non_qualified":
                cat.non_qualified += amount
            else:  # mixed - default 50/50
                cat.qualified += amount * Decimal("0.5")
                cat.non_qualified += amount * Decimal("0.5")
        
        # Finalize status based on actual spend
        for cat in categories.values():
            if cat.total > 0:
                qual_pct = cat.qualified / cat.total * 100
                if qual_pct >= 95:
                    cat.status = "qualified"
                    cat.reason = "All spend in this category qualifies"
                elif qual_pct <= 5:
                    cat.status = "non_qualified" if "excluded" not in cat.code else "excluded"
                    cat.reason = "No spend in this category qualifies"
                else:
                    cat.status = "mixed"
                    cat.reason = f"{qual_pct:.0f}% of spend qualifies"
        
        return list(categories.values())
    
    def _calculate_credit(
        self,
        budget_total: Decimal,
        spend_categories: List[SpendCategory],
        project_info: Dict
    ) -> CreditCalculation:
        """Calculate estimated tax credit based on qualified spend."""
        # Sum up spend
        qualified = sum(c.qualified for c in spend_categories)
        non_qualified = sum(c.non_qualified for c in spend_categories)
        excluded = sum(
            c.non_qualified for c in spend_categories 
            if c.status == "excluded"
        )
        
        # Base rate
        base_rate = Decimal("20.0")
        uplift_rate = Decimal("0")
        uplifts_applied = []
        
        # Check uplifts
        if project_info.get("is_independent"):
            uplift_rate += Decimal("5.0")
            uplifts_applied.append("Independent Film (+5%)")
        
        if project_info.get("is_relocating"):
            uplift_rate += Decimal("5.0")
            uplifts_applied.append("Relocation (+5%)")
        
        ca_jobs_ratio = project_info.get("ca_jobs_ratio", 0.8)
        if ca_jobs_ratio >= 0.85:
            uplift_rate += Decimal("5.0")
            uplifts_applied.append("Jobs Ratio 85%+ (+5%)")
        
        total_rate = base_rate + uplift_rate
        estimated_credit = qualified * total_rate / Decimal("100")
        
        return CreditCalculation(
            base_rate=base_rate,
            uplift_rate=uplift_rate,
            total_rate=total_rate,
            qualified_spend=qualified.quantize(Decimal("0.01")),
            non_qualified_spend=non_qualified.quantize(Decimal("0.01")),
            excluded_spend=excluded.quantize(Decimal("0.01")),
            estimated_credit=estimated_credit.quantize(Decimal("0.01")),
            spend_categories=spend_categories,
            uplifts_applied=uplifts_applied
        )
    
    def _generate_warnings(
        self,
        eligibility: EligibilityResult,
        spend_categories: List[SpendCategory],
        budget_total: Decimal
    ) -> List[str]:
        """Generate helpful warnings about the analysis."""
        warnings = []
        
        # Low qualified spend warning
        total_spend = sum(c.total for c in spend_categories)
        qualified_spend = sum(c.qualified for c in spend_categories)
        
        if total_spend > 0:
            qual_pct = qualified_spend / total_spend * 100
            if qual_pct < 50:
                warnings.append(
                    f"Only {qual_pct:.0f}% of spend qualifies. "
                    "Review vendor locations and crew residency."
                )
        
        # Above-the-line heavy budget
        atl_spend = sum(
            c.total for c in spend_categories 
            if "atl" in c.code
        )
        if total_spend > 0 and atl_spend / total_spend > Decimal("0.3"):
            warnings.append(
                "Above-the-line costs exceed 30% of budget. "
                "ATL costs are excluded from qualified spend."
            )
        
        # Near threshold warnings
        if not eligibility.requirements_met.get("min_budget"):
            shortfall = Decimal("1000000") - budget_total
            warnings.append(
                f"Budget is ${shortfall:,.0f} below minimum. "
                "Consider adjusting scope to qualify."
            )
        
        return warnings


def analyze_budget_for_tax_credit(
    budget_total: float,
    line_items: List[Dict],
    project_info: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Convenience function to analyze a budget for CA Film Tax Credit.
    
    Returns a dictionary suitable for JSON serialization and API response.
    """
    engine = CATaxCreditEngine()
    analysis = engine.analyze(
        Decimal(str(budget_total)),
        line_items,
        project_info
    )
    
    # Convert to dict for API
    result = {
        "program_code": analysis.eligibility.program_code,
        "program_name": analysis.eligibility.program_name,
        "program_year": analysis.eligibility.program_year,
        "eligibility": {
            "is_eligible": analysis.eligibility.is_eligible,
            "score": float(analysis.eligibility.eligibility_score),
            "requirements_met": analysis.eligibility.requirements_met,
            "requirements_notes": analysis.eligibility.requirements_notes,
            "disqualifying_reasons": analysis.eligibility.disqualifying_reasons
        },
        "evaluated_at": analysis.evaluated_at.isoformat(),
        "rule_pack_version": analysis.rule_pack_version,
        "warnings": analysis.warnings
    }
    
    if analysis.calculation:
        calc = analysis.calculation
        result["credit_calculation"] = {
            "base_rate": float(calc.base_rate),
            "uplift_rate": float(calc.uplift_rate),
            "total_rate": float(calc.total_rate),
            "qualified_spend": float(calc.qualified_spend),
            "non_qualified_spend": float(calc.non_qualified_spend),
            "excluded_spend": float(calc.excluded_spend),
            "estimated_credit": float(calc.estimated_credit),
            "uplifts_applied": calc.uplifts_applied,
            "spend_categories": [
                {
                    "code": c.code,
                    "name": c.name,
                    "total": float(c.total),
                    "qualified": float(c.qualified),
                    "non_qualified": float(c.non_qualified),
                    "status": c.status,
                    "reason": c.reason,
                    "line_item_count": len(c.line_item_ids)
                }
                for c in calc.spend_categories
            ]
        }
    
    return result
