# RegEngine FSMA 204 Go-to-Market Bundle

**Compiled:** 2026-05-06
**Status:** Working draft — buyer/pricing study not yet run
**Owner:** Christopher Sellers

This document bundles all GTM artifacts produced during the 2026-05-06 discovery sprint:
ICP consensus report, recruitment screener v2, interview guide, Van Westendorp PSM script,
synthesis template, outreach copy stack, and named outreach list.

Prior chapters in this conversation produced these in stages; consolidating here for durability.

---

## 1. Methodology — how this was produced

- 8 web searches verified FSMA 204 regulatory landscape, competitive pricing, FTL scope, buyer roles
- Research bundle compiled at internal `/tmp/regengine-icp-research.md`
- 4 independent specialist agents (B2B SaaS PMM, food traceability domain expert, solo-founder GTM strategist, adversarial critic) produced personas without seeing each other's output
- Cross-agent consensus extracted: ≥3-of-4 endorsement = consensus; <3 = split worth user judgment
- 142 additional named companies pulled from public LGMA + FPAA directories

---

## 2. Consensus ICP Report

**Verdict pattern:** 4 of 5 reviewers in the prior reshape review said RESHAPE FIRST; consensus moved the buyer/pricing study ahead of dashboard usability work.

### Top 2 ICPs (4-of-4 agent consensus)

#### ICP #1 — Mid-Market Fresh-Cut Processor QA Manager

- **Title:** Plant QA Manager / Director of Food Safety & QA / Compliance Manager
- **Company:** $20M–$120M fresh-cut produce processor — leafy greens / tomatoes / fresh-cut fruits / fresh-cut vegetables. Single-plant or small multi-plant. Sells to **regional grocers + foodservice distributors**, NOT Walmart/Kroger (which would trigger ReposiTrak displacement).
- **Geography:** Salinas, Watsonville, Yuma, Central Valley, Florida (Plant City/Immokalee), Mid-Atlantic (PA/NJ), Texas (McAllen)
- **Supply-chain position:** Transformation CTE (cut/wash/pack node) + Receiving + Shipping
- **Buying authority:** Champion → COO/VP Ops signs
- **Deal size:** $12K–$30K ARR
- **Sales cycle:** 60–90 days
- **Estimated US TAM:** ~3,000 mid-market processors

**Why solo-founder-winnable:** Above ReposiTrak's retailer-pull radar (regional customers don't mandate). Below FoodLogiQ's enterprise economics. Champion buyer → no procurement gauntlet at this size. Hard 2028 deadline forces decision inside founder's runway.

**Pain quote (composite):** *"I don't need recipe-to-recall. I need to type a lot code and have a sortable spreadsheet on the FDA investigator's screen before he finishes his coffee. FoodLogiQ wants to sell me a Ferrari to drive to the mailbox."*

#### ICP #2 — First Land-Based Receiver / Small Importer

- **Title:** Owner / VP Operations / Compliance Lead (often combined at this scale)
- **Company:** $5M–$50M independent food importer or seafood First Land-Based Receiver. Finfish, crustaceans, molluscan shellfish, tropical tree fruits via West Coast / Gulf / Northeast ports. Often immigrant-founded family business.
- **Supply-chain position:** First Land-Based Receiver — the specific CTE called out as "narrow but real obligation, no dedicated tool"
- **Buying authority:** Decision Maker (small importer signs themselves)
- **Deal size:** $5K–$15K ARR (single-CTE wedge)
- **Sales cycle:** 30–45 days
- **Estimated US TAM:** ~700–1,200 firms

**Pain quote (composite):** *"I'm a First Land-Based Receiver — that's literally one of the seven CTEs and nobody sells me a product. They sell to my customer's customer."*

**Risk flagged by adversarial reviewer:** Trace Register / ReposiTrak alliance (announced 2026) is starting to circle seafood specifically. **Window to capture is now.**

### Split — ICP #3 candidate: Owner-Operator Specialty Processor (parked)

Solo-founder-pragmatism agent ranked this #1 (speed-to-yes, $6K–$12K ARR, 30–60 day cycles); PMM and domain agents flagged ACV concerns. **Park until self-serve onboarding flow exists.**

### Consensus AVOID list (4-agent agreement)

- Enterprise CPG (Conagra-tier, $1B+) — FoodLogiQ's customer base; procurement/SOC2 wall
- Mid-market foodservice distributor ($200M–$1B) — FoodLogiQ's mid-market sweet spot; SOC2 + ReposiTrak displacement
- Tier-1 retail-mandated supplier (Walmart/Kroger pipe) — ReposiTrak network IS the mandate
- Mid-market seafood importer/distributor — Trace Register territory since 2005

### Strategic open questions

1. **Post-2028 cliff:** What's the year-3 product? Once customers have a sortable spreadsheet that satisfies FDA, perceived value collapses unless RegEngine has expanded into adjacent workflows.
2. **ReposiTrak displacement filter:** Pre-sales disqualification — "Who are your top 3 customers?" If Walmart/Kroger/Sysco/USFoods/Costco-heavy → defer.

