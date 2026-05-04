"""
Bias Engine Test Vectors
Statistical correctness validation for disparate impact analysis.
These test vectors MUST pass for bias detection to be considered valid.
"""

import pytest
import math
from typing import Dict, List, Tuple
import numpy as np
from scipy import stats


# ============================================
# TEST VECTOR DEFINITIONS
# ============================================

class BiasTestVector:
    """Represents a known bias scenario with expected outcomes."""
    
    def __init__(
        self,
        name: str,
        control_group: Dict[str, int],
        protected_group: Dict[str, int],
        expected_dir: float,
        expected_80_rule_pass: bool,
        expected_statistical_significance: bool,
        description: str
    ):
        self.name = name
        self.control_approvals = control_group["approvals"]
        self.control_total = control_group["total"]
        self.protected_approvals = protected_group["approvals"]
        self.protected_total = protected_group["total"]
        self.expected_dir = expected_dir
        self.expected_80_rule_pass = expected_80_rule_pass
        self.expected_statistical_significance = expected_statistical_significance
        self.description = description


# Test Vector 1: Severe Bias (Fails 80% Rule)
SEVERE_BIAS = BiasTestVector(
    name="severe_bias",
    control_group={"approvals": 800, "total": 1000},  # 80% approval rate
    protected_group={"approvals": 400, "total": 1000},  # 40% approval rate
    expected_dir=0.50,  # 40% / 80% = 0.50
    expected_80_rule_pass=False,  # 0.50 < 0.80
    expected_statistical_significance=True,  # Large sample, clear difference
    description="Clear disparate impact: protected group approval rate is 50% of control rate"
)

# Test Vector 2: Moderate Bias (Marginal Fail)
MODERATE_BIAS = BiasTestVector(
    name="moderate_bias",
    control_group={"approvals": 750, "total": 1000},  # 75% approval rate
    protected_group={"approvals": 550, "total": 1000},  # 55% approval rate
    expected_dir=0.733,  # 55% / 75% = 0.733
    expected_80_rule_pass=False,  # 0.733 < 0.80
    expected_statistical_significance=True,  # Large sample, significant difference
    description="Moderate disparate impact: below 80% threshold but not extreme"
)

# Test Vector 3: Balanced (Passes 80% Rule)
BALANCED = BiasTestVector(
    name="balanced",
    control_group={"approvals": 700, "total": 1000},  # 70% approval rate
    protected_group={"approvals": 665, "total": 1000},  # 66.5% approval rate
    expected_dir=0.950,  # 66.5% / 70% = 0.950
    expected_80_rule_pass=True,  # 0.950 >= 0.80
    expected_statistical_significance=False,  # Difference not statistically significant
    description="Approximately equal treatment: DIR well above 80% threshold"
)

# Test Vector 4: Perfect Equality
PERFECT_EQUALITY = BiasTestVector(
    name="perfect_equality",
    control_group={"approvals": 600, "total": 1000},  # 60% approval rate
    protected_group={"approvals": 600, "total": 1000},  # 60% approval rate
    expected_dir=1.00,  # 60% / 60% = 1.00
    expected_80_rule_pass=True,  # 1.00 >= 0.80
    expected_statistical_significance=False,  # No difference
    description="Perfect parity: identical approval rates"
)

# Test Vector 5: Small Sample (Fisher Exact Required)
SMALL_SAMPLE_BIAS = BiasTestVector(
    name="small_sample_bias",
    control_group={"approvals": 18, "total": 20},  # 90% approval rate
    protected_group={"approvals": 8, "total": 20},  # 40% approval rate
    expected_dir=0.444,  # 40% / 90% = 0.444
    expected_80_rule_pass=False,  # 0.444 < 0.80
    expected_statistical_significance=True,  # Fisher exact should detect this
    description="Small sample with severe bias: requires Fisher exact test"
)

