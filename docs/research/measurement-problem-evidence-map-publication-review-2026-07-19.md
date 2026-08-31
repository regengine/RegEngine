# Publication Review: “The Measurement Problem in Food Traceability” Evidence Map

- **Reviewed:** 2026-07-19
- **Status:** Docs-only research review — **not publication-ready**
- **Scope:** Structural audit plus primary-source spot checks of the highest-risk claims. This is not a completed systematic review or a verification of every citation in the supplied evidence map.

## Executive verdict

The evidence map contains a credible core argument: food traceability research documents implementation barriers, information-sharing reluctance, SME constraints, and limited recall-performance studies, while broad cross-firm outcome measurement remains sparse.

The map cannot yet support its strongest public claims. It currently mixes peer-reviewed studies with preprints, working papers, dissertations, and adjacent-domain analogies; assigns exact numerical propositions to sources that do not establish those numbers; and labels research gaps “confirmed” without documenting a reproducible systematic-search protocol.

The safest publishable thesis is:

> Existing studies measure selected traceability processes and localized recall performance, but the reviewed literature does not yet provide a standardized, cross-firm, multi-jurisdiction outcome dataset capable of evaluating traceability-system effectiveness at scale.

Do not publish the broader statement that “nobody can answer whether traceability works” until the search methodology and inclusion criteria are documented.

## Publication blockers

1. **Incorrect source-class claim.** The statement that all sources are peer-reviewed is false as written. The map includes arXiv, SSRN, institutional working papers, and dissertations. Each citation needs an explicit source-status field.
2. **A2’s exact numbers are unsupported.** The proposition cites a roughly 27% formalization yield and roughly 62% pass@k result, but its supporting discussion instead reports constrained extraction precision and recall of 84–97%. Those are different tasks and metrics.
3. **A1 overstates a benchmark as a universal ceiling.** DocILE supports layout- and task-dependent performance limitations; it does not establish a universal 80% operational extraction ceiling.
4. **Cross-domain findings are presented as food-domain evidence.** Healthcare privacy and credit-bureau consolidation are useful analogies, not direct estimates for food traceability.
5. **Absence claims lack a search protocol.** C11, C13, and C15 require databases, search strings, dates, language restrictions, screening counts, inclusion criteria, and a definition of “at scale.”
6. **Citation counts are unstable and unsourced.** Remove them or record the database and retrieval date.
7. **Several 2025–2026 citations remain unverified.** They must not carry a claim until the publication venue, DOI, peer-review status, and relevant result are checked.

## Claim-by-claim publication gate

| Claim | Gate | Finding | Required wording or action |
|---|---|---|---|
| A1 | Revise | DocILE and Kleister support material performance limits, especially across document layouts, but not a universal 80% ceiling. F1 is not equivalent to exact field correctness in production. | Replace “~80% ceiling” with “benchmark performance is task-, metric-, and layout-dependent, with material degradation on unfamiliar formats.” |
| A2 | Block | The cited Zhang and El-Gohary result is 96.9% precision and 94.4% recall for extracting constrained quantitative requirements from one building code. It does not support 27% yield or 62% pass@k. | Delete the exact numbers unless the original experiment producing them is cited. Separate extraction, formalization, and executable-rule validation. |
| A3 | Revise | Seafood-fraud research supports the presence of fraudulent or insufficient documentation and broader mislabeling vulnerabilities. The causal phrase “facilitates food laundering” is stronger than the verified evidence. | Use “documentation irregularities are a recurring mechanism or indicator in reported food-fraud cases.” |
| A4 | Revise | Privacy-preserving prototypes exist, but the Glew source is an arXiv preprint. The adoption-effect gap remains plausible. | Classify technical prototypes separately from peer-reviewed adoption evidence. Say “we found no comparative participation study” only after a documented search. |
| B5 | Revise | SME studies support disproportionate cost, capability, interoperability, and uncertainty barriers. Most do not estimate a formally regressive cost incidence. | Use “SMEs report disproportionate adoption barriers” unless costs are normalized by revenue, margin, or transaction volume. |
| B6 | Conditional support | Direct food-supply-chain studies support reluctance and confidentiality concerns; stronger causal magnitude evidence comes from other industries. | State direction confidently; do not state a quantified deterrent magnitude. |
| B7 | Analogy only | Miller and Tucker directly estimate effects in US hospital EMR adoption, not food traceability. The publisher reports more than a 24% reduction in aggregate adoption and evidence of suppressed network effects. | Label explicitly as a healthcare analogue. Do not transfer the percentage to food supply chains. |
| B8 | Support | Timeliness, record availability, recall scope, and recall cost are established evaluation dimensions. The strongest verified studies remain small or sector-specific. | Retain with scope limitations and distinguish internal traceability from cross-chain traceback. |
| B9 | Support, verify bibliography | The private-standards literature strongly supports retailer influence and exclusion effects. | Retain after validating every bibliography entry and distinguishing conceptual, case-study, and causal evidence. |
| B10 | Analogy only | Credit-bureau research supports network effects, consolidation pressure, and strategic resistance to sharing. It does not prove food-traceability infrastructure is a natural monopoly. | Use “may exhibit natural-monopoly-like economics when fixed costs and returns to coverage dominate.” State the transfer conditions. |
| C11 | Gap hypothesis | Donnelly et al. provide a limited simulated-recall study; Dzwolak measures six small firms. These examples show limited scope, not proof that no scaled study exists. | Define “completion,” “cross-firm,” and “at scale,” then report the systematic-search result as “no eligible study identified.” |
| C12 | Retain revised verdict | Shared technical components and platforms exist, while neutral cross-firm outcome-measurement infrastructure appears fragmented. | Distinguish transaction infrastructure, interoperability standards, commercial networks, and public measurement infrastructure. |
| C13 | Gap hypothesis | The supplied map identifies qualitative and directional evidence but no food-domain causal estimate of deterrent magnitude. | Retain only as a research question until a reproducible search is completed. |
| C14 | Direction supported | The literature supports meaningful SME participation differences and barriers, but the map mixes adoption rates, intention, capability, and statistical significance. | Specify the outcome and population for every quantitative comparison. Do not call p=0.073 significant under a 5% threshold. |
| C15 | Gap hypothesis | Broad system-level outcome evidence appears sparse, but “no outcome data exists at scale” is not established by citation examples alone. It also overlaps substantially with C11. | Define system outcomes beyond traceback completion, document the search, and merge or sharply distinguish C11 and C15. |

