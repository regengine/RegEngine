# Customer hypotheses and competing design tournament

Scope: FSMA supplier-record intake, diagnosis, persistence and export; no new product surface is proposed for implementation.
Status: source inspection and a design comparison, not a usability study. No customers were contacted, observed or invented.
Archetypes and predicted behavior below are **L0 hypotheses**; implementation observations and selection reasoning are **L1**.
Willingness to pay, conversion, task times, mobile usability, repeat use and customer preference are **UNKNOWN**.
Existing component tests do not establish customer comprehension, deployed behavior or a working database-to-export workflow.

## Inspected surfaces and constraints

- [CSV upload](../../../frontend/src/app/ingest/page.tsx), `IngestPage`: File Upload uses a CSV response and displays accepted/rejected counts; the default tab and page title still emphasize document URLs.
- [Data Import Hub](../../../frontend/src/app/tools/data-import/components/DataImportClient.tsx), `DataImportClient`: defaults to CSV, accepts files up to 5 MB, and also exposes IoT/API tabs and a lead gate.
- [Inflow](../../../frontend/src/app/tools/inflow-lab/components/InflowLabClient.tsx): has Data feeder, Fix queue, Scenarios, Lineage and Diagnostics; `saveFeederRun` distinguishes local save from unavailable backend save.
- Inflow's `prepareExport` selects Test previews and its export links use mock service paths; a preview is not evidence of canonical FDA export completion.
- [Supplier portal](../../../frontend/src/app/portal/[portalId]/page.tsx), `PortalSubmissionPage`: link-based shipment form, preflight before submission, explicit accepted-state handling and another-submission reset.
- [Proof page](../../../frontend/src/app/proof/page.tsx): downloadable artifacts; revised bundle wording distinguishes internal consistency from issuer authenticity and source accuracy.
- [Dashboard](../../../frontend/src/app/dashboard/page.tsx): role-dependent actions span imports, scores, alerts, suppliers, products and recall readiness.
- [CSV component tests](../../../frontend/src/__tests__/pages/ingest-csv.test.tsx) exercise response states with mocked requests; [Inflow tests](../../../frontend/src/__tests__/pages/inflow-lab.test.tsx) include sandbox/save boundaries. These tests were inspected, not rerun in this lane.
- [Canonical description](../../PRODUCT_DESCRIPTION.md) keeps the ERP as the inventory/order system of record; this tournament does not replace it.
- [First-pilot playbook](../../runbooks/first_pilot_session.md), pre-call step 1, excludes spreadsheet-only prospects from the live pilot. That selection rule cannot validate the CSV-first customer hypothesis.

## Customer simulation: three explicit hypotheses

**A. QA / traceability operator — L0, not an interviewed person.**
Job: assemble one requested lot's records, identify omissions, and hand off a usable artifact without becoming an API integrator.
Candidate current alternatives: ERP report plus spreadsheet cleanup, supplier email requests, or an implementation consultant; actual use is UNKNOWN.
Switching trigger / aha: their own file produces understandable row outcomes and a correction that changes the usable export, not just a higher score.
Adoption blockers: no supplier authority, uncertain file permission, new account/key setup, or inability to reconcile source and output counts.
Distrust / abandonment: synthetic data mistaken for their records, an unexplained green score, hidden partial acceptance, or a document-URL workflow before CSV.
Repeat / recommendation: the next supplier file needs less cleanup and a colleague can reproduce the handoff; both mechanisms remain unobserved.
Buyer and willingness to pay: QA may use it while operations/compliance controls budget; both authority and WTP are UNKNOWN.

