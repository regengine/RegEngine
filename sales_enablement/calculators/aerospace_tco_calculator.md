# Aerospace FAI TCO Calculator

**Calculate Your 3-Year ROI with RegEngine**

---

## Input Variables

### Company Profile
- **Annual FAI Submissions**: New parts requiring AS9102 per year (e.g., 100)
- **Configuration Baselines**: Assemblies requiring 30-year tracking (e.g., 50)
- **NADCAP Processes**: Special processes you perform (e.g., 3)
- **Annual Revenue**: Total aerospace revenue (e.g., $50M)

### Current Compliance Costs
- **FAI Prep Time**: Hours per AS9102 FAI (e.g., 40 hrs)
- **Blended Hourly Rate**: Quality engineer cost (e.g., $85/hr)
- **FAI Rework Rate**: % requiring rework due to missing records (e.g., 10%)
- **Avg Rework Cost**: Cost per rework (e.g., $15K)
- **NADCAP Audit Prep**: Annual audit preparation (e.g., $100K)
- **Configuration Lookups**: Hours spent finding old baselines (e.g., 500 hrs/year)
- **Counterfeit Investigation**: Annual cost of suspect part investigations (e.g., $200K)

---

## Calculation Model

### Current State (Annual)

| Cost Component | Formula | Example |
|----------------|---------|---------|
| **FAI Prep Labor** | Submissions × Hours × Rate | 100 × 40 × $85 = **$340,000** |
| **FAI Rework** | Submissions × Rework % × Cost | 100 × 0.10 × $15K = **$150,000** |
| **NADCAP Audit Prep** | Direct cost | **$100,000** |
| **Configuration Lookups** | Hours × Rate | 500 × $85 = **$42,500** |
| **Counterfeit Investigation** | Direct cost | **$200,000** |
| **Total Current Cost** | Sum | **$832,500/year** |

### RegEngine State (Annual)

| Cost Component | Formula | Example |
|----------------|---------|---------|
| **RegEngine Subscription** | Prime Vendor tier | **$350,000/year** |
| **Reduced FAI Prep** | 80% time | 100 × 32 × $85 = **$272,000** |
| **Reduced Rework** | 2% rate | 100 × 0.02 × $15K = **$30,000** |
| **Reduced NADCAP Prep** | 80% reduction | **$20,000** |
| **Reduced Lookups** | 90% reduction | 50 × $85 = **$4,250** |
| **Reduced Investigations** | 90% reduction | **$20,000** |
| **Total RegEngine Cost** | Sum | **$696,250/year** |

### Net Savings

| Metric | Value |
|--------|-------|
| **Annual Savings** | **$136,250/year** |
| **3-Year TCO Savings** | **$408,750** |
| **Payback Period** | **30.8 months** |
| **3-Year ROI** | **39%** |

---

## Risk Mitigation Value

### Counterfeit Part Protection
- **Industry Average**: $1B+ lost annually to counterfeit parts
- **Single Incident Cost**: $500K-$2M (rework + liability)
- **RegEngine Protection**: Cryptographic supply chain verification
- **Expected Value**: 0.10 (baseline risk) × 0.9 (reduction) × $1M = **$90K/year**

### 30-Year Configuration Baseline Value
- **Aircraft Lifespan**: 20-30 years
- **Lost Baseline Cost**: Cannot prove part provenance = grounded aircraft
- **RegEngine Guarantee**: Instant retrieval of any baseline from any date

---

**Contact**: sales@regengine.co  
**Calculator**: www.regengine.co/aerospace/roi-calculator
