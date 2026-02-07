# Energy (NERC CIP) TCO Calculator

**Calculate Your 3-Year ROI with RegEngine**

---

## Input Variables

### Utility Profile
- **Registered Substations**: NERC CIP monitored assets (e.g., 25)
- **BES Cyber Assets**: Critical infrastructure endpoints (e.g., 150)
- **Annual Revenue**: Utility annual revenue (e.g., $800M)
- **Service Territory**: States/regions served (e.g., 3)

### Current Compliance Costs
- **NERC Audit Prep**: Annual preparation time (e.g., $200K)
- **Manual Evidence Collection**: Hours per month (e.g., 200 hrs)
- **Blended Hourly Rate**: Compliance team cost (e.g., $80/hr)
- **Drift Detection**: Time identifying config changes (e.g., 100 hrs/month)
- **NERC Violation Risk**: Historical fines/settlements (e.g., $50K/year avg)
- **Consultant Spend**: External NERC experts (e.g., $100K/year)

---

## Calculation Model

### Current State (Annual)

| Cost Component | Formula | Example |
|----------------|---------|---------|
| **NERC Audit Prep** | Direct cost | **$200,000** |
| **Evidence Collection** | 12 × Hours × Rate | 12 × 200 × $80 = **$192,000** |
| **Drift Detection** | 12 × Hours × Rate | 12 × 100 × $80 = **$96,000** |
| **NERC Violations** | Historical average | **$50,000** |
| **Consultant Spend** | Direct cost | **$100,000** |
| **Total Current Cost** | Sum | **$638,000/year** |

### RegEngine State (Annual)

| Cost Component | Formula | Example |
|----------------|---------|---------|
| **RegEngine Subscription** | Professional tier (11-50) | **$300,000/year** |
| **Reduced Audit Prep** | 90% reduction | **$20,000** |
| **Automated Evidence** | 95% reduction | 12 × 10 × $80 = **$9,600** |
| **Automated Drift Detection** | 100% reduction | **$0** |
| **Reduced Violations** | 95% reduction | **$2,500** |
| **Reduced Consultants** | 80% reduction | **$20,000** |
| **Total RegEngine Cost** | Sum | **$352,100/year** |

### Net Savings

| Metric | Value |
|--------|-------|
| **Annual Savings** | **$285,900/year** |
| **3-Year TCO Savings** | **$857,700** |
| **Payback Period** | **12.6 months** |
| **3-Year ROI** | **95%** |

---

## Risk Mitigation Value

### NERC CIP Fine Avoidance
- **Potential Fine**: $1M/day for serious violations
- **Industry Average**: $250K per violation
- **RegEngine Protection**: Immutable evidence = 95% violation reduction
- **Expected Value**: 0.20 × 0.95 × $250K = **$47.5K/year**

---

**Contact**: sales@regengine.co  
**Calculator**: www.regengine.co/energy/roi-calculator
