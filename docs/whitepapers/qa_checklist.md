# RegEngine White Paper QA Checklist

Use this checklist before publishing any RegEngine white paper. All items must pass before release.

---

## 1. Structural Integrity

### Cover Block
- [ ] Title follows format: "[Vertical] RegEngine for [Industry] Compliance"
- [ ] Subtitle clearly states value proposition
- [ ] Publication date is present and accurate (Month Year)
- [ ] Document version number included (X.X format)
- [ ] Industry focus explicitly stated
- [ ] Regulatory scope lists all relevant regulations

### Table of Contents
- [ ] TOC includes all 12+ major sections
- [ ] TOC entries match H1 headings exactly
- [ ] No orphaned or missing sections
- [ ] Section numbers are sequential (1-12)

### Document Structure
- [ ] H1 headings used only for numbered major sections
- [ ] H2 headings used consistently for subsections
- [ ] H3 headings used for sub-subsections only
- [ ] No heading level skips (H1 → H3 without H2)
- [ ] Maximum 12 major sections (including About/Disclaimer/Control)

---

## 2. Content Quality

### Executive Summary
- [ ] TL;DR includes all 4 elements: Problem, Solution, Impact, ROI
- [ ] Pain points are quantified with specific numbers
- [ ] Business outcomes table is present and complete
- [ ] Critical insight callout highlights primary value driver
- [ ] Audit savings vs. sales velocity distinction is clear

### Solution Architecture
- [ ] ASCII diagram shows input → platform → output
- [ ] Trust model transparency section acknowledges limitations
- [ ] Cryptographic proof example with real SHA-256 hashes
- [ ] No "absolute immutability" claims without HSM/blockchain

### Competitive Analysis
- [ ] Market landscape table includes 5+ competitors
- [ ] Head-to-head comparison table has 8+ capabilities
- [ ] Differentiation uses qualifiers ("as of Jan 2026", "to our knowledge")
- [ ] Price premium justification includes 3+ value drivers

### Business Case & ROI
- [ ] Cost-benefit table shows before/after comparison
- [ ] All assumptions explicitly listed
- [ ] Sales velocity section separate from audit savings
- [ ] Payback period and ROI percentage included

---

## 3. Formatting & Typography

### Headings
- [ ] H1 titles use Title Case
- [ ] H2/H3 titles consistent (all Title Case OR all Sentence case)
- [ ] No ALL CAPS headings
- [ ] No trailing punctuation on headings

### Tables
- [ ] Every table has a header row
- [ ] Numbers right-aligned with consistent units
- [ ] Currency format consistent: $1.05M, $450K, $500K ARR
- [ ] Time format consistent: 7,000 hrs/year, 3-6 months

### Callouts
- [ ] Maximum 1 callout per major section
- [ ] Callout format: `> **[Type]:** [content]`
- [ ] Callout types: Critical Insight, Key Clarification, Decision Note

---

## 4. Credibility & Citations

### Statistics & Claims
- [ ] Every external statistic has citation marker [1], [2], etc.
- [ ] No "X% of companies" claims without source
- [ ] Industry benchmarks attributed to research firms

### Competitive Claims
- [ ] No unqualified "only platform" statements
- [ ] Superiority claims use qualifiers: "differentiated by", "as of Jan 2026"
- [ ] Feature comparison based on public information

### ROI & Financial Models
- [ ] All assumptions explicitly listed
- [ ] Model inputs labeled as "example" or "typical" when not customer-specific
- [ ] Conservative vs. aggressive scenarios distinguished

---

## 5. Required Ending Blocks

### Conclusion & Next Steps
- [ ] Summary paragraph (2-3 sentences)
- [ ] Decision framework with "is a fit if" and "may not be a fit if"
- [ ] 3 clear CTAs: Live demo, ROI assessment, Pilot program

### About RegEngine
- [ ] Company information (HQ, founded, customers)
- [ ] Compliance certifications (SOC 2, ISO 27001, etc.)
- [ ] Contact information (website, email, phone)

### Legal Disclaimer
- [ ] Disclaimer present and comprehensive
- [ ] Covers: informational purposes, consult professionals, no guarantees

### Document Control
- [ ] Document version matches cover block
- [ ] Publication date matches cover block
- [ ] Next review date set (typically 6 months out)

---

## Issue Severity Guide

**CRITICAL (must fix before publication):**
- Missing required sections
- Unqualified absolute superiority claims
- No ROI assumptions listed
- No legal disclaimer

**HIGH (fix strongly recommended):**
- Statistics without citations
- Inconsistent terminology
- Poor table formatting
- Missing decision framework

---

**Checklist Version:** 1.0
**Last Updated:** January 2026
**Maintained by:** RegEngine Marketing Operations
