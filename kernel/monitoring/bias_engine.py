"""
Bias Engine
===========
Statistical bias detection for protected characteristics.

Implements:
- Disparate Impact Ratio (DIR)
- 80% Rule (EEOC guidance)
- Chi-square test for independence
- Fisher's exact test (small samples)
- Statistical significance determination

Based on test vectors from services/analytics/tests/test_bias_vectors.py
"""

import numpy as np
from typing import Dict, List, Any, Optional
from scipy.stats import chi2_contingency, fisher_exact
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ProtectedClass(str, Enum):
    """Protected characteristics under ECOA."""
    RACE = "race"
    SEX = "sex"
    MARITAL_STATUS = "marital_status"
    RELIGION = "religion"
    NATIONAL_ORIGIN = "national_origin"
    AGE = "age"
    RECEIPT_PUBLIC_ASSISTANCE = "receipt_public_assistance"


class BiasTestResult(BaseModel):
    """Result of a single bias test."""
    protected_class: str
    reference_group: str
    protected_group: str
    
    # Counts
    reference_approvals: int
    reference_total: int
    protected_approvals: int
    protected_total: int
    
    # Metrics
    disparate_impact_ratio: float = Field(..., description="DIR: protected_rate / reference_rate")
    passes_80_rule: bool = Field(..., description="DIR >= 0.80")
    
    # Statistical tests
    chi_square_statistic: Optional[float] = None
    chi_square_p_value: Optional[float] = None
    fisher_exact_p_value: Optional[float] = None
    statistically_significant: bool = Field(default=False, description="p < 0.05")
    
    # Severity
    severity: str = Field(..., description="none, moderate, severe")


class BiasReport(BaseModel):
    """Complete bias analysis report."""
    report_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_id: str
    decision_type: str
    
    # Analysis period
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    total_decisions: int
    
    # Test results
    test_results: List[BiasTestResult]
    
    # Overall assessment
    all_tests_pass: bool
    failed_classes: List[str] = Field(default_factory=list)
    statistically_significant_failures: List[str] = Field(default_factory=list)
    
    # Risk score
    bias_risk_score: float = Field(..., ge=0.0, le=1.0, description="0=no bias, 1=severe bias")