**B. ERP integrator / implementation engineer — L0, not an interviewed person.**
Job: map a source event once, replay safely, and explain every accepted, rejected or duplicate outcome to the operational owner.
Candidate alternatives: existing ERP/EDI exports, a custom mapping script, or a managed integration; actual vendor/workflow is UNKNOWN.
Switching trigger / aha: a documented request produces a reconciled event and repeat submission has an explicit, safe result.
Adoption blockers: tenant/key provisioning, field semantics, source-change handling, or unclear responsibility between RegEngine and the ERP.
Distrust / abandonment: schema examples diverge from runtime, UI success differs from persistence, or a sample package cannot be verified.
Repeat / recommendation: a second feed reuses the mapping and support knowledge; recommendation requires the next implementation to save measured time.
Buyer and willingness to pay: may recommend a vendor or bill implementation labor without owning the subscription budget; WTP is UNKNOWN.

**C. Supplier shipping clerk / coordinator — L0, not an interviewed person.**
Job: satisfy a buyer's shipment-data request while continuing their normal shipping work, possibly from a phone.
Candidate alternatives: send an existing shipping document, email a spreadsheet, use the buyer's portal, or ask another employee; actual practice is UNKNOWN.
Switching trigger / aha: a familiar shipment entry is accepted with a recoverable receipt and no duplicate transcription for that buyer.
Adoption blockers: unknown lot/source fields, expired links, unclear recipient, weak connectivity, or a second buyer requiring the same work again.
Distrust / abandonment: a link with unexplained destination, retained data they cannot correct, or generic errors that require a manager to resolve.
Repeat / recommendation: the next shipment is easier and the buyer accepts the output; a supplier submitting data is not automatically a paying customer.
Buyer and willingness to pay: the requesting buyer is a plausible payer, not an established one; supplier and buyer WTP are UNKNOWN.

## Tournament: inspect now, compare with people next

Common task: account for a permitted file's rows, identify a planted defect, correct/reject it explicitly, and explain the resulting artifact's limits.
Criteria: comprehension, setup friction, useful-output time, recovery, trust accuracy, repeatability and operator minutes; no invented numerical scores.
An attractive screen cannot compensate for an unexplained missing row, unauthorized disclosure, or a false persistence/proof claim.

| Candidate | Plausible advantage; strongest counterargument | Falsifiable comparison / disposition |
| --- | --- | --- |
| Minimalist CSV, outcome first | Reuses an operator's file and the existing upload/result path; manual mapping may erase the benefit. | Can cohort A explain partial acceptance and retrieve reconciled output with fewer setup steps than its current method? **First candidate to test**, not a proved winner. |
| Technical / API first | Makes payloads and retry behavior inspectable for cohort B; forces cohort A to acquire integration skills. | Can an integrator repeat the same event safely and explain all outcomes without founder debugging? **Qualified runner-up** for API-capable prospects. |
| Trust / provenance first | Shows source, limits and verification before a commitment; hash vocabulary may obscure the actual task. | After inspection, can the participant distinguish source truth, persistence and file consistency without claiming issuer authentication? **Required disclosure layer**, not a new onboarding branch. |
| Mobile first | May fit cohort C's point of work; typing lot/location details and reading errors may cost more than sending a document. | Compare the existing portal on the participant's phone and desktop using the same shipment; record transcription errors, recovery and interruption. **Defer investment** until this cohort is observed. |
| Consumer / gamified | A checklist may clarify progress; points/streaks can reward activity or conceal incomplete records. | Do neutral steps improve completion without increasing false confidence compared with scores/rewards? **Do not build rewards** without task evidence; current readiness scores are not validated gamification. |
| Enterprise broad dashboard | May coordinate several suppliers and roles; many choices can delay the first useful artifact. | Can an operator with a real multi-supplier task act faster than through the focused import/fix flow? **Defer expansion**; retain existing navigation as comparison. |
| Data first | Row-level accounting may make defects and discrepancies inspectable; a large table can overwhelm a nontechnical operator. | Can users locate the seeded wrong/missing row and explain totals without reading every field? **Test within CSV results**, not as another analytics product. |
| Experiment first | Inflow offers samples, diagnosis and replay before persistence; samples can be mistaken for customer success. | Can participants identify what was only simulated, what was saved locally, and what reached canonical storage? **Use for diagnosis**, not as the activation metric. |

