from __future__ import annotations

from typing import List

from app.models import GeneratedControl, GeneratedObligation, GeneratedTest, RegulationMapRequest


def _disparate_impact_controls() -> List[GeneratedControl]:
    return [
        GeneratedControl(
            control_name="Monthly disparate impact testing",
            control_type="statistical_test",
            frequency="monthly",
            threshold_value="DIR >= 0.80",
            tests=[
                GeneratedTest(
                    test_name="Disparate Impact Ratio",
                    methodology="DIR",
                    metric_definition="DIR = protected_group_approval_rate / max_group_approval_rate",
                    failure_threshold="DIR < 0.80",
                )
            ],
        ),
        GeneratedControl(
            control_name="Threshold sensitivity stress test",
            control_type="monitoring",
            frequency="monthly",
            threshold_value="No high-risk DIR degradation at +/- 10% cutoffs",
            tests=[
                GeneratedTest(
                    test_name="Approval threshold sensitivity",
                    methodology="regression",
                    metric_definition="Simulate approval cutoff drift at +/- 5% and +/- 10%",
                    failure_threshold="Any stressed scenario produces DIR < 0.80",
                )
            ],
        ),
    ]


def _documentation_controls() -> List[GeneratedControl]:
    return [
        GeneratedControl(
            control_name="Fair lending validation dossier",
            control_type="documentation",
            frequency="quarterly",
            threshold_value="100% artifact completeness",
            tests=[
                GeneratedTest(
                    test_name="Model validation evidence completeness",
                    methodology="feature_importance",
                    metric_definition="Control evidence contains regulation, methodology, output, sign-off",
                    failure_threshold="Any required evidence field missing",
                )
            ],
        )
    ]


def _drift_controls() -> List[GeneratedControl]:
    return [
        GeneratedControl(
            control_name="Protected class drift monitoring",
            control_type="monitoring",
            frequency="monthly",
            threshold_value="KS statistic <= 0.20",
            tests=[
                GeneratedTest(
                    test_name="Approval distribution drift check",
                    methodology="KS_test",
                    metric_definition="KS test on protected-class approval distributions over time",
                    failure_threshold="KS statistic > 0.20",
                )
            ],
        )
    ]


def generate_obligations(request: RegulationMapRequest) -> List[GeneratedObligation]:
    marker = f"{request.source_name} {request.citation} {request.section} {request.text}".lower()

    obligations: List[GeneratedObligation] = []

    if "ecoa" in marker or "701" in marker:
        obligations.append(
            GeneratedObligation(
                obligation_text="No discriminatory impact in underwriting decisions across protected classes.",
                risk_category="disparate_impact",
                controls=_disparate_impact_controls(),
            )
        )
        obligations.append(
            GeneratedObligation(
                obligation_text="Maintain complete, reviewable documentation supporting fair lending controls.",
                risk_category="documentation",
                controls=_documentation_controls(),
            )
        )

    if "fair housing" in marker or "fha" in marker:
        obligations.append(
            GeneratedObligation(
                obligation_text="Detect and mitigate disparate treatment risk in lending outcomes.",
                risk_category="disparate_treatment",
                controls=[
                    GeneratedControl(
                        control_name="Protected class regression testing",
                        control_type="statistical_test",
                        frequency="monthly",
                        threshold_value="p-value >= 0.05 or mitigation documented",
                        tests=[
                            GeneratedTest(
                                test_name="Logistic regression bias test",
                                methodology="regression",
                                metric_definition="Marginal effect of protected class controlling for score and income proxies",
                                failure_threshold="p-value < 0.05",
                            )
                        ],
                    )
                ],
            )
        )

    if "cfpb" in marker or "interagency" in marker or "examination" in marker:
        obligations.append(
            GeneratedObligation(
                obligation_text="Operate continuous monitoring for fair lending drift and emerging risk.",
                risk_category="disparate_impact",
                controls=_drift_controls(),
            )
        )

    if not obligations:
        obligations = [
            GeneratedObligation(
                obligation_text="Establish defensible fair lending controls tied to explicit regulatory obligations.",
                risk_category="documentation",
                controls=_documentation_controls() + _disparate_impact_controls(),
            )
        ]

    return obligations