class BiasEngine:
    """
    Bias detection engine.
    
    EEOC 80% Rule:
    - DIR >= 0.80: No adverse impact
    - DIR < 0.80: Potential adverse impact
    
    Statistical Significance:
    - Chi-square test: Used for large samples (expected counts > 5)
    - Fisher exact test: Used for small samples (expected counts <= 5)
    - p < 0.05: Statistically significant
    """
    
    def __init__(self, significance_level: float = 0.05):
        """
        Initialize bias engine.
        
        Args:
            significance_level: p-value threshold for statistical significance (default 0.05)
        """
        self.significance_level = significance_level
    
    def analyze_bias(
        self,
        model_id: str,
        decision_type: str,
        decisions: List[Dict[str, Any]],
        protected_classes: List[str] = None
    ) -> BiasReport:
        """
        Analyze bias across protected characteristics.
        
        Args:
            model_id: Model identifier
            decision_type: Type of decision (e.g., credit_approval)
            decisions: List of decision records with 'outcome' and protected class attributes
            protected_classes: List of protected class attributes to test (default: all)
        
        Returns:
            BiasReport with test results
        """
        if protected_classes is None:
            protected_classes = [pc.value for pc in ProtectedClass]
        
        test_results = []
        
        for protected_class in protected_classes:
            # Group decisions by protected class
            groups = self._group_by_protected_class(decisions, protected_class)
            
            if len(groups) < 2:
                continue  # Need at least 2 groups to test
            
            # Identify reference group (typically majority/advantaged group)
            reference_group = self._identify_reference_group(groups)
            
            # Test each protected group against reference
            for group_name, group_decisions in groups.items():
                if group_name == reference_group:
                    continue
                
                test_result = self._test_disparate_impact(
                    protected_class=protected_class,
                    reference_group=reference_group,
                    reference_decisions=groups[reference_group],
                    protected_group=group_name,
                    protected_decisions=group_decisions
                )
                
                test_results.append(test_result)
        
        # Overall assessment
        all_tests_pass = all(result.passes_80_rule for result in test_results)
        failed_classes = [
            f"{result.protected_class}:{result.protected_group}"
            for result in test_results
            if not result.passes_80_rule
        ]
        statistically_significant_failures = [
            f"{result.protected_class}:{result.protected_group}"
            for result in test_results
            if not result.passes_80_rule and result.statistically_significant
        ]
        
        # Compute bias risk score
        bias_risk_score = self._compute_bias_risk_score(test_results)
        
        return BiasReport(
            report_id=f"bias_{model_id}_{datetime.utcnow().isoformat()}",
            model_id=model_id,
            decision_type=decision_type,
            total_decisions=len(decisions),
            test_results=test_results,
            all_tests_pass=all_tests_pass,
            failed_classes=failed_classes,
            statistically_significant_failures=statistically_significant_failures,
            bias_risk_score=bias_risk_score
        )
    
    def _group_by_protected_class(
        self,
        decisions: List[Dict[str, Any]],
        protected_class: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group decisions by protected class attribute."""
        groups = {}
        for decision in decisions:
            if protected_class not in decision:
                continue
            
            group_value = decision[protected_class]
            if group_value not in groups:
                groups[group_value] = []
            groups[group_value].append(decision)
        
        return groups
    
    def _identify_reference_group(self, groups: Dict[str, List]) -> str:
        """Identify reference group (typically largest group)."""
        return max(groups.keys(), key=lambda k: len(groups[k]))
    
    def _test_disparate_impact(
        self,
        protected_class: str,
        reference_group: str,
        reference_decisions: List[Dict[str, Any]],
        protected_group: str,
        protected_decisions: List[Dict[str, Any]]
    ) -> BiasTestResult:
        """
        Test for disparate impact between reference and protected groups.
        
        Steps:
        1. Compute approval rates
        2. Compute DIR
        3. Apply 80% rule
        4. Run statistical tests (chi-square or Fisher exact)
        5. Determine severity
        """
        # Count approvals
        ref_approvals = sum(1 for d in reference_decisions if d.get('outcome') == 'approved')
        ref_total = len(reference_decisions)
        
        prot_approvals = sum(1 for d in protected_decisions if d.get('outcome') == 'approved')
        prot_total = len(protected_decisions)
        
        # Compute rates
        ref_rate = ref_approvals / ref_total if ref_total > 0 else 0
        prot_rate = prot_approvals / prot_total if prot_total > 0 else 0
        
        # Compute DIR
        dir_ratio = prot_rate / ref_rate if ref_rate > 0 else 0
        passes_80_rule = dir_ratio >= 0.80
        
        # Statistical tests
        chi_square_stat, chi_square_p, fisher_p = None, None, None
        statistically_significant = False
        
        # Contingency table: [[ref_approved, ref_denied], [prot_approved, prot_denied]]
        contingency_table = np.array([
            [ref_approvals, ref_total - ref_approvals],
            [prot_approvals, prot_total - prot_approvals]
        ])
        
        # Determine which test to use
        expected_counts = self._compute_expected_counts(contingency_table)
        use_fisher = any(count < 5 for count in expected_counts.flatten())
        
        if use_fisher:
            # Fisher's exact test
            _, fisher_p = fisher_exact(contingency_table)
            statistically_significant = fisher_p < self.significance_level
        else:
            # Chi-square test
            chi_square_stat, chi_square_p, _, _ = chi2_contingency(contingency_table)
            statistically_significant = chi_square_p < self.significance_level
        
        # Determine severity
        severity = self._determine_severity(dir_ratio, statistically_significant)
        
        return BiasTestResult(
            protected_class=protected_class,
            reference_group=reference_group,
            protected_group=protected_group,
            reference_approvals=ref_approvals,
            reference_total=ref_total,
            protected_approvals=prot_approvals,
            protected_total=prot_total,
            disparate_impact_ratio=dir_ratio,
            passes_80_rule=passes_80_rule,
            chi_square_statistic=chi_square_stat,
            chi_square_p_value=chi_square_p,
            fisher_exact_p_value=fisher_p,
            statistically_significant=statistically_significant,
            severity=severity
        )
    
    def _compute_expected_counts(self, contingency_table: np.ndarray) -> np.ndarray:
        """Compute expected counts for chi-square test."""
        row_totals = contingency_table.sum(axis=1)
        col_totals = contingency_table.sum(axis=0)
        total = contingency_table.sum()
        
        expected = np.outer(row_totals, col_totals) / total
        return expected
    
    def _determine_severity(self, dir_ratio: float, statistically_significant: bool) -> str:
        """
        Determine bias severity.
        
        Severity levels:
        - none: DIR >= 0.80
        - moderate: 0.50 <= DIR < 0.80 (or not statistically significant)
        - severe: DIR < 0.50 and statistically significant
        """
        if dir_ratio >= 0.80:
            return "none"
        elif dir_ratio >= 0.50 or not statistically_significant:
            return "moderate"
        else:
            return "severe"
    
    def _compute_bias_risk_score(self, test_results: List[BiasTestResult]) -> float:
        """
        Compute overall bias risk score.
        
        Score formula:
        - Start at 0.0 (no bias)
        - +0.20 per failed 80% rule test
        - +0.30 if failure is statistically significant
        - Cap at 1.0
        """
        if not test_results:
            return 0.0
        
        risk_score = 0.0
        
        for result in test_results:
            if not result.passes_80_rule:
                risk_score += 0.20
                
                if result.statistically_significant:
                    risk_score += 0.30
        
        return min(risk_score, 1.0)
