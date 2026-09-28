# FSMA 204 Rule Catalog Audit

**Structural status:** PASS

Generated from `services/shared/rules/seeds.py:FSMA_RULE_SEEDS` with `python3 scripts/audit_fsma_rule_catalog.py`.

## Scope

- This is a static structural audit of the built-in seed catalog.
- It does not verify the legal accuracy or completeness of citations.
- It does not compare seeds with rule definitions in a live database.
- It does not verify runtime enforcement mode or deployed behavior.

## Summary

| Measure | Count |
| --- | ---: |
| Total rules | 37 |
| Legal requirement | 28 |
| Operational control | 8 |
| Industry standard | 1 |
| Unclassified citation | 0 |
| Supported evaluator | 37 |

## CTE coverage

| CTE type | Rules |
| --- | ---: |
| cooling | 13 |
| first_land_based_receiving | 11 |
| harvesting | 11 |
| initial_packing | 14 |
| receiving | 14 |
| shipping | 15 |
| transformation | 11 |

## Findings

No structural catalog findings.

## Rules

| # | Title | Severity | CTE types | Evaluator | Citation class | Citation |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | Receiving: TLC Source Reference Required | critical | receiving | multi_field_presence | legal_requirement | 21 CFR §1.1345(a)(7) |
| 2 | Receiving: Immediate Previous Source Required | critical | receiving | multi_field_presence | legal_requirement | 21 CFR §1.1345(a)(4) |
| 3 | Receiving: Reference Document Required | warning | receiving | field_presence | legal_requirement | 21 CFR §1.1345(a)(8) |
| 4 | Receiving: Receive Date Required | critical | receiving | field_presence | legal_requirement | 21 CFR §1.1345(a)(6) |
| 5 | Shipping: Ship-From Location Required | critical | shipping | multi_field_presence | legal_requirement | 21 CFR §1.1340(a)(5) |
| 6 | Shipping: Ship-To Location Required | critical | shipping | multi_field_presence | legal_requirement | 21 CFR §1.1340(a)(4) |
| 7 | Shipping: Ship Date Required | critical | shipping | field_presence | legal_requirement | 21 CFR §1.1340(a)(6) |
| 8 | Shipping: Reference Document Required | warning | shipping | field_presence | legal_requirement | 21 CFR §1.1340(a)(8) |
| 9 | Harvesting: Harvest Date Required | critical | harvesting | field_presence | legal_requirement | 21 CFR §1.1325(a)(1)(vii) |
| 10 | Harvesting: Farm Location Required | critical | harvesting | multi_field_presence | legal_requirement | 21 CFR §1.1325(a)(1)(iv) |
| 11 | Initial Packing: Packing Date Required | critical | initial_packing | field_presence | legal_requirement | 21 CFR §1.1330(a)(15) |
| 12 | Transformation: Transformation Date Required | critical | transformation | field_presence | legal_requirement | 21 CFR §1.1350(a)(2)(iii) |
| 13 | Cooling: Cooling Date Required | critical | cooling | field_presence | legal_requirement | 21 CFR §1.1325(b)(1)(v) |
| 14 | Cooling: Cooling Location Required | critical | cooling | multi_field_presence | legal_requirement | 21 CFR §1.1325(b)(1)(iv) |
| 15 | Cooling: Temperature Reading Required | warning | cooling | multi_field_presence | operational_control | Operational cold-chain check |
| 16 | Cooling: Temperature Within Cold-Chain Window | warning | cooling | numeric_range | operational_control | Operational cold-chain check |
| 17 | Initial Packing: Packing Location Required | critical | initial_packing | multi_field_presence | legal_requirement | 21 CFR §1.1330(a)(14) |
| 18 | Initial Packing: Harvest Location Reference Required | critical | initial_packing | multi_field_presence | legal_requirement | 21 CFR §1.1330(a)(4) |
| 19 | First Land-Based Receiving: Entry Point Required | critical | first_land_based_receiving | multi_field_presence | legal_requirement | 21 CFR §1.1335(e) |
| 20 | First Land-Based Receiving: Source Vessel / Origin Required | critical | first_land_based_receiving | multi_field_presence | operational_control | Operational source-vessel identification (supports 21 CFR §1.1335(d) harvest provenance) |
| 21 | TLC Must Be Present | critical | all | field_presence | operational_control | Operational lot linkage (supports 21 CFR §1.1320; harvesting and cooling precede TLC assignment) |
| 22 | Product Description Required | critical | all | multi_field_presence | legal_requirement | 21 CFR §§1.1325(a)(1)(ii), 1.1325(b)(1)(ii), 1.1330(a)(12), 1.1335(b), 1.1340(a)(3), 1.1345(a)(3), 1.1350(a)(2)(iv) |
| 23 | Quantity and Unit of Measure Required | critical | all | multi_field_presence | legal_requirement | 21 CFR §§1.1325(a)(1)(iii), 1.1325(b)(1)(iii), 1.1330(a)(13), 1.1335(c), 1.1340(a)(2), 1.1345(a)(2), 1.1350(a)(2)(v) |
| 24 | Location Identifier Required | critical | all | multi_field_presence | legal_requirement | 21 CFR §§1.1325(a)(1)(iv), 1.1325(b)(1)(iv), 1.1330(a)(14), 1.1335(e), 1.1340(a)(5), 1.1345(a)(5), 1.1350(a)(2)(ii) |
| 25 | GLN Format Validation | warning | all | gs1_check_digit | industry_standard | GS1 General Specifications (GS1 check digit) |
| 26 | Shipping: TLC Source Reference Required | warning | shipping | multi_field_presence | legal_requirement | 21 CFR §1.1340(a)(7) |
| 27 | Transformation: Input TLCs Required | critical | transformation | multi_field_presence | legal_requirement | 21 CFR §1.1350(a)(1)(i) |
| 28 | Reference Document Required for All CTEs | warning | all | multi_field_presence | legal_requirement | 21 CFR §§1.1325(a)(1)(viii), 1.1325(b)(1)(vii), 1.1330(a)(16), 1.1335(g), 1.1340(a)(8), 1.1345(a)(8), 1.1350(a)(2)(vi) |
| 29 | First Land-Based Receiving: Landing Date Required | critical | first_land_based_receiving | field_presence | legal_requirement | 21 CFR §1.1335(f) |
| 30 | Harvesting: Commodity and Variety Required | critical | harvesting | multi_field_presence | legal_requirement | 21 CFR §1.1325(a)(1)(ii) |
| 31 | Receiving: Receiving Location Required | critical | receiving | multi_field_presence | legal_requirement | 21 CFR §1.1345(a)(5) |
| 32 | Initial Packing: Harvester Business Name Required | warning | initial_packing | multi_field_presence | legal_requirement | 21 CFR §1.1330(a)(7) |
| 33 | Initial Packing: Harvester Phone Required | warning | initial_packing | field_presence | legal_requirement | 21 CFR §1.1330(a)(7) |
| 34 | Temporal Order: CTE Chronology Must Be Causal | critical | shipping, receiving, transformation, initial_packing, cooling | temporal_order | operational_control | Operational integrity control (supports 21 CFR §§1.1325–1.1350 date KDE accuracy) |
| 35 | Identity Consistency: Product Must Not Change for Same TLC | warning | harvesting, cooling, initial_packing, first_land_based_receiving, shipping, receiving | identity_consistency | operational_control | Operational product identity consistency (supports 21 CFR §1.1320 lot linkage) |
| 36 | Mass Balance: Output Cannot Exceed Input for Same TLC | warning | shipping, transformation | mass_balance | operational_control | Operational integrity control (supports 21 CFR §1.1350(a)(1) quantity linkage) |
| 37 | FTL Classification: Product Must Be Classified | critical | all | multi_field_presence | operational_control | Operational FTL classification (supports 21 CFR §1.1300 scope determination) |