# Test Vector 6: Edge Case - Zero Control Approvals
ZERO_CONTROL_APPROVALS = BiasTestVector(
    name="zero_control_approvals",
    control_group={"approvals": 0, "total": 100},  # 0% approval rate
    protected_group={"approvals": 10, "total": 100},  # 10% approval rate
    expected_dir=float('inf'),  # Division by zero handling
    expected_80_rule_pass=True,  # Protected group has HIGHER rate (reverse discrimination?)
    expected_statistical_significance=True,
    description="Edge case: control group has zero approvals (reverse discrimination detection)"
)

# Test Vector 7: Edge Case - Single Approval in Protected Group
SINGLE_APPROVAL = BiasTestVector(
    name="single_approval",
    control_group={"approvals": 50, "total": 100},  # 50% approval rate
    protected_group={"approvals": 1, "total": 100},  # 1% approval rate
    expected_dir=0.02,  # 1% / 50% = 0.02
    expected_80_rule_pass=False,  # Extreme bias
    expected_statistical_significance=True,
    description="Extreme bias: only 1 approval in protected group"
)


# ============================================
# TEST FUNCTIONS
# ============================================

def compute_disparate_impact_ratio(
    control_approvals: int,
    control_total: int,
    protected_approvals: int,
    protected_total: int
) -> float:
    """
    Compute Disparate Impact Ratio (DIR).
    DIR = (protected approval rate) / (control approval rate)
    DIR >= 0.80 indicates no disparate impact (80% rule)
    """
    control_rate = control_approvals / control_total if control_total > 0 else 0
    protected_rate = protected_approvals / protected_total if protected_total > 0 else 0
    
    if control_rate == 0:
        return float('inf') if protected_rate > 0 else 1.0
    
    return protected_rate / control_rate


def eighty_percent_rule(dir_value: float) -> bool:
    """Check if DIR meets 80% rule threshold."""
    return dir_value >= 0.80


def chi_square_test(
    control_approvals: int,
    control_denials: int,
    protected_approvals: int,
    protected_denials: int
) -> Tuple[float, float, bool]:
    """
    Perform chi-square test for independence.
    Returns: (chi2_statistic, p_value, is_significant_at_0.05)
    """
    # Contingency table:
    #               Approved    Denied
    # Control       c_app       c_den
    # Protected     p_app       p_den
    
    contingency_table = np.array([
        [control_approvals, control_denials],
        [protected_approvals, protected_denials]
    ])
    
    chi2, p_value, dof, expected = stats.chi2_contingency(contingency_table)
    is_significant = p_value < 0.05
    
    return chi2, p_value, is_significant


def fisher_exact_test(
    control_approvals: int,
    control_denials: int,
    protected_approvals: int,
    protected_denials: int
) -> Tuple[float, float, bool]:
    """
    Perform Fisher exact test (better for small samples).
    Returns: (odds_ratio, p_value, is_significant_at_0.05)
    """
    contingency_table = np.array([
        [control_approvals, control_denials],
        [protected_approvals, protected_denials]
    ])
    
    odds_ratio, p_value = stats.fisher_exact(contingency_table)
    is_significant = p_value < 0.05
    
    return odds_ratio, p_value, is_significant


# ============================================
# PYTEST TEST CASES
# ============================================

@pytest.mark.parametrize("test_vector", [
    SEVERE_BIAS,
    MODERATE_BIAS,
    BALANCED,
    PERFECT_EQUALITY,
    SMALL_SAMPLE_BIAS,
    ZERO_CONTROL_APPROVALS,
    SINGLE_APPROVAL
])
def test_disparate_impact_ratio(test_vector: BiasTestVector):
    """Test DIR computation against known test vectors."""
    actual_dir = compute_disparate_impact_ratio(
        test_vector.control_approvals,
        test_vector.control_total,
        test_vector.protected_approvals,
        test_vector.protected_total
    )
    
    if math.isinf(test_vector.expected_dir):
        assert math.isinf(actual_dir), \
            f"{test_vector.name}: Expected DIR {test_vector.expected_dir}, got {actual_dir}"
    else:
        # Allow small floating point tolerance
        assert abs(actual_dir - test_vector.expected_dir) < 0.01, \
            f"{test_vector.name}: Expected DIR {test_vector.expected_dir}, got {actual_dir}"