---

## 3. Recruitment Screener v2

```
FSMA 204 buyer & pricing study — 30 min, $50 thank-you
(or free 12-month advisor access — your pick)

Q1. Your role at your company (multi-select OK)
   ● Owner / CEO / President                     ✓ priority A
   ● COO / VP Operations / Plant Manager         ✓ priority A
   ● CFO / Director Finance                      ✓ priority A
   ● QA / Compliance / Food-Safety lead          ✓ priority B
   ● Procurement / Sourcing                      ✓ priority B
   ● IT / Data integration                       ✓ priority C
   ○ Marketing / sales / vendor / consultant     ✗ DQ
   ○ Student / academic                          ✗ DQ

Q2. Your company type
   ● Food producer (grower, processor, manufacturer)  ✓
   ● Distributor / wholesaler                          ✓
   ● 3PL / cold-chain logistics                        ✓
   ● Retailer / grocer / co-manufacturer               ✓
   ● Restaurant / foodservice                          ✓
   ○ Vendor / consulting                               ✗ DQ

Q3. Annual revenue range
   ● <$10M                            ✓ priority B (long tail)
   ● $10M – $50M                      ✓ priority A
   ● $50M – $250M                     ✓ priority A
   ● $250M – $1B                      ✓ priority B
   ● >$1B                             ✓ priority C
   ○ Prefer not to say                ✓ but flag

Q4. In the last 24 months, have you been involved in selecting
    a compliance / traceability / food-safety tool?
   ● Yes — I led the decision               ✓ priority A
   ● Yes — I influenced the decision        ✓ priority B
   ● No — I'd be involved next time         ✓ priority C
   ● No — never                             ✓ cap at 1

Q5. Where does your company stand on FSMA 204?
   ● Have a system, CONSIDERING SWITCHING       ✓ priority A
   ● Actively evaluating                        ✓ priority A
   ● Plan to start within 6 months              ✓ priority A
   ● Researching options                        ✓ priority B
   ● Have a system, satisfied                   ✓ priority B
   ● Haven't started                            ✓ cap at 1

Q6. Which of these have you EVALUATED OR USED in the last
    24 months? (multi-select, no DQ — competitive intel gold)
   □ FoodLogiQ (Trustwell)
   □ Trustwell / HarvestMark
   □ ReposiTrak
   □ Trace Register
   □ iTrade Network
   □ IBM Food Trust
   □ Optel
   □ ERP module (SAP / Oracle / NetSuite / etc.)
   □ Spreadsheets / shared drives
   □ Custom in-house build
   □ Nothing yet
   □ Other: ____________

Q7. Annual budget for compliance + traceability + recall tooling
   ● <$10K   ● $10K-$30K   ● $30K-$100K
   ● $100K-$500K   ● >$500K   ● Don't know

Q8. In 2-3 sentences: what's the hardest part of FSMA 204 prep
    at your company today?

Q9. Time zone + best 30-min window in next 14 days

Q10. Email + name (we won't share)

Q11. Among your top 3 customers by revenue, are any of these on
     the list? (DQ if checked)
   □ Walmart                                    ✗ DQ
   □ Kroger / King Soopers / Harris Teeter      ✗ DQ
   □ Sysco                                      ✗ DQ
   □ US Foods                                   ✗ DQ
   □ Costco                                     ✗ DQ
   □ Whole Foods                                ✓ flag
   □ Performance Food Group                     ✓ flag
   □ Regional grocer (Wegmans, HEB, Publix...)  ✓ qualify
   □ Regional foodservice distributor           ✓ qualify
   □ Direct to restaurant / chain               ✓ qualify

Quotas (N=15) — REWEIGHTED:
   • ≥9 from ICP #1 (mid-market fresh-cut QA Manager, $20M-$120M,
     no Walmart/Kroger/Sysco/USFoods in top 3)
   • ≥4 from ICP #2 (FLBR / small importer, $5M-$50M)
   • ≥3 switchers
   • ≥2 economic buyers
   • ≤1 "haven't started"
   • REMOVED: spreadsheet-only quota (wrong segment for ACV)
```

**Honorarium tiers:**
- Practitioners (QA / Ops / IT): $50 Amazon **or** 12-month free access
- Buyers (Owner / COO / CFO): no cash. Offer "20-min advisor call with the founder + 12-month free access." Pull is 5× higher than money for this segment.

---

## 4. Interview Guide — 45 min

### A. Warm-up (5 min)
1. Tell me about your role and how FSMA 204 fits into it.
2. Who in your org approves spend on a compliance tool? Are *you* that person, an influencer, or the user? *(Code as B/I/U.)*