## Verified high-risk spot checks

### A1 — DocILE

The [official DocILE repository](https://github.com/rossumai/docile) identifies the work as accepted to ICDAR 2023 and links to an arXiv manuscript. The benchmark contains 6.7k annotated business documents and includes zero- and few-shot layouts. This supports a claim about generalization difficulty, not a universal accuracy ceiling.

**Safe use:** benchmark evidence that document extraction varies by task, metric, and layout familiarity.

### A2 — regulatory extraction

[Zhang and El-Gohary (2016)](https://experts.illinois.edu/en/publications/semantic-nlp-based-information-extraction-from-construction-regul/) report 0.969 precision and 0.944 recall for quantitative requirements extracted from the 2009 International Building Code. This is a constrained extraction task. It neither establishes the evidence map’s 27% figure nor evaluates end-to-end conversion of open-textured food regulation into executable rules.

**Safe use:** evidence that high accuracy is possible for a narrowly defined regulatory extraction task; not evidence of general formalization accuracy.

### A4 — privacy prototype status

[Glew, Tröger, and Schmittner (2022)](https://arxiv.org/abs/2204.00317) describe an EPCIS-based prototype for sanitized and anonymous sharing. The record is an arXiv preprint. It validates a technical design, not adoption or participation effects.

**Safe use:** proof of technical feasibility, explicitly classified as preprint evidence.

### B7 — healthcare analogy

[Miller and Tucker (2009)](https://pubsonline.informs.org/doi/abs/10.1287/mnsc.1090.1014) report that state privacy regulation restricting hospital release of health information reduced aggregate EMR adoption by more than 24%, with evidence pointing to suppressed network externalities.

**Safe use:** a cross-domain mechanism analogue. The percentage must not be described as a food-traceability estimate.

### B8/C11 — measured but limited recall performance

[Dzwolak (2016)](https://onlinelibrary.wiley.com/doi/abs/10.1111/jfs.12232) studies six Polish small food businesses and proposes record-availability and traceability-time indicators. [Donnelly, Karlsen, and Dreyer (2012)](https://www.emerald.com/bfj/article/114/7/1016/18173/A-simulated-recall-study-in-five-major-food) conduct a simulated recall involving 30 products across five sectors in Norway.

**Safe use:** direct evidence that traceability performance has been measured, but in limited samples that do not constitute standardized cross-firm measurement at scale.

### B6 — information-sharing reluctance

[Behnke and Janssen (2020)](https://www.sciencedirect.com/science/article/pii/S0268401219303536) analyze four food-supply-chain cases using 16 interviews and identify 18 boundary conditions for sharing assurance information. The design supports qualitative conclusions about reluctance and enabling conditions, not a causal estimate of participation effects.

**Safe use:** food-domain qualitative support for confidentiality and governance barriers.

### A3 — seafood fraud

[Lawrence et al. (2022)](https://ift.onlinelibrary.wiley.com/doi/10.1111/1541-4337.12998) review reported seafood-fraud incidents across multiple databases. This supports documentation irregularities as part of the fraud landscape, but “food laundering” should be defined and tied to a directly measured mechanism before using causal language.

### B10 — credit-bureau analogy and citation correction

Liberti, Sturgess, and Sutherland’s article was published in the *Journal of Financial Economics* in **2022**, not 2020: [DOI 10.1016/j.jfineco.2021.08.023](https://doi.org/10.1016/j.jfineco.2021.08.023). It studies formation of a voluntary US commercial credit information-sharing system.

**Safe use:** evidence about adoption incentives and network formation in credit markets. Any “natural monopoly” conclusion for food traceability remains an inference requiring explicit transfer conditions.

## Required systematic-search protocol for C11, C13, and C15

Companion artifacts now provide the executable review structure:

- [Systematic review protocol](./measurement-problem-systematic-review-protocol-2026-07-20.md) — preregistration-ready questions, definitions, search strategy, screening, extraction, synthesis, and gap decision rules.
- [Citation ledger](./measurement-problem-citation-ledger.csv) — seeded source-status and claim-support controls for the verified high-risk citations.

The protocol is a plan, not a completed review. The three claims remain gap hypotheses until its searches, screening, and citation chasing are executed.

Before calling the gaps confirmed, append a methods section containing:

- Databases searched, including at minimum Scopus or Web of Science plus domain databases.
- Exact search strings and Boolean operators.
- Search execution date and coverage window.
- Language and publication-type restrictions.
- Definitions of `traceback completion`, `cross-firm`, `participation`, `outcome`, and `at scale`.
- Deduplication and title/abstract/full-text screening counts.
- Inclusion and exclusion criteria.
- A PRISMA-style flow diagram.
- A table of near-miss studies and the reason each was excluded.
- A dated statement: “No eligible study was identified by this protocol,” not “no study exists.”

## Minimum citation ledger

Create one row per source with these fields:

| Field | Purpose |
|---|---|
| Full citation and DOI | Prevent ambiguous author-year references |
| Publication status | Journal, peer-reviewed proceedings, preprint, working paper, dissertation, report |
| Domain and geography | Prevent silent transfer across industries or jurisdictions |
| Study design and sample | Separate reviews, interviews, simulations, observational studies, and experiments |
| Outcome and metric | Prevent mixing F1, exact match, adoption, participation, time, and cost |
| Direct or analogue | Make evidentiary distance visible |
| Result used | Record the exact table, page, or passage supporting the claim |
| Limitation | Preserve scope and avoid universalization |
| Verified by/date | Create an auditable publication trail |

### Unresolved verification queue

The seeded ledger is deliberately not an exhaustive bibliography. The following items remain blocked before manuscript submission:

- Extract exact tables, pages, denominators, and uncertainty measures for every numerical result used from DocILE, Lawrence et al., Miller and Tucker, Dzwolak, Donnelly et al., and Liberti et al.
- Identify the actual source and experimental task for A2's claimed 27% formalization yield and 62% pass@k, or remove both figures.
- Determine whether Glew et al. (2022) has a later peer-reviewed version; until then it remains preprint evidence.
- Verify the publication metadata and relevant result for every supporting citation not yet in the ledger, especially the 2025-2026 records.
- Audit the full B9 private-standards bibliography rather than treating the general strength of that literature as verification of each listed source.
- Reconcile every C14 percentage and significance statement to a named population, outcome, model, table, and threshold.
- Remove or date-stamp all citation counts with the database used; citation counts are not evidence quality measures.
- Execute the companion systematic-review protocol before changing C11, C13, or C15 from hypotheses to evidence findings.

## Recommended paper edits

1. Replace every categorical “ceiling” with a scoped benchmark statement.
2. Remove A2’s 27% and 62% numbers until the originating study is identified.
3. Split sources into direct food evidence, adjacent-domain empirical analogies, theory, and technical prototypes.
4. Rename “gap confirmed” to “no eligible study identified” after completing the search protocol.
5. Merge C11 and C15 unless C15 is explicitly defined as outcomes beyond traceback completion.
6. Remove unsourced citation counts.
7. Add a limitations paragraph stating that the map is not evidence that a shared API will improve participation or outcomes; that remains a testable product and research hypothesis.

## Product boundary

This audit does not justify new production claims for RegEngine and does not change the production spine. Until the evidence ledger and systematic review are complete, use the material for research framing only—not compliance guarantees, efficacy claims, or quantified marketing copy.