@pytest.mark.parametrize("test_vector", [
    SEVERE_BIAS,
    MODERATE_BIAS,
    BALANCED,
    PERFECT_EQUALITY,
    SMALL_SAMPLE_BIAS,
    SINGLE_APPROVAL
])
def test_eighty_percent_rule(test_vector: BiasTestVector):
    """Test 80% rule validation against known test vectors."""
    dir_value = compute_disparate_impact_ratio(
        test_vector.control_approvals,
        test_vector.control_total,
        test_vector.protected_approvals,
        test_vector.protected_total
    )
    
    actual_pass = eighty_percent_rule(dir_value)
    
    assert actual_pass == test_vector.expected_80_rule_pass, \
        f"{test_vector.name}: Expected 80% rule pass={test_vector.expected_80_rule_pass}, got {actual_pass}"


@pytest.mark.parametrize("test_vector", [
    SEVERE_BIAS,
    MODERATE_BIAS,
    BALANCED,
    PERFECT_EQUALITY
])
def test_chi_square_significance(test_vector: BiasTestVector):
    """Test chi-square statistical significance against known test vectors."""
    control_denials = test_vector.control_total - test_vector.control_approvals
    protected_denials = test_vector.protected_total - test_vector.protected_approvals
    
    chi2, p_value, is_significant = chi_square_test(
        test_vector.control_approvals,
        control_denials,
        test_vector.protected_approvals,
        protected_denials
    )
    
    assert is_significant == test_vector.expected_statistical_significance, \
        f"{test_vector.name}: Expected significance={test_vector.expected_statistical_significance}, " \
        f"got {is_significant} (p={p_value})"


@pytest.mark.parametrize("test_vector", [SMALL_SAMPLE_BIAS])
def test_fisher_exact_small_sample(test_vector: BiasTestVector):
    """Test Fisher exact test for small samples."""
    control_denials = test_vector.control_total - test_vector.control_approvals
    protected_denials = test_vector.protected_total - test_vector.protected_approvals
    
    odds_ratio, p_value, is_significant = fisher_exact_test(
        test_vector.control_approvals,
        control_denials,
        test_vector.protected_approvals,
        protected_denials
    )
    
    assert is_significant == test_vector.expected_statistical_significance, \
        f"{test_vector.name}: Expected Fisher significance={test_vector.expected_statistical_significance}, " \
        f"got {is_significant} (p={p_value})"


# ============================================
# SUMMARY TEST VECTOR TABLE
# ============================================

def print_test_vector_table():
    """Print summary table of all test vectors for documentation."""
    print("\n" + "="*100)
    print("BIAS ENGINE TEST VECTORS")
    print("="*100)
    print(f"{'Vector Name':<25} {'Control Rate':<15} {'Protected Rate':<15} {'DIR':<10} {'80% Pass':<10} {'Significant':<12}")
    print("-"*100)
    
    for tv in [SEVERE_BIAS, MODERATE_BIAS, BALANCED, PERFECT_EQUALITY, SMALL_SAMPLE_BIAS, SINGLE_APPROVAL]:
        control_rate = tv.control_approvals / tv.control_total
        protected_rate = tv.protected_approvals / tv.protected_total
        
        print(f"{tv.name:<25} {control_rate:<15.2%} {protected_rate:<15.2%} {tv.expected_dir:<10.3f} "
              f"{str(tv.expected_80_rule_pass):<10} {str(tv.expected_statistical_significance):<12}")
    
    print("="*100 + "\n")


if __name__ == "__main__":
    print_test_vector_table()
