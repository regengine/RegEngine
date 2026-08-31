# Systematic Review Protocol: Outcome Measurement in Food Traceability

- **Protocol version:** 0.1
- **Prepared:** 2026-07-20
- **Status:** Draft for preregistration; searches have not been executed
- **Scope:** Docs-only research. This protocol does not establish a RegEngine product, compliance, or efficacy claim.

## Purpose

This protocol converts claims C11, C13, and C15 in the evidence map for “The Measurement Problem in Food Traceability” from asserted literature gaps into falsifiable review questions. It is designed for reporting under [PRISMA 2020](https://www.prisma-statement.org/prisma-2020), search reporting under [PRISMA-S](https://www.prisma-statement.org/prisma-search), and preregistration using the [OSF Generalized Systematic Review](https://help.osf.io/article/330-welcome-to-registrations) template.

The review must be preregistered before the final systematic searches are executed. Limited pilot searches may be used to validate retrieval of the seed set; their dates, strings, and revisions must be disclosed in the registration. Any change after preregistration must be dated, justified, and retained in a deviation log.

## Review questions

### RQ1 — operational traceback performance (C11)

What peer-reviewed food-domain studies measure cross-firm traceback completion or time-to-trace, and which of those measurements were conducted at scale?

### RQ2 — competitive-sensitivity deterrence (C13)

What peer-reviewed food-domain studies quantify the effect of competitive or commercial sensitivity on an organization’s participation in, or disclosure to, a traceability information-sharing system?

### RQ3 — system effectiveness outcomes (C15)

What peer-reviewed food-domain studies measure standardized cross-firm outcomes of traceability-system effectiveness at scale, beyond adoption, intention, or technical transaction performance?

RQ1 is a focused operational-performance question. RQ3 is broader and covers downstream effects such as recall precision, recall scope, mass balance, cost, detection, waste, and public-health outcomes. A study may answer both questions, but the claims must not be merged during extraction.

## Operational definitions

| Term | Prespecified definition |
|---|---|
| Food traceability | The ability to follow the movement, transformation, or custody of food, feed, ingredients, or their traceable resource units through specified supply-chain stages. |
| Cross-firm | A trace or evaluation crosses at least two independent legal entities. Departments or sites within one legal entity are not cross-firm. |
| Traceback completion | The proportion of eligible trace requests or traceable resource units that reach the study’s prespecified origin or destination endpoint with the required identity and linkage data. |
| Time-to-trace | Elapsed time from a defined trace request to the prespecified completion endpoint. Retrieval time for one firm’s internal records is recorded separately. |
| Competitive sensitivity | Concern that shared supplier, customer, price, volume, process, sourcing, or market-position information could create commercial disadvantage. General privacy concerns are not sufficient unless the commercial mechanism is measured. |
| Quantified deterrent | An effect estimate tied to participation or disclosure, such as a risk difference, odds ratio, marginal effect, elasticity, standardized coefficient, or experimental difference. A rank-only barrier list or qualitative theme does not qualify. |
| Participation | Joining, remaining in, contributing required data to, or completing required exchanges through a cross-firm traceability system. Adoption intention is not realized participation. |
| Traceability effectiveness outcome | Completion, accuracy, time, mass balance or recovery, recall precision or scope, recall cost, detection, waste, or public-health effect. Adoption, intention, user satisfaction, blockchain throughput, and database latency alone are not effectiveness outcomes. |
| Standardized outcome | The outcome definition, denominator, start event, endpoint, and calculation are stated and applied consistently across evaluated entities or events. |

### “At scale” classification

The review will report results in three tiers rather than treating scale as an unstated judgment:

1. **Cross-firm:** at least two independent legal entities.
2. **Multi-firm:** at least 10 independent legal entities or 100 trace/recall observations.
3. **At scale:** either (a) at least 100 independent legal entities, or (b) at least 1,000 trace/recall observations spanning at least two food sectors or two regulatory jurisdictions.

A nationwide or multi-jurisdiction administrative dataset can qualify as “at scale” when it has a defined sampling frame and meets the event threshold, even if entity identities are masked. Studies below the threshold remain eligible and will be reported as near-scale or small-sample evidence; they cannot independently support an at-scale claim.

The scale thresholds are methodological choices, not facts from the literature. They must be approved before preregistration. Sensitivity analyses will repeat the classification at 50 entities/500 events and 250 entities/2,500 events.

## Eligibility criteria

### Common inclusion criteria

- Study concerns food, feed, agricultural ingredients destined for food, or a defined food supply chain.
- Study reports original empirical evidence or a systematic evidence synthesis that exposes extractable primary-study details.
- Full text is available in English or can be translated with a documented method.
- Publication is a peer-reviewed journal article or peer-reviewed conference paper.
- Publication date is database inception through the final search date.

### Question-specific inclusion criteria

| Question | Required population/system | Required exposure or intervention | Required outcome |
|---|---|---|---|
| RQ1/C11 | At least two independent food-chain entities | Actual trace, simulated recall, mock recall, or standardized trace exercise | Traceback completion and/or time-to-trace with a defined denominator or endpoint |
| RQ2/C13 | Food-chain organizations facing a cross-firm data-sharing decision | Measured competitive/commercial sensitivity, confidentiality condition, disclosure rule, or privacy-preserving treatment | Quantitative participation or disclosure effect estimate |
| RQ3/C15 | Cross-firm food-traceability system or regulatory program | System use, implementation, mandate, or controlled comparison | At least one standardized effectiveness outcome, excluding adoption/intention and technical performance alone |

### Exclusion criteria

- One-firm internal traceability with no cross-firm endpoint, except as a named near-miss.
- Purely conceptual, normative, legal, architecture, simulation, or prototype papers without observed food-chain outcomes.
- Consumer-facing provenance or willingness-to-pay studies without an organizational traceability outcome.
- Food quality, fraud, or recall studies that do not evaluate traceability performance.
- Vendor case studies without sufficient methods, denominators, and independently inspectable results.
- Preprints, dissertations, working papers, reports, and trade publications from the primary peer-reviewed synthesis.
- Adjacent-domain studies such as healthcare or credit reporting from the direct evidence synthesis.

Non-peer-reviewed and adjacent-domain sources may be retained in separate appendices as context or mechanism analogues. They must never be counted as direct peer-reviewed food-domain evidence.

## Information sources

Search the following databases from inception through the execution date:

- Scopus.
- Web of Science Core Collection.
- CAB Abstracts.
- FSTA: Food Science and Technology Abstracts.
- AGRICOLA.
- ABI/INFORM Collection or Business Source Complete.
- PubMed/MEDLINE.

Use OpenAlex and Crossref only for metadata reconciliation and citation discovery. Search relevant references and forward citations for every included study and every high-relevance near-miss. Search registries and grey literature separately to identify publication bias and ongoing work, but do not use grey literature to satisfy a peer-reviewed evidence claim.

The final report must name the vendor/platform, database segment, coverage dates, and search execution date. “Google Scholar was searched” is not sufficient as the primary method.

## Search strategy

The following are syntax-neutral master strings. The reviewer must adapt field codes, proximity operators, phrase rules, and wildcards to each database without changing the concepts. Every executed string must be copied verbatim into an appendix and exported with its result count.

### RQ1/C11 master string

```text
("food traceab*" OR "food supply chain traceab*" OR "agri-food traceab*"
 OR "seafood traceab*" OR "produce traceab*" OR "meat traceab*")
AND
(traceback OR "trace back" OR "trace-back" OR recall OR "mock recall"
 OR "simulated recall" OR "trace exercise")
AND
(completion OR success OR effectiveness OR performance OR "time to trace"
 OR "traceability time" OR timeliness OR origin)
```

### RQ2/C13 master string

```text
("food supply chain" OR "food traceab*" OR "agri-food" OR seafood
 OR produce OR "food industry")
AND
("information sharing" OR "data sharing" OR disclosure OR participation
 OR "supply chain transparency")
AND
(confidential* OR proprietary OR "competitive sensitivity"
 OR "commercial sensitivity" OR competition OR "competitive advantage")
AND
(effect OR magnitude OR estimate OR adoption OR participation OR experiment
 OR causal OR regression OR survey OR "willingness to share")
```

### RQ3/C15 master string

```text
("food traceab*" OR "traceability system*" OR "food recall system*"
 OR "agri-food traceab*")
AND
(effectiveness OR outcome* OR performance OR evaluation OR impact)
AND
("cross-firm" OR interorgani?ational OR "supply chain" OR network
 OR "multi-firm" OR "multi company")
AND
(recall OR traceback OR accuracy OR completion OR timeliness OR cost
 OR "mass balance" OR recovery OR detection OR waste OR illness)
```

### Search controls

- Run a pilot against the seed set before freezing the strings. A search that does not retrieve Donnelly et al. (2012), Dzwolak (2016), and Behnke and Janssen (2020) where relevant must be diagnosed and revised before preregistration.
- Record all pilot revisions; do not silently tune the search after seeing substantive results.
- Do not use citation counts as eligibility or quality criteria.
- Update the searches within 90 days before manuscript submission.
- Archive native exports, RIS/BibTeX files, exact queries, and result counts in a dated review directory.

## Study selection

1. Import all records into one review library and retain database/source identifiers.
2. Deduplicate by DOI, then normalized title/author/year, with manual resolution of conflicts.
3. Two reviewers independently screen titles/abstracts and then full texts.
4. Resolve disagreements by discussion; use a named third adjudicator if agreement cannot be reached.
5. Record one primary exclusion reason for every excluded full text.
6. Conduct backward and forward citation chasing after initial inclusion decisions, then screen those records under the same criteria.
7. Report identification, deduplication, screening, exclusion, and inclusion counts in a PRISMA 2020 flow diagram.

If two independent reviewers are not available, a second reviewer must blind-screen a random 20% sample at both stages. Report agreement and treat the remaining single-reviewer process as a limitation; do not describe it as a fully independent dual review.

## Data extraction

Use one row per study and a child row for each distinct outcome. Extract:

- Full citation, DOI, publication status, funding, and conflicts of interest.
- Country, jurisdiction, food sector, supply-chain stages, and study dates.
- Study design, sampling frame, recruitment method, and sample size.
- Count of independent legal entities, trace events, recalls, products, and sectors.
- Actual incident, administrative observation, simulated recall, mock exercise, survey, experiment, or case study.
- System boundary, trace request start, completion endpoint, denominator, and time unit.
- Outcome definition, measurement method, missingness, estimate, uncertainty interval, and adjusted covariates.
- Competitive-sensitivity construct, comparator, participation/disclosure endpoint, and effect measure for RQ2.
- Scale tier and sensitivity-analysis tier.
- Direct food evidence, grey literature, or adjacent-domain analogue.
- Exact page, table, figure, or supplement supporting every result used in the manuscript.
- Reviewer, verification date, limitations, and unresolved questions.

The companion citation ledger is the bibliographic control layer; the final extraction sheet will add outcome-level child rows after screening.

## Quality and risk-of-bias assessment

Select the appraisal tool by study design before extraction begins and document that decision. Do not collapse reporting quality, risk of bias, and evidence relevance into one score. At minimum assess:

- Selection and nonresponse bias.
- Whether the denominator and endpoint were prespecified and consistently applied.
- Missing traces, attrition, and excluded firms or events.
- Measurement validity and independence of outcome verification.
- Confounding and comparator validity for observational estimates.
- Clustering by firm, chain, sector, or jurisdiction.
- Selective reporting and sponsor/vendor influence.
- External validity across food sectors, firm sizes, and jurisdictions.

No study is excluded solely for low quality. Low-quality studies remain visible and are excluded from stronger causal or prevalence conclusions during synthesis.

## Synthesis plan

- Present direct food evidence separately from adjacent-domain analogues and technical prototypes.
- Tabulate results by question, design, food sector, jurisdiction, outcome, and scale tier.
- Do not pool completion percentages whose start event, endpoint, denominator, or chain boundary differs.
- Conduct meta-analysis only when at least three studies use materially compatible definitions and designs. Use random-effects models and report heterogeneity; otherwise use structured narrative synthesis.
- Treat actual incidents, administrative records, and simulated exercises as separate strata.
- For RQ2, distinguish participation effects from disclosure-volume or disclosure-content effects.
- For RQ3, distinguish operational performance from downstream economic and public-health effects.
- Run the prespecified scale-threshold sensitivity analyses.

## Gap decision rules

The manuscript may use **“no eligible study was identified”** only when all of the following are true:

1. All required databases and citation-chasing steps were completed and reported.
2. The search was updated within 90 days of submission.
3. Screening and full-text exclusion decisions are auditable.
4. No direct food-domain study meets the question-specific criteria and prespecified scale tier.

If one or more eligible studies exist but are small, heterogeneous, low quality, or geographically narrow, the conclusion must be **“evidence is sparse and not yet generalizable at scale.”** Never use “no evidence exists” or “gap confirmed.” Adjacent-domain analogies cannot close or prove a direct food-domain gap.

Question-specific decisions:

- **C11 supported:** no eligible at-scale study measures cross-firm traceback completion or time-to-trace.
- **C13 supported:** no eligible food-domain study estimates a competitive-sensitivity effect on participation or disclosure using a stated quantitative effect measure.
- **C15 supported:** no eligible at-scale study reports a standardized cross-firm effectiveness outcome beyond adoption, intention, or technical performance.

## Seed studies for search validation

These are candidate records, not automatically included studies:

- Donnelly, Karlsen, and Dreyer (2012), “A simulated recall study in five major food sectors,” DOI `10.1108/00070701211241590`.
- Dzwolak (2016), “Practical Aspects of Traceability in Small Food Businesses with Implemented Food Safety Management Systems,” DOI `10.1111/jfs.12232`.
- Behnke and Janssen (2020), “Boundary conditions for traceability in food supply chains using blockchain technology,” DOI `10.1016/j.ijinfomgt.2019.05.025`.
- Curto and Gaspar (2021), “Traceability in food supply chains: Review and SME focused analysis—Part 1,” DOI `10.3934/agrfood.2021041`.
- Lawrence et al. (2022), “The 11 sins of seafood: Assessing a decade of food fraud reports in the global supply chain,” DOI `10.1111/1541-4337.12998`.

## Required review artifacts

- Preregistered protocol URL and immutable registration date.
- Per-database exact search strings, execution dates, and result counts.
- Raw and deduplicated citation exports.
- Title/abstract and full-text screening decisions.
- Full-text exclusion table with one primary reason per record.
- Citation ledger and outcome-level extraction sheet.
- Risk-of-bias assessments.
- PRISMA 2020 flow diagram and PRISMA-S checklist.
- Search and protocol deviation log.
- Reproducible synthesis code or formulas, if quantitative synthesis is performed.

## Registration fields still requiring named owners

- Review authors and institutional affiliations.
- Two screeners and conflict adjudicator.
- Database access owner.
- Translation process for non-English records, or a justified language restriction.
- Statistical reviewer if meta-analysis becomes eligible.
- Public repository location and data-retention policy.
