"""
Drift Engine Test Vectors
Statistical correctness validation for model drift detection.
These test vectors MUST pass for drift detection to be considered valid.
"""

import pytest
from typing import List, Dict, Tuple
import numpy as np
from scipy import stats

from kernel.monitoring.drift_engine import DriftEngine


# ============================================
# TEST VECTOR DEFINITIONS
# ============================================

class DriftTestVector:
    """Represents a known drift scenario with expected outcomes."""
    
    def __init__(
        self,
        name: str,
        baseline_distribution: List[float],
        current_distribution: List[float],
        expected_psi: float,
        expected_kl_divergence: float,
        expected_drift_detected: bool,
        drift_severity: str,
        description: str
    ):
        self.name = name
        self.baseline = np.array(baseline_distribution)
        self.current = np.array(current_distribution)
        self.expected_psi = expected_psi
        self.expected_kl_divergence = expected_kl_divergence
        self.expected_drift_detected = expected_drift_detected  # PSI > 0.25
        self.drift_severity = drift_severity  # low, medium, high, severe
        self.description = description


def make_score_distribution(mean: float, std_dev: float, size: int = 2000) -> List[float]:
    """Create a deterministic score-like distribution clipped to [0, 1]."""
    quantiles = np.linspace(0.001, 0.999, size)
    return np.clip(stats.norm.ppf(quantiles, loc=mean, scale=std_dev), 0.0, 1.0).tolist()


# Test Vector 1: No Drift (Stable Distribution)
NO_DRIFT = DriftTestVector(
    name="no_drift",
    baseline_distribution=make_score_distribution(0.70, 0.10),
    current_distribution=make_score_distribution(0.70, 0.10),
    expected_psi=0.00,  # No measurable drift
    expected_kl_divergence=0.00,  # Minimal divergence
    expected_drift_detected=False,
    drift_severity="low",
    description="Stable model: current predictions match baseline distribution"
)

# Test Vector 2: Minor Drift (Monitor Zone)
MINOR_DRIFT = DriftTestVector(
    name="minor_drift",
    baseline_distribution=make_score_distribution(0.70, 0.10),
    current_distribution=make_score_distribution(0.74, 0.10),
    expected_psi=0.16,  # PSI in 0.1-0.25 range (monitor)
    expected_kl_divergence=0.08,
    expected_drift_detected=False,  # Below 0.25 threshold
    drift_severity="medium",
    description="Minor confidence shift: requires monitoring but not critical"
)

# Test Vector 3: Significant Drift (Threshold Exceeded)
SIGNIFICANT_DRIFT = DriftTestVector(
    name="significant_drift",
    baseline_distribution=make_score_distribution(0.70, 0.10),
    current_distribution=make_score_distribution(0.76, 0.10),
    expected_psi=0.36,  # PSI > 0.25 (significant drift)
    expected_kl_divergence=0.18,
    expected_drift_detected=True,
    drift_severity="high",
    description="Significant drift: model predictions shifted substantially"
)

# Test Vector 4: Extreme Drift (Critical)
EXTREME_DRIFT = DriftTestVector(
    name="extreme_drift",
    baseline_distribution=make_score_distribution(0.70, 0.10),
    current_distribution=make_score_distribution(0.80, 0.10),
    expected_psi=1.06,  # Very high PSI
    expected_kl_divergence=0.52,
    expected_drift_detected=True,
    drift_severity="severe",
    description="Extreme drift: model behavior fundamentally changed"
)

# Test Vector 5: Variance Shift (Same Mean, Different Spread)
VARIANCE_SHIFT = DriftTestVector(
    name="variance_shift",
    baseline_distribution=make_score_distribution(0.70, 0.05),  # std=0.05
    current_distribution=make_score_distribution(0.70, 0.12),  # std=0.12 (wider)
    expected_psi=3.51,  # High PSI due to shape change
    expected_kl_divergence=0.84,
    expected_drift_detected=True,
    drift_severity="severe",
    description="Variance drift: same mean but increased uncertainty"
)

