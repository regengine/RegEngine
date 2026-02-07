# RegEngine White Paper Style and Layout Specification (v1.0)

This guide defines the formatting standards for all RegEngine white papers. Use this spec to ensure consistency across verticals and maintain executive-credible presentation quality.

---

## A. Output Formats (Choose One Per Run)

Your AI should support two output modes:

1. **Markdown for docs + web** (default)
2. **Google Docs / Word layout instructions** (when requested)

If the user does not specify, output in **Markdown**.

---

## B. Document Skeleton (Required)

Always generate this structure in this order:

1. Cover block (title, subtitle, date, version, scope, audience)
2. Table of contents (10-12 major sections max)
3. Executive summary (TL;DR bullets + "why now")
4. Market overview (regulatory environment + industry challenges)
5. Compliance challenges (3-6 named pain points)
6. Solution architecture (diagram + trust model + proof example)
7. Feature sections (3-6 features, each with "what it does / why it matters / audit impact")
8. Competitive analysis (landscape + comparison table + differentiation)
9. Business case & ROI (cost table + revenue acceleration model + assumptions)
10. Implementation methodology (phases + timeline + deliverables)
11. Customer success story (profile, timeline, results table, quotes labeled "name changed" if needed)
12. Conclusion & next steps (decision framework + CTAs)
13. About + legal disclaimer + document control

---

## C. Heading and Typography Rules

In Markdown:

* Use **exact heading levels**:

  * H1 (`#`) only for major numbered sections (1, 2, 3…)
  * H2 (`##`) for subsections
  * H3 (`###`) for sub-subsections

* Use numbered H1 titles like:
  `# 4. Solution Architecture`

* Use consistent capitalization:

  * Titles: Title Case
  * Subheads: Sentence case or Title Case, but be consistent.

---

## D. Table Rules

* Every table must include a header row.
* Align numbers to the right with consistent units:

  * Currency: `$1.05M`, `$450K`, `$500K ARR`
  * Time: `7,000 hrs/year`, `3-6 months`
* If the table is central to the argument, add a 1-2 sentence interpretation immediately after.

---

## E. Callout Rules

Use callouts sparingly (max 1 per major section). Format in Markdown as blockquotes:

* `> **Critical Insight:** ...`
* `> **Key Clarification:** ...`
* `> **Decision Note:** ...`

---

## F. Credibility Rules (Critical for Trust)

Your AI must enforce these:

1. **No absolute superiority claims without qualifiers.**
   - Avoid: "the only platform", "auditors can mathematically trust" (unless fully supported).
   - Prefer: "differentiated by…", "to our knowledge…", "as of Jan 2026…"

2. **Every external statistic must carry a citation marker** in the text, even if you don't list sources yet:
   - Example: "SEC fines totaled $4.2B in 2023 [1]."
   - Add a **Sources** section if citations are available. If not available, include:
     "Source needed: add citation for [1]."

3. **Every ROI model must list assumptions.**
   - If assumptions are missing, the AI must create them explicitly and label them as assumptions.

4. **Distinguish between "audit savings" and "revenue acceleration."**
   - The executive summary must include both but clearly label which is primary.

---

## G. Voice and Tone Rules

* **Audience:** CFO, CISO, Head of Internal Audit, VP Sales, procurement stakeholders.
* **Tone:** executive-credible, technical where needed, not hypey.
* **Style:**

  * Short paragraphs (2-4 sentences)
  * Bullets when listing process steps
  * Avoid jargon dumps; define acronyms on first use: "Sarbanes-Oxley Act (SOX)"

---

## H. Diagram Rules

* If the output is Markdown only, diagrams can be ASCII inside triple backticks.
* If producing a PDF/Word-ready version, diagrams should be specified as:

  * "Figure 1: Architecture diagram" + a short caption.
* All diagrams must include:

  * Inputs (systems)
  * Core platform layer
  * Outputs (auditors/procurement/SEC)

---

## I. Content Hygiene Rules

Before final output, the AI must:

* Remove website navigation/footer junk unless explicitly requested.
* Remove conflicting product claims (e.g., FSMA 204 copy inside a SOX finance white paper).
* Fix obvious typos (e.g., "priduct" -> "product").
* Ensure "name changed" appears anywhere you present quotes from a case study.

---

## J. Required Ending Blocks

Always end with:

* **Legal Disclaimer**
* **Document Control** (version, publication date, next review)
* **CTA** (Demo, ROI assessment, Pilot) - keep it short, no website nav.

---

## K. Example Structure Template

```markdown
# [Vertical] RegEngine for [Industry] Compliance

## Competitive Positioning White Paper

**[Specific Regulation Focus]**

**Publication Date:** [Month Year]
**Document Version:** [X.X]
**Industry Focus:** [Industry Name]
**Regulatory Scope:** [Comma-separated regulations]

---

## Table of Contents

1. Executive Summary
2. Market Overview
3. The Compliance Challenge
[etc...]

---

# 1. Executive Summary

## TL;DR for Decision-Makers

* **Problem:** [quantified pain]
* **Solution:** [core differentiator]
* **Impact:** [primary + secondary value]
* **ROI:** [percentage + timeframe]

[Continue following skeleton...]
```

---

## L. Quality Validation Checklist

Before publishing, verify:

* [ ] Cover block includes all required metadata
* [ ] TOC matches H1 headings exactly
* [ ] All numbers have units and ideally citation markers
* [ ] No absolute claims without qualifiers
* [ ] ROI section includes explicit assumptions
* [ ] Tables are clean and interpretable
* [ ] Diagram includes input → platform → output
* [ ] Case study quotes labeled "name changed" if anonymized
* [ ] Legal disclaimer present
* [ ] Document control block present
* [ ] No conflicting vertical content
* [ ] Consistent terminology throughout

---

## M. Version Control

**Guide Version:** 1.0
**Last Updated:** January 2026
**Next Review:** July 2026
**Maintained by:** RegEngine Marketing & Product Teams
