"""
Drift Engine
============
Statistical drift detection for model performance monitoring.

Implements:
- Population Stability Index (PSI)
- Kullback-Leibler (KL) divergence
- Jensen-Shannon (JS) divergence
- Mean and variance shift detection

Based on test vectors from services/analytics/tests/test_drift_vectors.py
"""

import numpy as np
from typing import Dict, List, Any, Optional
from scipy.stats import entropy
from scipy.spatial.distance import jensenshannon
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class DriftSeverity(str, Enum):
    """Drift severity levels based on PSI thresholds."""
    NONE = "none"           # PSI < 0.10
    MINOR = "minor"         # 0.10 <= PSI < 0.25
    MODERATE = "moderate"   # 0.25 <= PSI < 0.50
    SEVERE = "severe"       # PSI >= 0.50


class DriftMetrics(BaseModel):
    """Statistical drift metrics."""
    psi: float = Field(..., description="Population Stability Index")
    kl_divergence: float = Field(..., description="Kullback-Leibler divergence")
    js_divergence: float = Field(..., description="Jensen-Shannon divergence")
    
    mean_shift: float = Field(..., description="Absolute difference in means")
    mean_shift_percent: float = Field(..., description="Percentage change in mean")
    
    variance_shift: float = Field(..., description="Absolute difference in variances")
    variance_shift_percent: float = Field(..., description="Percentage change in variance")


class DriftEvent(BaseModel):
    """Drift detection event."""
    event_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_id: str
    feature_name: str
    
    # Reference period (baseline)
    reference_start: Optional[str] = None
    reference_end: Optional[str] = None
    reference_sample_size: int
    
    # Current period (comparison)
    current_start: Optional[str] = None
    current_end: Optional[str] = None
    current_sample_size: int
    
    # Metrics
    metrics: DriftMetrics
    
    # Severity assessment
    severity: DriftSeverity
    alert_triggered: bool = Field(..., description="Whether drift exceeds alert threshold")
    
    # Recommendations
    recommended_actions: List[str] = Field(default_factory=list)


class DriftReport(BaseModel):
    """Complete drift monitoring report."""
    report_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_id: str
    
    # Analysis period
    reference_period: str
    current_period: str
    
    # Drift events
    drift_events: List[DriftEvent]
    
    # Overall assessment
    total_features_monitored: int
    features_with_drift: int
    features_with_severe_drift: int
    
    # Risk score
    drift_risk_score: float = Field(..., ge=0.0, le=1.0, description="0=stable, 1=severe drift")