### B. Current state (10 min) — generative, no product shown
3. Walk me through how your team handles FSMA 204 prep today, end to end.
4. Where does data come from? Supplier 856s? COAs? Email? Drive? Manual entry?
5. What's broken about that today? *(Listen for SPECIFIC failures with names/dates.)*
6. The last time someone asked you for a recall trace — walk me through exactly what happened.
7. If your auditor walked in tomorrow and asked for one-up / one-back on a romaine TLC, how long would it take?

### C. Competitive switching (10 min)
8. In the last 24 months, what compliance / traceability / recall tools have you evaluated or used?
9. For each: *"What made you take the demo? What killed the deal? What did you wish they'd shown?"*
10. (For incumbent users) *"Walk me through a recent moment when [incumbent] failed you."*
11. What's your renewal date? *(Code as MM/YYYY.)*
12. What would have to be true for you to switch?
13. What would make you NOT trust a traceability vendor? *(Listen for: no SOC2, no FDA reference customer, solo founder, no enterprise logo.)*

### D. Willingness to pay — Van Westendorp PSM (10 min)

**Anchor on the regulatory artifact, NOT the dashboard:**

> *"Imagine a tool that, on demand within 24 hours of any audit request, produces your FDA Sortable Spreadsheet — every FTL product, every CTE, every KDE, fully linked by traceability lot code, with chain-of-custody proof. It ingests your supplier 856s, COAs, and harvest records, and reconciles them to lot codes automatically."*

Ask in this exact order:
14. **"At what monthly price would this be SO EXPENSIVE you wouldn't consider it at all?"** → *too expensive*
15. **"At what monthly price would it be expensive — but you'd still consider it?"** → *expensive*
16. **"At what monthly price would you consider it a BARGAIN — a great buy?"** → *bargain*
17. **"At what monthly price would it be SO CHEAP you'd question whether it actually worked?"** → *too cheap*

Probe unit each time: *"Per facility? Per location? Per user? Per FTL SKU?"*

18. Who'd sign that PO?
19. Versus what you spend today on [incumbent / spreadsheets / consultants], how does that compare?

### E. Solution preview (5 min, optional)
20. Show ONE feature mockup (e.g., 60-sec Loom of "856 → auto-reconciled to FTL lot codes"). What questions would you ask before believing this works?
21. What would have to be in your hands before you'd run a 30-day paid pilot?

### F. Wrap (5 min)
22. If a one-person team built this and got it audit-ready, what would your decision criteria be?
23. **Who else should I talk to?** *(Referral chain.)*

---

## 5. Van Westendorp PSM Scoring

Plot 4 cumulative curves on shared x-axis (price):

| Curve | Direction | Interpretation |
|---|---|---|
| Too cheap | Ascending CDF | "I'd doubt quality below this" |
| Bargain | Ascending CDF | "Great deal at this price" |
| Expensive | Descending CDF | "Stretching, but worth it" |
| Too expensive | Descending CDF | "I won't even consider it" |

**Four intersections — your decision points:**

- **PMC** (Point of Marginal Cheapness) = *too cheap* ∩ *bargain* → **price floor**
- **PME** (Point of Marginal Expensiveness) = *expensive* ∩ *too expensive* → **price ceiling**
- **OPP** (Optimal Price Point) = *too cheap* ∩ *too expensive* → **maximizes acceptable**
- **IPP** (Indifference Price Point) = *bargain* ∩ *expensive* → **psychological midpoint, often what people would actually pay**

**Acceptable range:** PMC → PME. **Sweet spot:** OPP → IPP.

At N=15 the curves will be jagged. Goal is **order of magnitude**, not precision. If curves don't intersect cleanly, segment by company-size or buyer-type and re-plot.

---

## 6. One-page Synthesis Template

```markdown
# FSMA 204 Procurement & Pricing Discovery — Synthesis
**Window:** YYYY-MM-DD → YYYY-MM-DD
**N:** _ interviews (_ buyers / _ switchers / _ users)

## TL;DR (3 bullets)

## Q1. Will anyone pay?
**Verdict:** YES / NO / CONDITIONAL
**Evidence:** _ / _ said they'd evaluate at $___/mo or higher.

## Q2. At what price? (Van Westendorp, per ___)
- PMC: $___    IPP: $___
- OPP: $___    PME: $___
- **Sweet spot: $___ – $___ per ___**

## Q3. Who signs?
- Dominant buyer pattern: _____
- Typical sales cycle: _____ months
- Top 3 decision criteria: 1) ___ 2) ___ 3) ___

## Q4. Against which incumbents?
| Incumbent  | # mentions | Avg renewal MM/YY | Top kill reason         |
|------------|-----------|-------------------|-------------------------|
| FoodLogiQ  |           |                   |                         |
| ReposiTrak |           |                   |                         |
| Trustwell  |           |                   |                         |

## Q5. The wedge
Top 3 unmet needs by mention count:
1. _____  (N=___)
2. _____  (N=___)
3. _____  (N=___)

## Decisions made (with date)

## DON'T-ship list

## Pipeline emerging
- _ verbal LOIs
- _ pilot interest
- _ "ping me when it's ready"

## Next experiment
```