Selection reasoning (**L1**): start an operator session on existing `/ingest` File Upload with the task explicitly stated; it already has an upload/row-result path and targeted tests.
Use Inflow Data feeder only when diagnosing a defect; do not assume its preview or saved run completes production evidence handoff.
The CSV-default Data Import Hub is a legitimate challenger; its lead gate and extra intake choices must be measured, not assumed harmless.
Keep trust limits visible in every candidate. The API path is preferable when a prospect already has an integrator and repeatable feed; do not force that cohort through manual CSV.
This selects an initial experiment, not a UI redesign, universal onboarding choice, or readiness declaration. Export compatibility findings in [security](security.md) and [QA](qa.md) remain separate technical gates.

## Smallest real-session measurement

Question / hypothesis: can an operator obtain and correctly explain a reconciled outcome with less total work through the existing CSV path than through their current method?
Information value: high for choosing CSV versus API onboarding and identifying paid delivery labor; expected numerical value is UNKNOWN.
Cost / time / dependencies: one authorized participant, a consented sanitized file with known row counts, an isolated working environment, and 45–60 minutes plus setup; no paid research tool required.
Method: observe the current method first, then the candidate with a comparable task; reverse order on a later participant to expose learning effects. Do not compare different cohorts as if assignment were randomized.
Capture: setup steps, first useful diagnosis/output time, accepted/rejected/duplicate/unaccounted rows, retries, correction minutes, waiting time, facilitator minutes and mistaken beliefs about persistence/proof.
Ask the participant to explain the outcome in their own words and retrieve it again; record observed actions separately from stated preferences.
Success rule, proposed not benchmarked: every row accounted for, correct explanation of persistence and verification limits, and no unauthorized data exposure; compare labor with the actual alternative without inventing a target improvement.
Failure / stopping: stop the sensitive-data exercise on an isolation failure; silent omissions or false evidence claims block that workflow. Explicit valid rejection is not failure; assistance falsifies unassisted completion only and remains cost data for managed delivery.
Repeat trigger: at the next authorized shipment/file, observe whether the participant reuses the workflow and whether setup/correction work falls. Accepting another meeting is not repeat product use.
Payment question: obtain a separately defined offer and budget-owner commitment through the authorized commercial lane; satisfaction or form completion does not resolve WTP.
Result: **NOT RUN**. Confidence update: none; customer behavior remains L0. Next action: one cohort-A observation, followed by the integrator comparison only if qualification supports it.

## Extraordinary success, and its failure mechanism

**L0 scenario:** a buyer adopts the small CSV-to-reconciled-output workflow, asks several suppliers to use it, and introduces another buyer because less correction work is required.
The mechanism is a buyer's distribution authority plus reusable mapping/operational knowledge, not proven virality or an assumed data-network moat.
It fails if each buyer requires different fields, suppliers must re-enter the same shipment, saved mappings drift, or invitations create support work without funded accounts.
It also fails if the growing history exceeds supported export scope, consent does not permit reuse, or an incumbent reproduces the outcome inside the ERP.
Falsifier: in an authorized follow-on, track invited-to-completed suppliers, second-file labor, rejected mappings and paid buyer commitments separately; repeat the existing economics model with observed support inputs.
Do not add cross-tenant sharing, a marketplace, incentives, or a new mobile application to manufacture this mechanism before evidence exists.

Files changed: this document only. Tests run: none; source/test inspection only. Passed: cited surfaces and existing test cases located.
Not tested: rendering, accessibility, actual mobile behavior, user comprehension, production workflow, payment or repeat use.
Remaining risks: sampling bias toward API-capable contacts, assistance hidden as product value, and synthetic success mistaken for customer evidence.
Recommended next step: resolve the scoped artifact-contract blocker, then measure one real CSV outcome before funding any redesign.