class DriftEngine:
    """
    Drift detection engine.
    
    PSI Thresholds (industry standard):
    - PSI < 0.10: No significant drift
    - 0.10 <= PSI < 0.25: Minor drift - monitor
    - 0.25 <= PSI < 0.50: Moderate drift - investigate
    - PSI >= 0.50: Severe drift - action required
    
    KL Divergence:
    - Measures how one distribution differs from reference
    - Always >= 0 (0 = identical distributions)
    - Not symmetric
    
    JS Divergence:
    - Symmetric version of KL divergence
    - Bound: 0 <= JS <= 1 (for probability distributions)
    """
    
    def __init__(
        self,
        psi_alert_threshold: float = 0.25,
        num_bins: int = 10
    ):
        """
        Initialize drift engine.
        
        Args:
            psi_alert_threshold: PSI value that triggers alert (default 0.25)
            num_bins: Number of bins for discretizing continuous features (default 10)
        """
        self.psi_alert_threshold = psi_alert_threshold
        self.num_bins = num_bins
    
    def detect_drift(
        self,
        model_id: str,
        feature_name: str,
        reference_data: np.ndarray,
        current_data: np.ndarray
    ) -> DriftEvent:
        """
        Detect drift for a single feature.
        
        Args:
            model_id: Model identifier
            feature_name: Name of feature being monitored
            reference_data: Reference/baseline data
            current_data: Current/comparison data
        
        Returns:
            DriftEvent with metrics and severity
        """
        # Compute PSI
        psi = self._compute_psi(reference_data, current_data)
        
        # Compute KL and JS divergence
        kl_div = self._compute_kl_divergence(reference_data, current_data)
        js_div = self._compute_js_divergence(reference_data, current_data)
        
        # Compute mean and variance shifts
        mean_shift = abs(np.mean(current_data) - np.mean(reference_data))
        ref_mean = np.mean(reference_data)
        mean_shift_percent = (mean_shift / abs(ref_mean) * 100) if ref_mean != 0 else 0
        
        var_shift = abs(np.var(current_data) - np.var(reference_data))
        ref_var = np.var(reference_data)
        var_shift_percent = (var_shift / abs(ref_var) * 100) if ref_var != 0 else 0
        
        # Create metrics
        metrics = DriftMetrics(
            psi=psi,
            kl_divergence=kl_div,
            js_divergence=js_div,
            mean_shift=mean_shift,
            mean_shift_percent=mean_shift_percent,
            variance_shift=var_shift,
            variance_shift_percent=var_shift_percent
        )
        
        # Determine severity
        severity = self._determine_severity(psi)
        alert_triggered = psi >= self.psi_alert_threshold
        
        # Generate recommendations
        recommendations = self._generate_recommendations(severity, metrics)
        
        return DriftEvent(
            event_id=f"drift_{model_id}_{feature_name}_{datetime.utcnow().isoformat()}",
            model_id=model_id,
            feature_name=feature_name,
            reference_sample_size=len(reference_data),
            current_sample_size=len(current_data),
            metrics=metrics,
            severity=severity,
            alert_triggered=alert_triggered,
            recommended_actions=recommendations
        )
    
    def monitor_model_drift(
        self,
        model_id: str,
        reference_features: Dict[str, np.ndarray],
        current_features: Dict[str, np.ndarray]
    ) -> DriftReport:
        """
        Monitor drift across all model features.
        
        Args:
            model_id: Model identifier
            reference_features: Dict of feature_name -> reference data
            current_features: Dict of feature_name -> current data
        
        Returns:
            DriftReport with all drift events
        """
        drift_events = []
        
        for feature_name in reference_features.keys():
            if feature_name not in current_features:
                continue
            
            drift_event = self.detect_drift(
                model_id=model_id,
                feature_name=feature_name,
                reference_data=reference_features[feature_name],
                current_data=current_features[feature_name]
            )
            
            drift_events.append(drift_event)
        
        # Overall assessment
        features_with_drift = sum(
            1 for event in drift_events
            if event.severity != DriftSeverity.NONE
        )
        
        features_with_severe_drift = sum(
            1 for event in drift_events
            if event.severity == DriftSeverity.SEVERE
        )
        
        # Compute drift risk score
        drift_risk_score = self._compute_drift_risk_score(drift_events)
        
        return DriftReport(
            report_id=f"drift_report_{model_id}_{datetime.utcnow().isoformat()}",
            model_id=model_id,
            reference_period="baseline",
            current_period="current",
            drift_events=drift_events,
            total_features_monitored=len(drift_events),
            features_with_drift=features_with_drift,
            features_with_severe_drift=features_with_severe_drift,
            drift_risk_score=drift_risk_score
        )
    
    def _compute_psi(
        self,
        reference_data: np.ndarray,
        current_data: np.ndarray
    ) -> float:
        """
        Compute Population Stability Index (PSI).
        
        PSI = Σ (current% - reference%) * ln(current% / reference%)
        
        where the sum is over bins.
        """
        # Create bins from reference data
        _, bin_edges = np.histogram(reference_data, bins=self.num_bins)
        
        # Compute distributions
        ref_counts, _ = np.histogram(reference_data, bins=bin_edges)
        curr_counts, _ = np.histogram(current_data, bins=bin_edges)
        
        # Convert to percentages (add small epsilon to avoid division by zero)
        epsilon = 1e-10
        ref_percents = (ref_counts + epsilon) / (len(reference_data) + epsilon * self.num_bins)
        curr_percents = (curr_counts + epsilon) / (len(current_data) + epsilon * self.num_bins)
        
        # Compute PSI
        psi = np.sum((curr_percents - ref_percents) * np.log(curr_percents / ref_percents))
        
        return float(psi)
    
    def _compute_kl_divergence(
        self,
        reference_data: np.ndarray,
        current_data: np.ndarray
    ) -> float:
        """
        Compute Kullback-Leibler divergence.
        
        KL(P || Q) = Σ P(i) * log(P(i) / Q(i))
        
        Measures how current distribution diverges from reference.
        """
        # Create bins and compute distributions
        _, bin_edges = np.histogram(reference_data, bins=self.num_bins)
        
        ref_counts, _ = np.histogram(reference_data, bins=bin_edges)
        curr_counts, _ = np.histogram(current_data, bins=bin_edges)
        
        # Convert to probabilities
        epsilon = 1e-10
        ref_probs = (ref_counts + epsilon) / (len(reference_data) + epsilon * self.num_bins)
        curr_probs = (curr_counts + epsilon) / (len(current_data) + epsilon * self.num_bins)
        
        # Compute KL divergence using scipy
        kl_div = entropy(curr_probs, ref_probs)
        
        return float(kl_div)
    
    def _compute_js_divergence(
        self,
        reference_data: np.ndarray,
        current_data: np.ndarray
    ) -> float:
        """
        Compute Jensen-Shannon divergence.
        
        JS(P || Q) = 0.5 * KL(P || M) + 0.5 * KL(Q || M)
        where M = 0.5 * (P + Q)
        
        Symmetric version of KL divergence, bounded [0, 1].
        """
        # Create bins and compute distributions
        _, bin_edges = np.histogram(reference_data, bins=self.num_bins)
        
        ref_counts, _ = np.histogram(reference_data, bins=bin_edges)
        curr_counts, _ = np.histogram(current_data, bins=bin_edges)
        
        # Convert to probabilities
        epsilon = 1e-10
        ref_probs = (ref_counts + epsilon) / (len(reference_data) + epsilon * self.num_bins)
        curr_probs = (curr_counts + epsilon) / (len(current_data) + epsilon * self.num_bins)
        
        # Compute JS divergence using scipy
        js_div = jensenshannon(ref_probs, curr_probs)
        
        return float(js_div)
    
    def _determine_severity(self, psi: float) -> DriftSeverity:
        """
        Determine drift severity based on PSI.
        
        Thresholds:
        - PSI < 0.10: None
        - 0.10 <= PSI < 0.25: Minor
        - 0.25 <= PSI < 0.50: Moderate
        - PSI >= 0.50: Severe
        """
        if psi < 0.10:
            return DriftSeverity.NONE
        elif psi < 0.25:
            return DriftSeverity.MINOR
        elif psi < 0.50:
            return DriftSeverity.MODERATE
        else:
            return DriftSeverity.SEVERE
    
    def _generate_recommendations(
        self,
        severity: DriftSeverity,
        metrics: DriftMetrics
    ) -> List[str]:
        """Generate recommended actions based on drift severity."""
        recommendations = []
        
        if severity == DriftSeverity.NONE:
            recommendations.append("No action required - distribution is stable")
        
        elif severity == DriftSeverity.MINOR:
            recommendations.append("Continue monitoring - minor drift detected")
            recommendations.append("Review recent data patterns for anomalies")
        
        elif severity == DriftSeverity.MODERATE:
            recommendations.append("Investigate root cause of drift")
            recommendations.append("Consider retraining model with recent data")
            recommendations.append("Review data quality and feature engineering")
        
        elif severity == DriftSeverity.SEVERE:
            recommendations.append("URGENT: Severe drift detected")
            recommendations.append("Retrain model immediately with current data")
            recommendations.append("Review model assumptions and feature definitions")
            recommendations.append("Consider implementing champion/challenger testing")
        
        # Additional recommendations based on specific metrics
        if metrics.mean_shift_percent > 20:
            recommendations.append(f"Mean shifted by {metrics.mean_shift_percent:.1f}% - review data distribution")
        
        if metrics.variance_shift_percent > 50:
            recommendations.append(f"Variance shifted by {metrics.variance_shift_percent:.1f}% - check for outliers")
        
        return recommendations
    
    def _compute_drift_risk_score(self, drift_events: List[DriftEvent]) -> float:
        """
        Compute overall drift risk score.
        
        Score formula:
        - Average PSI across all features
        - Weight severe drift more heavily
        - Cap at 1.0
        """
        if not drift_events:
            return 0.0
        
        # Weighted average PSI
        total_psi = 0.0
        total_weight = 0.0
        
        for event in drift_events:
            # Weight by severity
            if event.severity == DriftSeverity.SEVERE:
                weight = 3.0
            elif event.severity == DriftSeverity.MODERATE:
                weight = 2.0
            elif event.severity == DriftSeverity.MINOR:
                weight = 1.0
            else:
                weight = 0.5
            
            total_psi += event.metrics.psi * weight
            total_weight += weight
        
        avg_psi = total_psi / total_weight if total_weight > 0 else 0.0
        
        # Normalize to [0, 1] range (PSI > 1.0 maps to 1.0)
        risk_score = min(avg_psi, 1.0)
        
        return risk_score