---

## 7. Outreach Copy Stack

### LinkedIn DM #1 — ICP #1 (Mid-Market QA Manager)

```
Subject: 30 minutes for $100 — your FSMA 204 prep at {{company}}

Hi {{first_name}} —

I'm building a focused tool for FSMA 204 record-keeping at fresh-cut
processors like {{company}}. Specifically the part where you have to
hand FDA a sortable spreadsheet for all your {{ftl_category}} lots
within 24 hours.

I'm not selling — I'm in discovery. I'd pay $100 for 30 minutes to
hear how your team is approaching the July 2028 deadline today,
what tools you're evaluating, and what the FoodLogiQ quote looked
like.

Pick a slot if any of this resonates: [calendly link]

— Christopher
```

### LinkedIn DM #2 — ICP #2 (FLBR / Importer)

```
Subject: First Land-Based Receiver tool for {{ftl_category}} — 30 min?

Hi {{first_name}} —

Quick one. I noticed {{company}} sits at the First Land-Based
Receiver point — one of the seven CTEs in FSMA 204 — and I haven't
seen a tool built specifically for that handoff. Trace Register
treats you like a producer; FoodLogiQ doesn't model the customs
handoff at all.

I'm building one. Before I build the wrong thing, I'd pay $100
(or 12 months free access on launch) for 30 minutes to learn how
you handle the ASN/COI/BOL reconciliation today and what the
broker software stack misses.

Slot here if interested: [calendly link]

— Christopher
```

### Cold email template

```
Subject: FSMA 204 prep at {{company}} — 30 min, $100

Hi {{first_name}},

Brief one. I'm building a focused traceability tool for {{segment}}
operators ahead of the July 2028 FSMA 204 deadline.

Before I build, I'm running 15 paid discovery calls. The questions
are: (1) what does your team actually do today for CTE/KDE capture,
(2) what tools have you evaluated, (3) what would you pay to make
the 24-hour FDA spreadsheet a non-issue.

I'll pay $100 (Amazon, Visa, your charity of choice) or offer 12
months free access on launch — whichever you prefer.

30 minutes, your time, your candor. {{calendar link}}

Thank you,
Christopher Sellers
RegEngine
```

### r/foodsafety / FSQA Slack post

```
Title: Solo founder building an FSMA 204 tool — paid 30-min discovery
       calls with QA / Compliance leads

I'm building a focused FSMA 204 traceability tool aimed at fresh-cut
processors and small importers in the gap between FoodLogiQ pricing
and ReposiTrak's retailer-driven pull.

Running 15 paid discovery calls. $100 per 30-min call (or free
12-month access on launch — your pick). Looking for:

- QA / Compliance / Food Safety leads at fresh-cut produce, leafy
  greens, tomato, herbs, soft cheese, smoked finfish, or RTE deli
  salad processors at $10M-$120M revenue
- Owners or VP Ops at small seafood / tropical produce importers
  who are First Land-Based Receivers
- Especially: anyone who's gotten a quote from FoodLogiQ, Trustwell,
  ReposiTrak, or Trace Register in the last 18 months

DM or comment. No pitch — discovery only.

— Christopher
```

### 90-second Loom script

```
[0:00–0:10] Intro
"I'm Christopher. RegEngine is a focused FSMA 204 tool for
fresh-cut processors and small importers. Not a platform — a
sortable spreadsheet generator with the CTE/KDE workflow wired in."

[0:10–0:40] The problem
"Here's the FDA Sortable Spreadsheet you'll have to produce within
24 hours of any audit. The hard part isn't the format — it's
pulling lot codes from a 856 EDI, reconciling them to your COA,
and surviving Transformation. Watch."

[0:40–1:10] The wedge demo
"I drop in a sample 856. RegEngine maps it to TLCs. I add a
Transformation event. I export. Done. 24 hours becomes 24 seconds.
That's it. No supplier network. No recipe-to-recall."

[1:10–1:30] Ask
"I'm in discovery, not selling. 30 minutes, $100 (or free access
on launch). If your job involves FSMA 204 prep at a $10M-$120M
producer or importer, I'd love to talk. Calendar link below."
```

### LinkedIn search strings

**ICP #1:**
```
"QA Manager" OR "Quality Assurance Manager" OR "Director of Food Safety"
   AND ("fresh cut" OR "leafy greens" OR "fresh-cut" OR "tomato" OR
        "produce processor" OR "food safety")
   AT companies 50-500 employees
   IN: California / Arizona / Florida / Pennsylvania / New Jersey
```

**ICP #2:**
```
"VP Operations" OR "President" OR "Owner" OR "Compliance Manager"
   AND ("seafood importer" OR "first receiver" OR "tropical produce" OR
        "food broker" OR "customs broker")
   IN: Massachusetts / Florida / Washington / Alaska / Louisiana / Texas
```

