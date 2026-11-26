# Final omission-aware prompt evaluation

Acceptance: **PASS**. The final candidate scored **34/34 regression** and **16/16 fresh held-out** cases. The combined reference scored **33/34 regression** and **16/16 held-out**; HS04 was its only mismatch. No verdict regressions, false decisive answers, missed true conflicts, or harness errors were observed for the candidate.

## Implementation

Only the polarity instructions change. All combined criteria, both other questions, the classifier, validator, model pin, and thresholds remain unchanged. The extra instructions distinguish omission from contradiction, necessary conditions from sufficient ones, and applicable exhaustive accounts from partial excerpts. No runtime application integration is included.

HS04 selected `partial_scope_only` at probability 0.67, yielding insufficient. B08 selected `affirms_hypothesis` at probability 0.76, yielding supported. HS04 reaches the existing `polarity_uncertain` branch because 0.67 is below 0.70; this is a correct abstention, not a high-confidence partial-support classification. The resolver uses selected-choice probability, not the separate confidence field.

## Frozen evaluation

The candidate was frozen before an independent author created the 16 fresh HV cases. The author saw no prompts, existing cases, or results. The lead accepted all gold labels without edits after reviewing the frozen cases. All 34 previously exposed cases are regression evidence; none is counted as fresh. Each case ran against both variants, with alternating variant order and held-out cases before regression cases.

The 100 live requests all returned HTTP 200 and validated. No retries or unknown-usage attempts occurred. All 100 classifications replay identically offline.

| Dataset | Case | Expected | Combined | Omission-aware |
|---|---|---|---|---|
| heldout | HV01 | supported | supported | supported |
| heldout | HV02 | supported | supported | supported |
| heldout | HV03 | supported | supported | supported |
| heldout | HV04 | supported | supported | supported |
| heldout | HV05 | contradicted | contradicted | contradicted |
| heldout | HV06 | contradicted | contradicted | contradicted |
| heldout | HV07 | contradicted | contradicted | contradicted |
| heldout | HV08 | contradicted | contradicted | contradicted |
| heldout | HV09 | insufficient | insufficient | insufficient |
| heldout | HV10 | insufficient | insufficient | insufficient |
| heldout | HV11 | insufficient | insufficient | insufficient |
| heldout | HV12 | insufficient | insufficient | insufficient |
| heldout | HV13 | conflicting | conflicting | conflicting |
| heldout | HV14 | conflicting | conflicting | conflicting |
| heldout | HV15 | conflicting | conflicting | conflicting |
| heldout | HV16 | conflicting | conflicting | conflicting |
| regression | B02 | contradicted | contradicted | contradicted |
| regression | B08 | supported | supported | supported |
| regression | HC01 | supported | supported | supported |
| regression | HC02 | conflicting | conflicting | conflicting |
| regression | HC03 | contradicted | contradicted | contradicted |
| regression | HC04 | insufficient | insufficient | insufficient |
| regression | HC05 | conflicting | conflicting | conflicting |
| regression | HC06 | supported | supported | supported |
| regression | HC07 | contradicted | contradicted | contradicted |
| regression | HC08 | insufficient | insufficient | insufficient |
| regression | HP01 | supported | supported | supported |
| regression | HP02 | contradicted | contradicted | contradicted |
| regression | HP03 | insufficient | insufficient | insufficient |
| regression | HP04 | supported | supported | supported |
| regression | HP05 | contradicted | contradicted | contradicted |
| regression | HP06 | insufficient | insufficient | insufficient |
| regression | HP07 | supported | supported | supported |
| regression | HP08 | contradicted | contradicted | contradicted |
| regression | HP09 | insufficient | insufficient | insufficient |
| regression | HP10 | supported | supported | supported |
| regression | HP11 | contradicted | contradicted | contradicted |
| regression | HP12 | insufficient | insufficient | insufficient |
| regression | HP13 | conflicting | conflicting | conflicting |
| regression | HP14 | conflicting | conflicting | conflicting |
| regression | HP15 | conflicting | conflicting | conflicting |
| regression | HP16 | conflicting | conflicting | conflicting |
| regression | HS01 | supported | supported | supported |
| regression | HS02 | insufficient | insufficient | insufficient |
| regression | HS03 | supported | supported | supported |
| regression | HS04 | insufficient | contradicted | insufficient |
| regression | HS05 | contradicted | contradicted | contradicted |
| regression | HS06 | contradicted | contradicted | contradicted |
| regression | HS07 | conflicting | conflicting | conflicting |
| regression | HS08 | conflicting | conflicting | conflicting |

## Rejected candidate retained

The first revision was evaluated in 68 requests. Both variants matched all 16 fresh cases. The candidate fixed HS04 but regressed B08(selected affirmation 0.65 < threshold 0.70); both scored17/18 on regression cases with different failures. Its acceptance test failed and it was not promoted. The successful revision restores all original criteria and appends neutral wording. The observed regression does not establish which wording change caused it.

## Usage-derived Jev cost

| Batch | Requests | Input tokens | Output tokens | Cost USD |
|---|---:|---:|---:|---:|
| Original evaluation | 16 | 18,496 | 2,592 | $0.000776832 |
| Earlier four-variant comparison | 72 | 70,832 | 8,196 | $0.002974944 |
| Rejected first omission revision | 68 | 73,470 | 7,720 | $0.003085740 |
| Final append-only revision | 100 | 105,100 | 11,354 | $0.004414200 |
| **Total** | **256** | **267,898** | **29,862** | **$0.011251716** |

**Remaining original $1 cap: $0.988748284.** The current user request required 168 requests across the failed and successful iterations, costing $0.007499940 combined. All attempts are retained in the two ledgers.

Cost equals returned input tokens × $0.042 per million; output is free at the [published Jev price](https://docs.typesafe.ai/models), checked 2026-10-29. Invoice/account debit was not independently verified. These figures cover Jev evaluations, not other coding-assistant usage.

## Verification and limitations

- All 80 offline tests pass, including 34 original-response preservation tests,34 candidate regression tests,100-response replay, fresh-case acceptance, malformed-response negative paths, true-conflict precedence, and6 mocked runner safeguards.
- Strict TypeScript compilation passes. All 100 requests and 100 responses pass the saved TypeSafe OpenAPI schema.
- Both frozen case sets, prompt hashes, core hashes, request hashes, queue identity, classifications, usage, and integer-nano-USD cost accounting reconcile.
- All 521 preexisting output artifact hashes remain unchanged. Failed revision fixtures are retained separately.
- Sixteen fresh synthetic cases include related designs; one response per case and variant does not establish repeatability, independent production accuracy, or calibration. Both prompts scored 16/16 on fresh cases, so no fresh-set accuracy superiority is claimed.
- Scope is standalone Mode B evidence classification. No public API, database, authorization, billing, deployment, or production decision logic changed.
