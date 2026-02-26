"""
Fringe & Payroll Tax Calculator

Calculates union fringe contributions and employer payroll tax burden
for entertainment production workers in California.
"""

import yaml
import structlog
from pathlib import Path
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum

logger = structlog.get_logger(__name__)

# Path to fringe tables
FRINGE_TABLES_PATH = Path(__file__).parent.parent.parent / "industry_plugins" / "production_ca_la" / "union_fringe_tables.yaml"


@dataclass
class FringeBreakdown:
    """Breakdown of fringe costs for a worker."""
    union_code: str
    union_name: str
    gross_wages: Decimal
    
    # Union fringes
    pension_pct: Decimal = Decimal("0")
    pension_amount: Decimal = Decimal("0")
    health_welfare_pct: Decimal = Decimal("0")
    health_welfare_amount: Decimal = Decimal("0")
    vacation_pct: Decimal = Decimal("0")
    vacation_amount: Decimal = Decimal("0")
    total_union_fringe_pct: Decimal = Decimal("0")
    total_union_fringe_amount: Decimal = Decimal("0")
    
    # Statutory taxes (employer side)
    fica_ss_amount: Decimal = Decimal("0")
    fica_med_amount: Decimal = Decimal("0")
    futa_amount: Decimal = Decimal("0")
    sui_amount: Decimal = Decimal("0")
    ett_amount: Decimal = Decimal("0")
    total_statutory_amount: Decimal = Decimal("0")
    
    # Workers comp
    workers_comp_rate_per_100: Decimal = Decimal("0")
    workers_comp_amount: Decimal = Decimal("0")
    
    # Totals
    total_employer_cost: Decimal = Decimal("0")
    total_burden_pct: Decimal = Decimal("0")


@dataclass 
class PayrollTaxEstimate:
    """Payroll tax estimate for a wage amount."""
    gross_wages: Decimal
    fica_ss: Decimal = Decimal("0")
    fica_med: Decimal = Decimal("0")
    futa: Decimal = Decimal("0")
    sui: Decimal = Decimal("0")
    ett: Decimal = Decimal("0")
    workers_comp: Decimal = Decimal("0")
    total: Decimal = Decimal("0")