---

## 8. Named Outreach List — verified companies

Total: **~210 unique companies** across both ICPs after dedup. Each marked: **FIT** = ICP-aligned / **BORDER** = check revenue before reaching out / **AVOID** = enterprise/incumbent-locked.

### ICP #1 — Mid-Market Fresh-Cut Processors

#### California Leafy Greens Marketing Agreement (LGMA) certified — fetched 2026-05-06
**Source:** [lgma.ca.gov/certified-members](https://lgma.ca.gov/certified-members)

Salinas / Watsonville / Gonzales / Castroville / Spreckels / Moss Landing / Gilroy / King City:
- 68 Produce, LLC (Salinas) — FIT
- Bengard Ranch, Inc. (Salinas) — FIT
- Bud Antle, LLC (Salinas) — BORDER
- C and E Farms, Inc. (Salinas) — FIT
- Church Brothers Farms (Salinas) — FIT
- Classic Salads, LLC (Salinas) — FIT
- Coastline Family Farms, Inc. (Salinas) — FIT
- D'Arrigo California (Salinas) — BORDER
- Duda Farm Fresh Foods, Inc-CA (Salinas) — BORDER
- Dynasty Farms (Salinas) — FIT
- Field Fresh Farms (Watsonville) — FIT
- Fresh Express, Inc. (Salinas) — AVOID (Chiquita-owned, FoodLogiQ tier)
- George Amaral Ranches, Inc. (Gonzales) — FIT
- Greengate Fresh, LLLP (Salinas) — FIT
- Harbinger Group / Misionero (Salinas) — FIT
- Hitchcock Farms, Inc. (Salinas) — FIT
- Ippolito International (Salinas) — FIT
- Lakeside Organic Gardens, LLC (Watsonville) — FIT
- Market Farms, Inc. (Salinas) — FIT
- Muzzi Family Farms (Moss Landing) — FIT
- Ocean Mist Farms (Castroville) — BORDER
- organicgirl, LLC (Salinas) — FIT
- Pacific International Marketing (Salinas) — FIT
- Pajaro Valley Fresh Fruit and Veg Dist. (Watsonville) — FIT
- River Fresh Farms, LLC (Salinas) — FIT
- Royal Rose, LLC (Salinas) — FIT
- Sábor Farms, LLC (Salinas) — FIT
- Salad Savoy Corp. (Salinas) — FIT
- Silva Farms, LLC (Gonzales) — FIT
- Spinaca Farms, Inc. (Gilroy) — FIT
- Steinbeck Country Produce (Spreckels) — FIT
- Sunsation Farms, Inc. (Monterey) — FIT
- Tanimura and Antle Fresh Foods, Inc. (Salinas) — BORDER
- Taylor Farms (Salinas) — AVOID (FoodLogiQ-tier, mass enterprise)
- The Nunes Company, Inc. (Salinas) — FIT
- The Salad Farm, LLC (Salinas) — FIT
- Visionary Vegetables, LLC (Salinas) — FIT
- Western Harvesting, LLC (King City) — FIT
- Zada Fresh Farms (Salinas) — FIT

Santa Maria / Guadalupe / Lompoc / Nipomo / Arroyo Grande:
- Agro Jal Farms, Inc. (Santa Maria) — FIT
- Babe Farms, Inc. (Santa Maria) — FIT
- Beachside Produce, LLC (Guadalupe) — FIT
- Bella Vista Produce, Inc. (Santa Maria) — FIT
- Bonipak Produce Inc. (Santa Maria) — FIT
- Durant Distributing (Santa Maria) — FIT
- EpicVeg, Inc. (Lompoc) — FIT
- Fresh Kist Produce (Nipomo) — FIT
- Gold Coast Packing Co. (Santa Maria) — FIT
- L & J Innovations, LLC (Santa Maria) — FIT
- Sun Coast Farms (Santa Maria) — FIT
- Talley Farms, Inc. (Arroyo Grande) — FIT

Oxnard / Fillmore / Westlake Village / Moorpark / Sun Valley:
- Boskovich Farms (Oxnard) — BORDER
- Cinagro Farms, Inc. (Fillmore) — FIT
- Coastal Fresh Farms (Westlake Village) — FIT
- Deardorff Family Farms (Oxnard) — FIT
- GJ Farms, Inc. (Fillmore) — FIT
- Golden West Vegetables, Inc. (Oxnard) — FIT
- Kenter Canyon Farms (Sun Valley) — FIT
- Marmolejo Farms, Inc. (Oxnard) — FIT
- Muranaka Farm, Inc. (Moorpark) — FIT
- Nova World Fresh (Oxnard) — FIT
- Pablo's Produce (Oxnard) — FIT
- Pacific Fresh Produce, Inc. (Oxnard) — FIT

Imperial Valley / El Centro / Holtville / Coachella:
- 1912 Produce, LLC (El Centro) — FIT
- Heritage Farms, LLC (El Centro) — FIT
- Joe Heger Farms, LLC (El Centro) — FIT
- Mainas Farms, LLC (Holtville) — FIT
- Mike Abatti Farms, LLC (El Centro) — FIT
- Vessey & Company, Inc. (Holtville) — FIT
- Amazing Coachella / Peter Rabbit Farms (Coachella) — FIT

Yuma / Scottsdale (AZ):
- Amigo Farms, Inc. (Yuma) — FIT
- Premium Valley Produce, Inc. (Scottsdale) — FIT
- TLC Custom Farming Company, LLC (Yuma) — FIT

San Joaquin / Modesto / Fresno / Bakersfield / Le Grand:
- Baloian Packing Co., Inc. (Fresno) — FIT
- Creekside Organics Inc. (Bakersfield) — FIT
- Dan Andrews Farms (Bakersfield) — FIT
- Grimmway Farms (Bakersfield) — AVOID (large carrot specialist, retailer-mandated)
- J. Marchini Farms (Le Grand) — FIT
- Ratto Bros., Inc. (Modesto) — FIT

Other CA / out-of-state LGMA members:
- Access Organics (Kalispell, MT) — FIT
- Bonduelle Americas dba Ready Pac Food, Inc. (Irwindale) — AVOID (Bonduelle = global)
- Peri & Sons Farms (Yerington, NV) — BORDER
- San Diego Farms / Fresh Origins (San Marcos) — FIT
- SunTerra Produce, Inc. (Newport Beach) — FIT

#### Fresh Produce Association of the Americas (FPAA) — Nogales / Rio Rico / Tucson / South Texas
**Source:** [thefpaa.com/distributor-membership-directory](https://www.thefpaa.com/distributor-membership-directory/)

- Atardecer Produce (Rio Rico, AZ) — FIT
- Cactus Melon Dist. Inc. (Nogales) — FIT
- Calavo Growers Inc. (Nogales) — AVOID (public company, large)
- Chucho Produce (Nogales) — FIT
- CIL Fresh (Weslaco, TX) — FIT
- Ciruli Brothers (Tubac, AZ) — FIT
- Del Campo Supreme (Nogales) — FIT
- Delta Fresh Sales LLC (Nogales) — FIT
- Direct Roots (Rio Rico) — FIT
- Divine Flavor LLC (Nogales) — BORDER (large organic)
- Double Tree Castle, Inc. (Rio Rico) — FIT
- Eagle Eye Produce (Rio Rico) — FIT
- Earth Blend LLC (Nogales) — FIT
- Farmer's Best International, LLC (Nogales) — BORDER
- Flavor King Farms (Rio Rico) — FIT
- Frank's Distributing of Produce, LLC (Nogales) — FIT
- Frello Fresh, LLC (Rio Rico) — FIT
- Fresh Farms (Rio Rico) — FIT
- Fresh International LLC (Tucson) — FIT
- Grower Alliance, LLC (Rio Rico) — FIT
- Healthy Fresh LLC (Rio Rico) — FIT
- Higueral Produce Inc (Rio Rico) — FIT
- iDealHarBest, LLC (Nogales) — FIT
- IPR Fresh (Rio Rico) — FIT
- L&M Companies, Inc. (Nogales + Raleigh, NC) — BORDER (multi-state)
- M.A.S. Melons & Grapes, LLC (Nogales) — FIT
- Magenta Produce (Nogales) — FIT
- Malena Produce, Inc. (Rio Rico) — FIT
- Marengo Foods, LLC (Rio Rico) — FIT
- Masterstouch Brand, LLC (San Diego) — FIT
- MexFresh Produce (Edinburg, TX) — FIT
- Natural Flavor Produce, LLC (Rio Rico) — FIT
- NatureSweet (San Antonio) — AVOID (largest tomato grower-shipper)
- P.D.G. Produce, Inc. (Nogales) — FIT
- Pacific Tomato Growers (Nogales) — BORDER
- Pandol Brothers, Inc. (Delano, CA) — BORDER (large grape)
- Prime Time International (La Quinta, CA) — BORDER
- Pristine Products Co. (Nogales) — FIT
- Produce Connection (Rio Rico) — FIT
- Produce House, LLC (Nogales) — FIT
- Produce Team (McAllen, TX) — FIT
- RCF Distributors (Rio Rico) — FIT
- Red Sun Farms (Nogales + Taylor, MI) — BORDER
- Robinson Fresh (Nogales) — AVOID (CH Robinson subsidiary)
- Seeded Produce (Nogales) — FIT
- Sigma Sales Co., Inc. (Nogales) — FIT
- SL Produce LLC (Chandler, AZ) — FIT
- Star Produce US LP (Nogales) — FIT
- SunFed (Rio Rico) — FIT
- Tepeyac Produce, Inc. (Rio Rico) — FIT
- Terra Fresh Organics (Reedley, CA) — FIT
- The Giumarra Companies (Rio Rico + LA) — AVOID (very large)
- The Sykes Company (Rio Rico) — FIT
- Tricar Sales, Inc. (Nogales) — FIT
- TruFresh (Nogales) — FIT
- Vandervoet & Associates, Inc. (Rio Rico) — FIT
- Wholesum Family Farms, Inc. (Nogales) — FIT
- Wilson Produce, LLC (Nogales) — FIT

#### Florida tomato / fresh-cut
- West Coast Tomato (FL only) — FIT
- Sunripe Certified Brands — BORDER
- Gargiulo, Inc. — FIT
- Harllee Packing Inc. — FIT
- Nobles-Collier, Inc. — FIT
- DiMare Ruskin, Inc. — BORDER
- Lipman Family Farms — AVOID (largest field tomato in NA)

#### Mid-Atlantic fresh-cut (PA/NJ/MD/VA)
- Robert's Precut Vegetables, Inc. (TazZA) — FIT
- Fresh Valley Foods Corporation — FIT
- Tailor Cut Produce — FIT
- Z-A Specialty Foods — FIT
- Maglio Companies — BORDER
- FreshPoint Pittsburgh — AVOID (Sysco-owned)

#### Kennett Square mushrooms (PA)
- Phillips Mushroom Farms / Phillips Gourmet — FIT (large family co)
- South Mill Mushroom Farms — FIT
- Greenwood Mushrooms — FIT
- Kennett Square Specialties Sales (KSS) — FIT
- Caputo & Guest — FIT
- Pietro Industries — FIT

#### Pacific Northwest berries (OR/WA)
- Willamette Valley Fruit Company — FIT
- Oregon Berry Packing, Inc. — FIT
- Rader Farms — BORDER
- Townsend Farms — FIT
- Pacific Coast Fresh Co. — FIT
- MBG Marketing / blueberries.com — FIT

#### Fresh herbs
- Soli Organic — FIT
- Infinite Herbs — FIT
- Kitchen Gardens Herbs — FIT
- Produce Services of LA — FIT
- SupHerb Farms — BORDER

#### RTE deli salads (single FTL category)
- Reser's Fine Foods — BORDER
- St. Clair Foods — FIT

### ICP #2 — First Land-Based Receiver / Small Importer

#### Gloucester / Boston / New Bedford, MA
- F.W. Bryce, Inc. — FIT
- Atlantic Fish and Seafood — FIT
- Intershell International — FIT
- Gloucester Seafood Processing, Inc. — FIT
- J. Turner Seafoods — FIT
- North Atlantic Pacific Seafood (NAPS) — FIT
- Channel Fish Processing (Braintree) — FIT
- Eastern Fisheries — BORDER
- Seatrade International / East Coast Seafood — BORDER
- Great Eastern Seafood — FIT
- North Coast Seafoods — BORDER
- Stavis Seafood — FIT
- John Nagle Co. — FIT
- Atlantic Coast Seafood — FIT

#### Miami — tropical fruit + seafood importers
- Tasty Seafood Company — FIT
- Seafood Imports, Inc. — FIT
- Miami Tropical — FIT
- WP Produce Corp — FIT
- AB Tropical — FIT
- Miami Tropical Wholesaler, Inc. — FIT
- Seasons Farm Fresh — FIT
- Jack Scalisi Wholesale Fruit & Produce — FIT
- iTi Tropicals — BORDER

#### Alaska / Pacific NW seafood (FLBR capital of the US)
- Leader Creek Fisheries — FIT
- Phoenix Processor LP — FIT
- E&E Foods — BORDER
- North Pacific Seafoods — BORDER
- Silver Bay Seafoods — AVOID (19 facilities)

---

## 9. Directories for further expansion (200 → 500+)

| Directory | URL | Yields |
|---|---|---|
| California LGMA | [lgma.ca.gov/certified-members](https://lgma.ca.gov/certified-members) | 84 (used) |
| FPAA Distributors | [thefpaa.com/distributor-membership-directory](https://www.thefpaa.com/distributor-membership-directory/) | 58 (used) |
| PSPA Members | [pspafish.net/members](https://www.pspafish.net/members) | 11 corporate + subs |
| NOAA Federal Processor List | [fisheries.noaa.gov/.../21ffp_current_processor.htm](https://www.fisheries.noaa.gov/sites/default/files/akro/21ffp_current_processor.htm) | 200+ AK seafood processors |
| Alaska ADEC GIS | [gis.data.alaska.gov/.../seafood-processing-facility-locations-1](https://gis.data.alaska.gov/datasets/ADEC::seafood-processing-facility-locations-1/data) | All licensed AK facilities |
| ADFG Buyers/Processors | [adfg.alaska.gov/index.cfm?adfg=fishlicense.buyers](https://www.adfg.alaska.gov/index.cfm?adfg=fishlicense.buyers) | Licensed buyer/processor list |
| IFPA Member Directory | [freshproduce.com](https://www.freshproduce.com/membership/membership-toolkit/) | Members-only — join cheap |
| Western Growers | [wga.com](https://www.wga.com/) | CA/AZ/CO/NM produce |
| NFI Member List | [aboutseafood.com](https://aboutseafood.com/) | National Fisheries Institute |
| Refrigerated Foods Association | [refrigeratedfrozenfood.com](https://www.refrigeratedfrozenfood.com/) | Smaller RTE producers |
| Vermont Cheese Council | [vtcheese.com](https://vtcheese.com/) | Soft cheese (parked under ICP #3) |
| ProduceMarketGuide | [producemarketguide.com](https://www.producemarketguide.com) | Searchable cross-category |
| GS1 US registered companies | [gs1us.org](https://www.gs1us.org/) | Existing TLC users |

---

## 10. Recommended sequence

1. **Today:** Review screener v2, sign off on quotas. Pick honorarium tier per persona.
2. **Days 1–2:** Recruiting outreach blitz — 30 LinkedIn DMs/day from named list, 1 r/foodsafety post, 1 FSQA Slack post, 1 round of cold emails to FPAA and Gloucester/Miami importer lists. Target 30 inbound responses.
3. **Days 3–7:** Schedule + run interviews. 3/day × 5 days = 15 interviews.
4. **Day 8:** Synthesize using template above.
5. **Day 9:** Make decisions: pricing model, ICP narrowing, wedge feature, build/pivot/kill.
6. **Day 10+:** If verdict is YES: build the Loom-able wedge; resume dashboard usability research after 3 verbal LOIs or 1 paid pilot.

---

## Sources (verified web research, 2026-05-06)

- [FDA — FSMA 204 Final Rule](https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods)
- [Federal Register — Compliance Date Extension to July 20, 2028](https://www.federalregister.gov/documents/2025/08/07/2025-14967/requirements-for-additional-traceability-records-for-certain-foods-compliance-date-extension)
- [FDA — Food Traceability List](https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list)
- [Food Safety Magazine — FDA Delays FSMA 204 30 Months](https://www.food-safety.com/articles/10245-fda-delays-fsma-204-traceability-rule-compliance-date-by-30-months)
- [Sustainable Agriculture — Smaller Farms Higher Compliance Costs](https://sustainableagriculture.net/blog/fsma-compliance-costs/)
- [Capterra — FoodLogiQ Pricing](https://www.capterra.com/p/160619/FoodLogiQ/)
- [ITQlick — FoodLogiQ Pricing Plans](https://www.itqlick.com/foodlogiq/pricing)
- [BusinessWire — ReposiTrak 18 Fresh Fruit/Veg Suppliers](https://www.businesswire.com/news/home/20260407021636/en/ReposiTrak-Traceability-Network-Extends-Deeper-into-the-Food-Supply-Chain-as-18-Fresh-Fruit-Vegetable-Providers-Join-the-Queue-Preparing-for-Traceability)
- [Food Safety Magazine — ReposiTrak 4,000 Suppliers](https://www.food-safety.com/articles/9812-repositrak-traceability-network-grows-to-4-000-suppliers-furthering-fsma-204-compliance)
- [Trace Register / ReposiTrak Alliance](https://repositrak.com/press-release/trace-register-and-repositrak-announce-alliance-to-help-retailers-wholesalers-and-seafood-suppliers-with-fsma-204-food-traceability/)
- [Food Logistics — FSMA 204 Cold Chain](https://www.foodlogistics.com/safety-security/food-safety/article/22926779/food-drug-administration-fda-fsma-204-compliance-to-fundamentally-change-how-the-cold-chain-works)
- [Lindner Logistics — 3PL Guide to FSMA 204](https://www.lindnerlogistics.com/fsma-204-cold-chain-compliance)
- [GMI — Food Traceability Market Size](https://www.gminsights.com/industry-analysis/food-traceability-market)
- [Mordor — Food Traceability Market](https://www.mordorintelligence.com/industry-reports/food-traceability-market)
- [IFT — Global Food Traceability Center](https://info.ift.org/global-food-traceability-center-fsma-collab)
- [FoodReady — First Land-Based Receivers Guide](https://foodready.ai/blog/fsma-rule-204-traceability-land-receivers/)
- [IFDA — FSMA 204 Manual](https://www.ifdaonline.org/wp-content/uploads/2024/02/IFDA-Manual-on-FSMA-204-Food-Traceability-Rule.pdf)
- [AgCareers — Food Safety/QA Manager Profile](https://www.agcareers.com/career-profiles/food-safety-quality-assurance-manager.cfm)
- [California LGMA Certified Members](https://lgma.ca.gov/certified-members)
- [FPAA Distributor Membership Directory](https://www.thefpaa.com/distributor-membership-directory/)