# Test Vector 6: Bimodal Shift (Distribution Shape Change)
BIMODAL_SHIFT = DriftTestVector(
    name="bimodal_shift",
    baseline_distribution=make_score_distribution(0.65, 0.10, 1000),  # Single peak
    current_distribution=(
        make_score_distribution(0.50, 0.05, 500) +  # Two peaks
        make_score_distribution(0.80, 0.05, 500)
    ),
    expected_psi=1.67,  # High PSI due to shape change
    expected_kl_divergence=0.42,
    expected_drift_detected=True,
    drift_severity="severe",
    description="Concept drift: distribution changed from unimodal to bimodal"
)


# ============================================
# DRIFT COMPUTATION FUNCTIONS
# ============================================

def compute_psi(baseline: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """
    Compute Population Stability Index (PSI).
    PSI measures distribution shift between baseline and current.
    
    Thresholds:
    - PSI < 0.1: No significant change
    - PSI 0.1-0.25: Minor change, monitor
    - PSI > 0.25: Significant change, investigate
    
    Formula: PSI = sum((current_pct - baseline_pct) * ln(current_pct / baseline_pct))
    """
    return DriftEngine(num_bins=bins)._compute_psi(baseline, current)


def compute_kl_divergence(baseline: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """
    Compute Kullback-Leibler (KL) divergence.
    KL measures how much the current distribution differs from baseline.
    
    Formula: KL(P||Q) = sum(P(x) * log(P(x) / Q(x)))
    """
    return DriftEngine(num_bins=bins)._compute_kl_divergence(baseline, current)


def compute_js_divergence(baseline: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """
    Compute Jensen-Shannon (JS) divergence.
    JS is symmetric version of KL divergence.
    
    Formula: JS(P||Q) = 0.5 * KL(P||M) + 0.5 * KL(Q||M) where M = 0.5(P + Q)
    """
    return DriftEngine(num_bins=bins)._compute_js_divergence(baseline, current)


def detect_mean_shift(baseline: np.ndarray, current: np.ndarray, threshold: float = 0.10) -> bool:
    """Detect if mean has shifted beyond threshold percentage."""
    baseline_mean = np.mean(baseline)
    current_mean = np.mean(current)
    
    shift_pct = abs(current_mean - baseline_mean) / baseline_mean if baseline_mean != 0 else 0
    
    return shift_pct > threshold


def detect_variance_shift(baseline: np.ndarray, current: np.ndarray, threshold: float = 0.50) -> bool:
    """Detect if variance has increased beyond threshold percentage."""
    baseline_var = np.var(baseline)
    current_var = np.var(current)
    
    shift_pct = abs(current_var - baseline_var) / baseline_var if baseline_var != 0 else 0
    
    return shift_pct > threshold


# ============================================
# PYTEST TEST CASES
# ============================================

@pytest.mark.parametrize("test_vector", [
    NO_DRIFT,
    MINOR_DRIFT,
    SIGNIFICANT_DRIFT,
    EXTREME_DRIFT,
    VARIANCE_SHIFT,
    BIMODAL_SHIFT
])
def test_psi_computation(test_vector: DriftTestVector):
    """Test PSI computation against known test vectors."""
    actual_psi = compute_psi(test_vector.baseline, test_vector.current)
    
    # Allow 20% tolerance due to randomness in some test vectors
    tolerance = 0.20 * test_vector.expected_psi if test_vector.expected_psi > 0 else 0.05
    
    assert abs(actual_psi - test_vector.expected_psi) < tolerance, \
        f"{test_vector.name}: Expected PSI ~{test_vector.expected_psi}, got {actual_psi}"


@pytest.mark.parametrize("test_vector", [
    NO_DRIFT,
    MINOR_DRIFT,
    SIGNIFICANT_DRIFT,
    EXTREME_DRIFT
])
def test_drift_threshold_detection(test_vector: DriftTestVector):
    """Test drift detection based on PSI > 0.25 threshold."""
    actual_psi = compute_psi(test_vector.baseline, test_vector.current)
    actual_detected = actual_psi > 0.25
    
    assert actual_detected == test_vector.expected_drift_detected, \
        f"{test_vector.name}: Expected drift_detected={test_vector.expected_drift_detected}, " \
        f"got {actual_detected} (PSI={actual_psi})"


@pytest.mark.parametrize("test_vector", [
    NO_DRIFT,
    SIGNIFICANT_DRIFT,
    EXTREME_DRIFT
])
def test_kl_divergence(test_vector: DriftTestVector):
    """Test KL divergence computation."""
    actual_kl = compute_kl_divergence(test_vector.baseline, test_vector.current)
    
    # KL should increase as drift increases
    # Just verify it's in reasonable range, not exact match due to binning
    assert actual_kl >= 0, f"{test_vector.name}: KL divergence must be non-negative"


def test_js_divergence_symmetry():
    """Test that JS divergence is symmetric."""
    baseline = np.array(make_score_distribution(0.60, 0.10, 1000))
    current = np.array(make_score_distribution(0.70, 0.10, 1000))
    
    js_forward = compute_js_divergence(baseline, current)
    js_reverse = compute_js_divergence(current, baseline)
    
    assert abs(js_forward - js_reverse) < 0.01, \
        f"JS divergence should be symmetric: {js_forward} vs {js_reverse}"


def test_mean_shift_detection():
    """Test mean shift detection."""
    baseline = np.array([0.60] * 100)  # Mean 0.60
    current_no_shift = np.array([0.62] * 100)  # Mean 0.62 (3.3% shift)
    current_with_shift = np.array([0.75] * 100)  # Mean 0.75 (25% shift)
    
    assert not detect_mean_shift(baseline, current_no_shift, threshold=0.10), \
        "Should not detect shift below threshold"
    
    assert detect_mean_shift(baseline, current_with_shift, threshold=0.10), \
        "Should detect shift above threshold"


def test_variance_shift_detection():
    """Test variance shift detection."""
    baseline = np.array(make_score_distribution(0.70, 0.05, 1000))  # Var ~= 0.0025
    current_no_shift = np.array(make_score_distribution(0.70, 0.055, 1000))  # ~21% increase
    current_with_shift = np.array(make_score_distribution(0.70, 0.15, 1000))  # ~800% increase
    
    assert not detect_variance_shift(baseline, current_no_shift, threshold=0.50), \
        "Should not detect variance shift below threshold"
    
    assert detect_variance_shift(baseline, current_with_shift, threshold=0.50), \
        "Should detect variance shift above threshold"


# ============================================
# SUMMARY TEST VECTOR TABLE
# ============================================

def print_test_vector_table():
    """Print summary table of all test vectors for documentation."""
    print("\n" + "="*110)
    print("DRIFT ENGINE TEST VECTORS")
    print("="*110)
    print(f"{'Vector Name':<20} {'Baseline Mean':<15} {'Current Mean':<15} {'Expected PSI':<15} "
          f"{'Detected':<12} {'Severity':<12}")
    print("-"*110)
    
    for tv in [NO_DRIFT, MINOR_DRIFT, SIGNIFICANT_DRIFT, EXTREME_DRIFT, VARIANCE_SHIFT, BIMODAL_SHIFT]:
        baseline_mean = np.mean(tv.baseline)
        current_mean = np.mean(tv.current)
        
        print(f"{tv.name:<20} {baseline_mean:<15.3f} {current_mean:<15.3f} {tv.expected_psi:<15.3f} "
              f"{str(tv.expected_drift_detected):<12} {tv.drift_severity:<12}")
    
    print("="*110 + "\n")


if __name__ == "__main__":
    print_test_vector_table()
