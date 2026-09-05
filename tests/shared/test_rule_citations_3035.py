"""Exact citation mapping checked against the official CFR and FDA CTE guide."""

from shared.rules.seeds import FSMA_RULE_SEEDS

EXPECTED = {
    "Receiving: TLC Source Reference Required": "21 CFR §1.1345(a)(7)",
    "Receiving: Immediate Previous Source Required": "21 CFR §1.1345(a)(4)",
    "Receiving: Reference Document Required": "21 CFR §1.1345(a)(8)",
    "Receiving: Receive Date Required": "21 CFR §1.1345(a)(6)",
    "Shipping: Ship-From Location Required": "21 CFR §1.1340(a)(5)",
    "Shipping: Ship-To Location Required": "21 CFR §1.1340(a)(4)",
    "Shipping: Ship Date Required": "21 CFR §1.1340(a)(6)",
    "Shipping: Reference Document Required": "21 CFR §1.1340(a)(8)",
    "Harvesting: Harvest Date Required": "21 CFR §1.1325(a)(1)(vii)",
    "Harvesting: Farm Location Required": "21 CFR §1.1325(a)(1)(iv)",
    "Initial Packing: Packing Date Required": "21 CFR §1.1330(a)(15)",
    "Transformation: Transformation Date Required": "21 CFR §1.1350(a)(2)(iii)",
    "Cooling: Cooling Date Required": "21 CFR §1.1325(b)(1)(v)",
    "Cooling: Cooling Location Required": "21 CFR §1.1325(b)(1)(iv)",
    "Cooling: Temperature Reading Required": "Operational cold-chain check",
    "Cooling: Temperature Within Cold-Chain Window": "Operational cold-chain check",
    "Initial Packing: Packing Location Required": "21 CFR §1.1330(a)(14)",
    "Initial Packing: Harvest Location Reference Required": "21 CFR §1.1330(a)(4)",
    "First Land-Based Receiving: Entry Point Required": "21 CFR §1.1335(e)",
    "First Land-Based Receiving: Source Vessel / Origin Required": "Operational source-vessel identification "
    "(supports 21 CFR §1.1335(d) harvest provenance)",
    "TLC Must Be Present": "Operational lot linkage (supports 21 CFR §1.1320; harvesting and cooling precede TLC "
    "assignment)",
    "Product Description Required": "21 CFR §§1.1325(a)(1)(ii), 1.1325(b)(1)(ii), 1.1330(a)(12), 1.1335(b), "
    "1.1340(a)(3), 1.1345(a)(3), 1.1350(a)(2)(iv)",
    "Quantity and Unit of Measure Required": "21 CFR §§1.1325(a)(1)(iii), 1.1325(b)(1)(iii), 1.1330(a)(13), "
    "1.1335(c), 1.1340(a)(2), 1.1345(a)(2), 1.1350(a)(2)(v)",
    "Location Identifier Required": "21 CFR §§1.1325(a)(1)(iv), 1.1325(b)(1)(iv), 1.1330(a)(14), 1.1335(e), "
    "1.1340(a)(5), 1.1345(a)(5), 1.1350(a)(2)(ii)",
    "GLN Format Validation": "GS1 General Specifications (GS1 check digit)",
    "Shipping: TLC Source Reference Required": "21 CFR §1.1340(a)(7)",
    "Transformation: Input TLCs Required": "21 CFR §1.1350(a)(1)(i)",
    "Reference Document Required for All CTEs": "21 CFR §§1.1325(a)(1)(viii), 1.1325(b)(1)(vii), 1.1330(a)(16), "
    "1.1335(g), 1.1340(a)(8), 1.1345(a)(8), 1.1350(a)(2)(vi)",
    "First Land-Based Receiving: Landing Date Required": "21 CFR §1.1335(f)",
    "Harvesting: Commodity and Variety Required": "21 CFR §1.1325(a)(1)(ii)",
    "Receiving: Receiving Location Required": "21 CFR §1.1345(a)(5)",
    "Initial Packing: Harvester Business Name Required": "21 CFR §1.1330(a)(7)",
    "Initial Packing: Harvester Phone Required": "21 CFR §1.1330(a)(7)",
    "Temporal Order: CTE Chronology Must Be Causal": "Operational integrity control (supports 21 CFR §§1.1325–1.1350 "
    "date KDE accuracy)",
    "Identity Consistency: Product Must Not Change for Same TLC": "Operational product identity consistency "
    "(supports 21 CFR §1.1320 lot linkage)",
    "Mass Balance: Output Cannot Exceed Input for Same TLC": "Operational integrity control (supports 21 CFR "
    "§1.1350(a)(1) quantity linkage)",
    "FTL Classification: Product Must Be Classified": "Operational FTL classification (supports 21 CFR §1.1300 scope "
    "determination)",
}


def test_every_seed_cites_its_actual_requirement():
    assert {r["title"]: r["citation_reference"] for r in FSMA_RULE_SEEDS} == EXPECTED
