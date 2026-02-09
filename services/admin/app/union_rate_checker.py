"""
Union Rate Checker

Validates crew/talent rates against union minimums with provenance tracking.
Loads rates from union_rate_tables.yaml and returns compliance results.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional
import yaml
import structlog

logger = structlog.get_logger(__name__)


class UnionCode(str, Enum):
    """Union identifiers."""
    SAG_AFTRA = "sag_aftra"
    DGA = "dga"
    WGA = "wga"
    IATSE_600 = "iatse_600"  # Camera
    IATSE_728 = "iatse_728"  # Electric
    IATSE_80 = "iatse_80"    # Grip
    IATSE_44 = "iatse_44"    # Props
    IATSE_705 = "iatse_705"  # Costume
    IATSE_706 = "iatse_706"  # Makeup/Hair
    IATSE_871 = "iatse_871"  # Script
    IATSE_695 = "iatse_695"  # Sound
    TEAMSTERS_399 = "teamsters_399"
    NON_UNION = "non_union"


@dataclass
class RateCheckResult:
    """Result of a union rate validation check."""
    union_code: str
    role_category: str
    minimum_rate: Decimal
    actual_rate: Decimal
    is_compliant: bool
    shortfall_amount: Decimal = Decimal("0")
    fringe_percent_required: Optional[Decimal] = None
    fringe_amount_required: Optional[Decimal] = None
    rate_table_version: str = ""
    rate_table_effective_date: Optional[date] = None
    notes: str = ""
    
    def to_dict(self) -> dict:
        return {
            "union_code": self.union_code,
            "role_category": self.role_category,
            "minimum_rate": float(self.minimum_rate),
            "actual_rate": float(self.actual_rate),
            "is_compliant": self.is_compliant,
            "shortfall_amount": float(self.shortfall_amount),
            "fringe_percent_required": float(self.fringe_percent_required) if self.fringe_percent_required else None,
            "fringe_amount_required": float(self.fringe_amount_required) if self.fringe_amount_required else None,
            "rate_table_version": self.rate_table_version,
            "rate_table_effective_date": self.rate_table_effective_date.isoformat() if self.rate_table_effective_date else None,
            "notes": self.notes,
        }


# Role category to union mapping for auto-detection
ROLE_TO_UNION_MAP = {
    # SAG-AFTRA
    "principal": "sag_aftra",
    "day_player": "sag_aftra",
    "background": "sag_aftra",
    "stand_in": "sag_aftra",
    "host": "sag_aftra",
    "actor": "sag_aftra",
    "talent": "sag_aftra",
    
    # DGA
    "director": "dga",
    "director_theatrical": "dga",
    "first_ad": "dga",
    "second_ad": "dga",
    "upm": "dga",
    
    # WGA
    "screenwriter": "wga",
    "screenwriter_original": "wga",
    "writer": "wga",
    "head_writer": "wga",
    "staff_writer": "wga",
    
    # IATSE 600 (Camera)
    "dp": "iatse_600",
    "director_of_photography": "iatse_600",
    "camera_operator": "iatse_600",
    "first_ac": "iatse_600",
    "second_ac": "iatse_600",
    "dit": "iatse_600",
    "steadicam": "iatse_600",
    
    # IATSE 728 (Electric)
    "gaffer": "iatse_728",
    "best_boy_electric": "iatse_728",
    "electrician": "iatse_728",
    "rigging_gaffer": "iatse_728",
    
    # IATSE 80 (Grip)
    "key_grip": "iatse_80",
    "best_boy_grip": "iatse_80",
    "dolly_grip": "iatse_80",
    "grip": "iatse_80",
    
    # IATSE 705 (Costume)
    "costume_designer": "iatse_705",
    "costume_supervisor": "iatse_705",
    "costumer": "iatse_705",
    "wardrobe": "iatse_705",
    
    # IATSE 706 (Makeup/Hair)
    "makeup_department_head": "iatse_706",
    "key_makeup": "iatse_706",
    "makeup_artist": "iatse_706",
    "hairstylist": "iatse_706",
    
    # IATSE 871 (Script/Coord)
    "script_supervisor": "iatse_871",
    "production_coordinator": "iatse_871",
    "production_accountant": "iatse_871",
    
    # IATSE 44 (Props)
    "prop_master": "iatse_44",
    "assistant_prop_master": "iatse_44",
    "set_decorator": "iatse_44",
    "leadman": "iatse_44",
    "propsmaster": "iatse_44",
    
    # IATSE 695 (Sound)
    "production_sound_mixer": "iatse_695",
    "sound_mixer": "iatse_695",
    "boom_operator": "iatse_695",
    "utility_sound": "iatse_695",
    
    # Teamsters 399
    "transportation_coordinator": "teamsters_399",
    "transportation_captain": "teamsters_399",
    "driver": "teamsters_399",
    
    # Non-union defaults
    "production_assistant": "non_union",
    "pa": "non_union",
    "coordinator": "non_union",
    "location_manager": "non_union",
    "craft_services": "non_union",
}


class UnionRateChecker:
    """
    Validates rates against union minimums.
    
    Usage:
        checker = UnionRateChecker()
        result = checker.check_rate(
            role_category="gaffer",
            actual_rate=450,
            budget_total=500000
        )
        if not result.is_compliant:
            logger.warning(
                "rate_below_union_minimum",
                shortfall_amount=result.shortfall_amount
            )
    """
    
    def __init__(self, rate_tables_path: Optional[str] = None):
        """Load rate tables from YAML file."""
        if rate_tables_path is None:
            # Default path relative to this file
            base_path = Path(__file__).parent.parent.parent
            rate_tables_path = base_path / "industry_plugins" / "production_ca_la" / "union_rate_tables.yaml"
        
        with open(rate_tables_path, "r") as f:
            self._data = yaml.safe_load(f)
        
        self.version = self._data.get("version", "unknown")
        self.effective_date = self._data.get("effective_date")
        if self.effective_date:
            self.effective_date = date.fromisoformat(self.effective_date)
    
    def detect_union(self, role_category: str) -> Optional[str]:
        """Detect which union covers a role category."""
        normalized = role_category.lower().replace(" ", "_").replace("-", "_")
        return ROLE_TO_UNION_MAP.get(normalized)
    
    def get_rate_tier(self, union_code: str, budget_total: float) -> Optional[dict]:
        """Get the appropriate rate tier based on budget."""
        union_data = self._data.get(union_code)
        if not union_data:
            return None
        
        # Check for tiered rates (SAG, DGA, WGA)
        tiers = []
        for key, value in union_data.items():
            if isinstance(value, dict) and "rates" in value:
                budget_min = value.get("budget_min", 0)
                budget_max = value.get("budget_max", float("inf"))
                if budget_min <= budget_total <= budget_max:
                    tiers.append((key, value))
        
        # Return lowest applicable tier (most restrictive)
        if tiers:
            return tiers[0][1]
        
        # No tiered rates, use top-level rates
        if "rates" in union_data:
            return union_data
        
        return None
    
    def get_minimum_rate(
        self,
        union_code: str,
        role_category: str,
        budget_total: float = 0,
        pay_type: str = "daily"
    ) -> Optional[Decimal]:
        """Get the minimum rate for a role."""
        tier = self.get_rate_tier(union_code, budget_total)
        if not tier:
            return None
        
        rates = tier.get("rates", {})
        normalized_role = role_category.lower().replace(" ", "_").replace("-", "_")
        
        role_rates = rates.get(normalized_role)
        if not role_rates:
            # Try partial match
            for role_name, rate_data in rates.items():
                if normalized_role in role_name or role_name in normalized_role:
                    role_rates = rate_data
                    break
        
        if not role_rates:
            return None
        
        # Get appropriate pay type
        if pay_type == "weekly" and "weekly" in role_rates:
            return Decimal(str(role_rates["weekly"]))
        elif "daily" in role_rates:
            return Decimal(str(role_rates["daily"]))
        elif "flat" in role_rates:
            return Decimal(str(role_rates["flat"]))
        elif "hourly" in role_rates:
            # Convert to daily (assume 10-hour day)
            return Decimal(str(role_rates["hourly"])) * 10
        
        return None
    
    def get_fringe_percent(self, union_code: str) -> Optional[Decimal]:
        """Get total fringe percentage for a union."""
        union_data = self._data.get(union_code, {})
        
        # Check top-level fringes
        fringes = union_data.get("fringes")
        if not fringes:
            # Check in tiers
            for key, value in union_data.items():
                if isinstance(value, dict) and "fringes" in value:
                    fringes = value["fringes"]
                    break
        
        if fringes and "total" in fringes:
            return Decimal(str(fringes["total"]))
        
        return None
    
    def check_rate(
        self,
        role_category: str,
        actual_rate: float,
        budget_total: float = 0,
        union_code: Optional[str] = None,
        pay_type: str = "daily"
    ) -> RateCheckResult:
        """
        Check if a rate meets union minimums.
        
        Args:
            role_category: The role (e.g., "gaffer", "principal", "dp")
            actual_rate: The actual daily/weekly rate being paid
            budget_total: Total budget (for tier selection)
            union_code: Override union detection
            pay_type: "daily" or "weekly"
        
        Returns:
            RateCheckResult with compliance status and details
        """
        # Detect union if not provided
        if not union_code:
            union_code = self.detect_union(role_category)
        
        if not union_code:
            # Unknown role, can't check
            return RateCheckResult(
                union_code="unknown",
                role_category=role_category,
                minimum_rate=Decimal("0"),
                actual_rate=Decimal(str(actual_rate)),
                is_compliant=True,  # Can't validate, assume OK
                rate_table_version=self.version,
                rate_table_effective_date=self.effective_date,
                notes="Unknown role category - cannot validate"
            )
        
        minimum_rate = self.get_minimum_rate(
            union_code, role_category, budget_total, pay_type
        )
        
        if minimum_rate is None:
            return RateCheckResult(
                union_code=union_code,
                role_category=role_category,
                minimum_rate=Decimal("0"),
                actual_rate=Decimal(str(actual_rate)),
                is_compliant=True,
                rate_table_version=self.version,
                rate_table_effective_date=self.effective_date,
                notes=f"No minimum rate found for {role_category} in {union_code}"
            )
        
        actual = Decimal(str(actual_rate))
        is_compliant = actual >= minimum_rate
        shortfall = max(Decimal("0"), minimum_rate - actual)
        
        fringe_percent = self.get_fringe_percent(union_code)
        fringe_amount = None
        if fringe_percent:
            fringe_amount = actual * (fringe_percent / 100)
        
        return RateCheckResult(
            union_code=union_code,
            role_category=role_category,
            minimum_rate=minimum_rate,
            actual_rate=actual,
            is_compliant=is_compliant,
            shortfall_amount=shortfall,
            fringe_percent_required=fringe_percent,
            fringe_amount_required=fringe_amount,
            rate_table_version=self.version,
            rate_table_effective_date=self.effective_date,
            notes="" if is_compliant else f"Below {union_code} minimum by ${shortfall}"
        )
    
    def check_budget_line_items(
        self,
        line_items: list[dict],
        budget_total: float = 0
    ) -> list[RateCheckResult]:
        """
        Check all line items in a budget.
        
        Args:
            line_items: List of dicts with at least "description", "rate"
            budget_total: Total budget for tier selection
        
        Returns:
            List of RateCheckResult for items that could be validated
        """
        results = []
        
        for item in line_items:
            description = item.get("description", "")
            rate = item.get("rate", 0)
            
            if not rate or rate <= 0:
                continue
            
            # Try to detect role from description
            role_category = self._extract_role_from_description(description)
            if not role_category:
                continue
            
            result = self.check_rate(
                role_category=role_category,
                actual_rate=rate,
                budget_total=budget_total
            )
            
            # Add line item reference
            result.notes = f"{description}: {result.notes}" if result.notes else description
            results.append(result)
        
        return results
    
    def _extract_role_from_description(self, description: str) -> Optional[str]:
        """Extract role category from a budget description."""
        lower = description.lower()
        
        # Check for known roles
        for role, union in ROLE_TO_UNION_MAP.items():
            role_words = role.replace("_", " ")
            if role_words in lower or role in lower:
                return role
        
        # Additional pattern matching
        patterns = {
            "producer": "producer",
            "director": "director",
            "writer": "writer",
            "camera": "camera_operator",
            "sound": "production_sound_mixer",
            "gaffer": "gaffer",
            "grip": "grip",
            "art ": "set_decorator",
            "edit": "editor",
            "post": "editor",
            "makeup": "makeup_artist",
            "hair": "hairstylist",
            "costume": "costumer",
            "wardrobe": "costumer",
            "script": "script_supervisor",
            "coord": "production_coordinator",
            "accountant": "production_accountant",
            "prop": "prop_master",
            "cast": "principal",
            "talent": "principal",
            "actor": "principal",
            "background": "background",
            "extra": "background",
            "pa ": "production_assistant",
            "production assistant": "production_assistant",
        }
        
        for pattern, role in patterns.items():
            if pattern in lower:
                return role
        
        return None