@dataclass
class BudgetFringeAnalysis:
    """Analysis of fringes for an entire budget."""
    total_labor_cost: Decimal
    total_union_fringes: Decimal
    total_statutory_taxes: Decimal
    total_workers_comp: Decimal
    total_employer_burden: Decimal
    budgeted_fringes: Decimal
    shortfall: Decimal
    shortfall_pct: Decimal
    line_item_breakdowns: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class FringeCalculator:
    """
    Calculator for union fringes and payroll taxes.
    
    Loads rate tables from YAML and provides calculation methods
    for individual workers and entire budgets.
    """
    
    # 2024 wage base limits
    SS_WAGE_BASE = Decimal("168600")
    FUTA_WAGE_BASE = Decimal("7000")
    SUI_WAGE_BASE = Decimal("7000")
    SDI_WAGE_BASE = Decimal("153164")
    
    # Standard rates
    FICA_SS_RATE = Decimal("0.062")
    FICA_MED_RATE = Decimal("0.0145")
    FUTA_RATE = Decimal("0.006")  # After SUTA credit
    CA_SUI_RATE = Decimal("0.034")  # New employer rate
    CA_ETT_RATE = Decimal("0.001")
    
    # Default workers comp rate
    DEFAULT_WC_RATE = Decimal("2.50")
    
    def __init__(self, tables_path: Optional[Path] = None):
        """
        Initialize calculator with fringe tables.
        
        Args:
            tables_path: Path to union_fringe_tables.yaml
        """
        self.tables_path = tables_path or FRINGE_TABLES_PATH
        self.fringe_rates = {}
        self.payroll_taxes = {}
        self.workers_comp = {}
        
        self._load_tables()
    
    def _load_tables(self):
        """Load fringe and tax tables from YAML."""
        try:
            if self.tables_path.exists():
                with open(self.tables_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    self.fringe_rates = data.get("fringe_rates", {})
                    self.payroll_taxes = data.get("payroll_taxes", {})
                    self.workers_comp = data.get("workers_comp", {})
                    
                logger.info(
                    "fringe_tables_loaded",
                    unions=len(self.fringe_rates),
                    path=str(self.tables_path)
                )
            else:
                logger.warning("fringe_tables_not_found", path=str(self.tables_path))
                self._use_defaults()
        except Exception as e:
            logger.error("fringe_tables_load_error", error=str(e))
            self._use_defaults()
    
    def _use_defaults(self):
        """Use built-in default rates."""
        self.fringe_rates = {
            "SAG-AFTRA": {"total_fringe_pct": 17.0, "pension_contribution_pct": 17.0},
            "DGA": {"total_fringe_pct": 16.0, "pension_contribution_pct": 8.5, "health_welfare_pct": 7.5},
            "IATSE": {"total_fringe_pct": 24.719, "pension_contribution_pct": 9.0, "health_welfare_pct": 8.0, "vacation_pay_pct": 7.719},
            "TEAMSTERS_399": {"total_fringe_pct": 27.5, "pension_contribution_pct": 10.0, "health_welfare_pct": 9.5, "vacation_pay_pct": 8.0},
            "NON_UNION": {"total_fringe_pct": 0.0},
        }
    
    def calculate_fringes(
        self,
        gross_wages: float,
        union_code: str = "NON_UNION",
        role_category: str = "production",
        ytd_wages: float = 0
    ) -> FringeBreakdown:
        """
        Calculate complete fringe breakdown for a worker.
        
        Args:
            gross_wages: Gross wages for the period
            union_code: Union code (SAG-AFTRA, IATSE_LOCAL_600, etc.)
            role_category: Role category for workers comp
            ytd_wages: Year-to-date wages (for tax cap calculations)
            
        Returns:
            FringeBreakdown with all costs itemized
        """
        wages = Decimal(str(gross_wages))
        ytd = Decimal(str(ytd_wages))
        
        # Get union rates
        union_rates = self.fringe_rates.get(union_code, self.fringe_rates.get("NON_UNION", {}))
        union_name = union_rates.get("description", union_code)
        
        # Calculate union fringes
        pension_pct = Decimal(str(union_rates.get("pension_contribution_pct", 0)))
        hw_pct = Decimal(str(union_rates.get("health_welfare_pct", 0)))
        vacation_pct = Decimal(str(union_rates.get("vacation_pay_pct", 0)))
        total_fringe_pct = Decimal(str(union_rates.get("total_fringe_pct", 0)))
        
        pension_amount = wages * pension_pct / 100
        hw_amount = wages * hw_pct / 100
        vacation_amount = wages * vacation_pct / 100
        total_union = wages * total_fringe_pct / 100
        
        # Calculate statutory taxes
        fica_ss = self._calc_with_cap(wages, ytd, self.SS_WAGE_BASE, self.FICA_SS_RATE)
        fica_med = wages * self.FICA_MED_RATE
        futa = self._calc_with_cap(wages, ytd, self.FUTA_WAGE_BASE, self.FUTA_RATE)
        sui = self._calc_with_cap(wages, ytd, self.SUI_WAGE_BASE, self.CA_SUI_RATE)
        ett = self._calc_with_cap(wages, ytd, self.SUI_WAGE_BASE, self.CA_ETT_RATE)
        
        total_statutory = fica_ss + fica_med + futa + sui + ett
        
        # Calculate workers comp
        wc_rate = self._get_wc_rate(role_category)
        workers_comp = wages * wc_rate / 100
        
        # Calculate totals
        total_employer = total_union + total_statutory + workers_comp
        burden_pct = (total_employer / wages * 100) if wages > 0 else Decimal("0")
        
        return FringeBreakdown(
            union_code=union_code,
            union_name=union_name,
            gross_wages=wages.quantize(Decimal("0.01")),
            pension_pct=pension_pct,
            pension_amount=pension_amount.quantize(Decimal("0.01")),
            health_welfare_pct=hw_pct,
            health_welfare_amount=hw_amount.quantize(Decimal("0.01")),
            vacation_pct=vacation_pct,
            vacation_amount=vacation_amount.quantize(Decimal("0.01")),
            total_union_fringe_pct=total_fringe_pct,
            total_union_fringe_amount=total_union.quantize(Decimal("0.01")),
            fica_ss_amount=fica_ss.quantize(Decimal("0.01")),
            fica_med_amount=fica_med.quantize(Decimal("0.01")),
            futa_amount=futa.quantize(Decimal("0.01")),
            sui_amount=sui.quantize(Decimal("0.01")),
            ett_amount=ett.quantize(Decimal("0.01")),
            total_statutory_amount=total_statutory.quantize(Decimal("0.01")),
            workers_comp_rate_per_100=wc_rate,
            workers_comp_amount=workers_comp.quantize(Decimal("0.01")),
            total_employer_cost=total_employer.quantize(Decimal("0.01")),
            total_burden_pct=burden_pct.quantize(Decimal("0.01"))
        )
    
    def _calc_with_cap(
        self,
        wages: Decimal,
        ytd: Decimal,
        cap: Decimal,
        rate: Decimal
    ) -> Decimal:
        """Calculate tax with wage base cap."""
        if ytd >= cap:
            return Decimal("0")
        
        taxable = min(wages, cap - ytd)
        return taxable * rate
    
    def _get_wc_rate(self, role_category: str) -> Decimal:
        """Get workers comp rate for role category."""
        category_map = {
            "production": "MOTION_PICTURE_PRODUCTION",
            "technical": "MOTION_PICTURE_TECHNICAL",
            "stunts": "MOTION_PICTURE_STUNTS",
            "driver": "DRIVERS_COMMERCIAL",
            "office": "CLERICAL_OFFICE",
            "construction": "CONSTRUCTION_CARPENTRY"
        }
        
        wc_code = category_map.get(role_category.lower(), "MOTION_PICTURE_PRODUCTION")
        classifications = self.workers_comp.get("classifications", {})
        
        if wc_code in classifications:
            return Decimal(str(classifications[wc_code].get("rate_per_100", self.DEFAULT_WC_RATE)))
        
        return Decimal(str(self.workers_comp.get("default_rate_per_100", self.DEFAULT_WC_RATE)))
    
    def analyze_budget_fringes(
        self,
        line_items: List[Dict],
        budgeted_fringes: float = 0
    ) -> BudgetFringeAnalysis:
        """
        Analyze fringe requirements for an entire budget.
        
        Args:
            line_items: List of budget line items with labor costs
            budgeted_fringes: Amount budgeted for fringes
            
        Returns:
            BudgetFringeAnalysis with shortfall detection
        """
        total_labor = Decimal("0")
        total_union = Decimal("0")
        total_statutory = Decimal("0")
        total_wc = Decimal("0")
        breakdowns = []
        warnings = []
        
        for item in line_items:
            # Skip non-labor items
            dept = str(item.get("department", ""))
            if dept.startswith("4") or dept.startswith("5") or dept.startswith("6"):
                # Equipment, materials, post - not labor
                continue
            
            labor_cost = Decimal(str(item.get("total_cost", 0) or 0))
            if labor_cost <= 0:
                continue
            
            total_labor += labor_cost
            
            # Detect union from role/description
            role = (item.get("description") or "").lower()
            union_code = self._detect_union_from_role(role)
            role_cat = self._detect_role_category(role)
            
            breakdown = self.calculate_fringes(float(labor_cost), union_code, role_cat)
            
            total_union += breakdown.total_union_fringe_amount
            total_statutory += breakdown.total_statutory_amount
            total_wc += breakdown.workers_comp_amount
            
            breakdowns.append({
                "line_item_id": item.get("id"),
                "description": item.get("description"),
                "labor_cost": float(labor_cost),
                "union_code": union_code,
                "union_fringe": float(breakdown.total_union_fringe_amount),
                "statutory": float(breakdown.total_statutory_amount),
                "workers_comp": float(breakdown.workers_comp_amount),
                "total_burden": float(breakdown.total_employer_cost),
                "burden_pct": float(breakdown.total_burden_pct)
            })
        
        total_employer = total_union + total_statutory + total_wc
        budgeted = Decimal(str(budgeted_fringes))
        shortfall = total_employer - budgeted
        shortfall_pct = (shortfall / total_employer * 100) if total_employer > 0 else Decimal("0")
        
        # Generate warnings
        if shortfall > 0:
            warnings.append(f"Budget is ${float(shortfall):,.2f} short on fringes ({float(shortfall_pct):.1f}%)")
        
        statutory_pct = (total_statutory / total_labor * 100) if total_labor > 0 else Decimal("0")
        if statutory_pct < Decimal("10"):
            warnings.append("Statutory tax estimate may be low; verify payroll setup")
        
        return BudgetFringeAnalysis(
            total_labor_cost=total_labor.quantize(Decimal("0.01")),
            total_union_fringes=total_union.quantize(Decimal("0.01")),
            total_statutory_taxes=total_statutory.quantize(Decimal("0.01")),
            total_workers_comp=total_wc.quantize(Decimal("0.01")),
            total_employer_burden=total_employer.quantize(Decimal("0.01")),
            budgeted_fringes=budgeted.quantize(Decimal("0.01")),
            shortfall=shortfall.quantize(Decimal("0.01")),
            shortfall_pct=shortfall_pct.quantize(Decimal("0.01")),
            line_item_breakdowns=breakdowns,
            warnings=warnings
        )
    
    def _detect_union_from_role(self, role: str) -> str:
        """Detect likely union from role description."""
        role = role.lower()
        
        if any(x in role for x in ["actor", "cast", "performer", "star", "talent"]):
            return "SAG-AFTRA"
        if any(x in role for x in ["director", "1st ad", "2nd ad", "assistant director", "upm"]):
            return "DGA"
        if any(x in role for x in ["writer", "screenwriter"]):
            return "WGA"
        if any(x in role for x in ["camera", "dp", "cinematographer", "focus", "loader"]):
            return "IATSE_LOCAL_600"
        if any(x in role for x in ["electric", "gaffer", "best boy electric", "lamp"]):
            return "IATSE_LOCAL_728"
        if any(x in role for x in ["grip", "key grip", "dolly", "rigging"]):
            return "IATSE_LOCAL_80"
        if any(x in role for x in ["prop", "set dec", "set dress", "greens"]):
            return "IATSE_LOCAL_44"
        if any(x in role for x in ["costume", "wardrobe"]):
            return "IATSE_LOCAL_705"
        if any(x in role for x in ["makeup", "hair", "mua"]):
            return "IATSE_LOCAL_706"
        if any(x in role for x in ["script supervisor", "scripty"]):
            return "IATSE_LOCAL_871"
        if any(x in role for x in ["sound", "mixer", "boom"]):
            return "IATSE_LOCAL_695"
        if any(x in role for x in ["driver", "teamster", "transportation"]):
            return "TEAMSTERS_399"
        
        return "NON_UNION"
    
    def _detect_role_category(self, role: str) -> str:
        """Detect role category for workers comp."""
        role = role.lower()
        
        if any(x in role for x in ["stunt", "stuntman", "stuntwoman"]):
            return "stunts"
        if any(x in role for x in ["driver", "teamster", "transportation"]):
            return "driver"
        if any(x in role for x in ["camera", "grip", "electric", "gaffer", "sound"]):
            return "technical"
        if any(x in role for x in ["construction", "carpenter", "scenic"]):
            return "construction"
        if any(x in role for x in ["coordinator", "accountant", "office", "pa"]):
            return "office"
        
        return "production"


def calculate_budget_fringes(
    line_items: List[Dict],
    budgeted_fringes: float = 0
) -> Dict[str, Any]:
    """
    Convenience function to analyze budget fringes.
    
    Returns a dictionary suitable for JSON serialization.
    """
    calculator = FringeCalculator()
    analysis = calculator.analyze_budget_fringes(line_items, budgeted_fringes)
    
    return {
        "total_labor_cost": float(analysis.total_labor_cost),
        "total_union_fringes": float(analysis.total_union_fringes),
        "total_statutory_taxes": float(analysis.total_statutory_taxes),
        "total_workers_comp": float(analysis.total_workers_comp),
        "total_employer_burden": float(analysis.total_employer_burden),
        "budgeted_fringes": float(analysis.budgeted_fringes),
        "shortfall": float(analysis.shortfall),
        "shortfall_pct": float(analysis.shortfall_pct),
        "is_underfunded": float(analysis.shortfall) > 0,
        "warnings": analysis.warnings,
        "line_item_count": len(analysis.line_item_breakdowns),
        "breakdown_by_item": analysis.line_item_breakdowns
    }
