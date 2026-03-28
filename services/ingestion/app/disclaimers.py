"""Standardized disclaimer constants for demo/sample/synthetic data.

Any module that returns data that may not be derived from actual tenant
traceability records should use these constants so the messaging is
consistent across FDA exports, recall reports, EPCIS documents, and
simulation endpoints.
"""

DEMO_DATA_DISCLAIMER = (
    "\u26a0 DEMO/SAMPLE DATA: This output contains illustrative or sample data "
    "that is NOT derived from your tenant\u2019s actual traceability records. "
    "Scores, findings, and recommendations are representative examples only. "
    "Complete your onboarding to see production data."
)

SIMULATION_DISCLAIMER = (
    "\u26a0 SYNTHETIC METRICS: Simulation metrics are based on illustrative "
    "scenarios, not your tenant\u2019s actual supply chain data. "
    "Use for training and demonstration purposes only."
)

SAMPLE_EXPORT_DISCLAIMER = (
    "This export contains illustrative sample data, not actual tenant "
    "traceability records. Do not submit to FDA or trading partners."
)
