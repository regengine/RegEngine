# RegEngine Execution Roadmap — Q2–Q4 2026

**Owner:** Christopher (solo founder)
**Date:** April 9, 2026
**Revenue:** $0 | **Team:** 1 + Claude Code overnight sessions
**North Star:** Generate inbound leads and close first paying customers before FSMA 204 urgency kicks in (July 2028 enforcement deadline)

---

## NOW — This Week / Next 2 Weeks (April 9–23)

These are the highest-ROI moves you can make immediately. Every item either fixes something embarrassing for prospects visiting the site, or turns on a lead-gen channel that's currently dormant.

---

### 1. Fix Pricing Inconsistency Across All Pages
- **What:** Audit every page that mentions pricing and align to the current tiers ($425–$639/mo annual). Kill or redirect legacy $999 pages. Single source of truth.
- **Why:** A prospect who sees $425 on the homepage and $999 on a buried page loses trust instantly. This is a deal-killer for anyone doing due diligence.
- **Who:** Claude Code (overnight session — grep all pricing references, update, submit PR)
- **Effort:** 2–3 hours Claude Code
- **Closes:** #526 (pricing page), #640 (pricing inconsistency)

### 2. Ship the Security & Trust Page
- **What:** Implement the security/trust page from the draft copy already written. Include SOC 2 intent, data handling, encryption, infrastructure details. Link it from the footer and pricing page.
- **Why:** Mid-market food companies have procurement teams. No security page = disqualified before a demo. This is table stakes.
- **Who:** Claude Code (overnight — implement from existing draft copy)
- **Effort:** 2–3 hours Claude Code
- **Closes:** #642

### 3. SEO Foundation — Index the 19 Free Tools
- **What:** Create individual landing pages (or optimize existing ones) for each free tool with proper title tags, meta descriptions, H1s targeting FSMA 204 long-tail keywords. Add internal linking between tools. Submit sitemap to Google Search Console.
- **Why:** You have 19 working tools and ZERO Google presence. Each tool is a potential ranking page for queries like "FSMA 204 traceability lot code lookup" or "food recall template free." This is your single biggest untapped asset.
- **Who:** Claude Code builds the pages/SEO markup; Christopher submits sitemap and verifies in Search Console (15 min manual)
- **Effort:** 4–6 hours Claude Code + 30 min Christopher
- **Closes:** #524 (SEO), #644 (free tools audit — already confirmed working)

### 4. Add EmailGate/LeadGate to All Free Tools
- **What:** Verify that every free tool captures an email before delivering results. For tools that don't have it yet, add the gate. Set up a simple email sequence (even 3 emails: welcome → value → CTA for demo).
- **Why:** Traffic without capture is wasted. The tools are built. The gates are built. Wire them together so every tool visitor becomes a lead.
- **Who:** Claude Code (gate implementation); Christopher sets up email sequence in whatever ESP you have (Mailchimp free tier, Resend, etc.)
- **Effort:** 3–4 hours Claude Code + 1 hour Christopher
- **Closes:** Part of #524

### 5. Fix Login/Auth Issues
- **What:** Implement rate limiting on login, remove QA presets from production, fix stale nav state, fix password change endpoint.
- **Why:** If a prospect tries to sign up or log in and hits broken UX, you're dead. These are bugs visible to anyone who clicks "Sign Up."
- **Who:** Claude Code (overnight session)
- **Effort:** 3–4 hours Claude Code
- **Closes:** #520, #521, #522, #523

### 6. Rewrite Homepage Positioning — Lead with Operational Value
- **What:** Replace any "comply or get fined" messaging with operational value: brand protection, supply chain visibility, recall readiness, customer audit confidence. The enforcement deadline is 2+ years out and Congress defunded enforcement — fear doesn't sell right now.
- **Why:** Your current pitch assumes urgency that doesn't exist yet. Buyers today are motivated by operational efficiency, not penalties. The companies buying now (like ReposiTrak's customers) are buying for competitive advantage.
- **Who:** Christopher drafts 3–5 bullet positioning; Claude Code implements on homepage
- **Effort:** 1 hour Christopher + 2 hours Claude Code
- **Closes:** #525 (positioning)

---

## NEXT — May–June 2026

Build on the foundation. NOW gave you a credible site, working lead capture, and search indexing. NEXT turns that into pipeline.

---

### 7. Content Engine — Publish 2 Blog Posts Per Week
- **What:** Claude Code drafts SEO-targeted blog posts on FSMA 204 topics: "What mid-market food companies need to know about FSMA 204," "FSMA 204 compliance checklist 2026," "How to prepare for FDA traceability requirements," etc. Christopher reviews (15 min each) and publishes.
- **Why:** Google needs content to rank you. Each post targets a keyword cluster, links to your free tools, and funnels to email capture. Compounding returns — posts published in May rank by August.
- **Who:** Claude Code drafts; Christopher reviews and publishes
- **Effort:** 2 hours/week Claude Code + 30 min/week Christopher
- **Closes:** Ongoing — supports #524

### 8. Build a "Compare" Page — RegEngine vs. Competitors
- **What:** Create a transparent comparison page: RegEngine vs. ReposiTrak vs. FoodLogiQ vs. TraceGains vs. FoodReady. Highlight your differentiators: API-first, mid-market pricing, public GitHub, purpose-built for FSMA 204.
- **Why:** Prospects Google "[competitor] alternative." This page captures that traffic and positions you as the informed choice. Also useful in sales conversations.
- **Who:** Claude Code builds the page; Christopher validates competitor claims
- **Effort:** 3–4 hours Claude Code + 1 hour Christopher

### 9. Get 2–3 Pilot Customers (Free or Deeply Discounted)
- **What:** Offer 3-month free pilots to 2–3 small food companies in exchange for: a logo on the site, a 2-sentence testimonial, and a 15-min case study interview. Target companies with 10–50 employees in the FDA's Food Traceability List categories (leafy greens, fresh-cut fruits, cheeses, nut butters, etc.).
- **Why:** You have zero social proof. No logos, no testimonials, no case studies. One real customer story is worth more than 50 blog posts. This also validates product-market fit.
- **Who:** Christopher (outreach — LinkedIn, food industry forums, local food companies). Target 20 outreach messages to get 2–3 yeses.
- **Effort:** 4–5 hours Christopher over 2 weeks
- **Closes:** #641 (customer logos)

### 10. Implement Customer Logo/Testimonial Section
- **What:** Once you have 1+ pilot customer, add a logo bar and testimonial section to the homepage. Even "Trusted by 3 food companies" with real logos changes the page completely.
- **Why:** Social proof is the #1 conversion factor for B2B SaaS. Right now the site screams "no one uses this."
- **Who:** Claude Code (30 min once logos are available)
- **Effort:** 30 min Claude Code
- **Closes:** #641

### 11. Set Up Basic Analytics and Conversion Tracking
- **What:** Google Analytics 4 + conversion events on: email gate submissions, pricing page views, demo requests. Set up Google Search Console and monitor which tool pages are getting impressions.
- **Why:** You can't optimize what you don't measure. You need to know which free tools drive the most leads and which blog posts get traffic.
- **Who:** Claude Code (GA4 snippet + event tracking); Christopher verifies in GA4 dashboard
- **Effort:** 2 hours Claude Code + 30 min Christopher

### 12. LinkedIn Thought Leadership — 3 Posts Per Week
- **What:** Christopher posts short, opinionated takes on FSMA 204 readiness, supply chain traceability, and what mid-market companies are getting wrong. Link to free tools and blog posts. Engage in food safety LinkedIn groups.
- **Why:** LinkedIn is where food safety and supply chain decision-makers hang out. Free distribution, builds personal brand as the FSMA 204 expert, drives traffic to the site.
- **Who:** Christopher (15 min/post — Claude Code can draft if needed)
- **Effort:** 45 min/week Christopher

---

## LATER — Q3–Q4 2026 (July–December)

The foundation is set: site is credible, tools are indexed and capturing leads, you have pilot customers and content ranking. Now scale what's working.

---

### 13. Double Down on What's Converting
- **What:** Review analytics from May–June. Which free tools generate the most leads? Which blog posts get the most traffic? Which outreach messages got responses? Kill what doesn't work, 3x what does.
- **Why:** By Q3 you'll have 2–3 months of data. Solo founders can't do everything — ruthlessly cut the bottom half and invest in the top performers.
- **Who:** Christopher (analysis) + Claude Code (implementation)
- **Effort:** 2–3 hours quarterly review

### 14. Launch a "FSMA 204 Readiness Assessment" Lead Magnet
- **What:** Interactive quiz/assessment: "How ready is your company for FSMA 204?" Captures company size, product types, current traceability methods. Delivers a personalized readiness score + recommendations. Captures email + company info.
- **Why:** Higher-intent lead capture than a generic email gate. Gives you qualification data (company size, product type) before you ever talk to them. Shareable — people forward these to their teams.
- **Who:** Claude Code builds it as a tool on the site
- **Effort:** 6–8 hours Claude Code

### 15. Publish 2–3 Case Studies from Pilot Customers
- **What:** Interview pilot customers. Write up: problem → solution → results. Even qualitative results ("saved 4 hours/week on traceability paperwork") are powerful.
- **Why:** Case studies close deals. A mid-market food company VP wants to see someone like them succeeding with your tool before they sign.
- **Who:** Christopher (interviews — 30 min each); Claude Code (writes up)
- **Effort:** 2 hours Christopher + 3 hours Claude Code

### 16. Explore Channel Partnerships
- **What:** Reach out to food safety consultants, FSMA 204 training companies, and food industry associations. Offer affiliate/referral arrangements or co-marketing (joint webinars, guest blog posts).
- **Why:** Consultants are already advising food companies on FSMA 204 compliance. If they recommend RegEngine as the tool, you get warm introductions without sales effort.
- **Who:** Christopher (relationship building)
- **Effort:** Ongoing — 2 hours/week

### 17. API Documentation and Developer Marketing
- **What:** Polish API docs, publish on the site, submit to API directories. Your public GitHub repo is a differentiator — make it visible.
- **Why:** API-first is your unique angle vs. legacy competitors. CTOs and technical buyers at mid-market companies will evaluate your API docs before they evaluate your sales deck.
- **Who:** Claude Code (docs generation from codebase)
- **Effort:** 4–6 hours Claude Code

### 18. Pricing Experiment — Add a Starter Tier
- **What:** If pilot data shows that $425/mo is too high for initial commitment, consider a $99–$199/mo starter tier with limited features (e.g., traceability for 1 facility, limited API calls). Or offer annual-only at current pricing with a monthly option at a premium.
- **Why:** FoodReady is at $24/seat. You don't need to race to the bottom, but you need a low-friction entry point for companies that aren't ready to commit $5K+/year sight unseen.
- **Who:** Christopher (pricing strategy); Claude Code (implementation)
- **Effort:** 2 hours strategy + 3 hours Claude Code

### 19. Prep for the 2027 Urgency Wave
- **What:** By late 2026, you're 18 months from the July 2028 deadline. Companies will start panicking. Have ready: a "Compliance Countdown" page, updated blog content with urgency framing, a webinar or live demo series, retargeting ads (even $200/mo budget) for people who visited your free tools.
- **Why:** The enforcement deadline will eventually create real urgency. The companies that prepared early (your pilot customers) become your case studies. The companies that waited become your pipeline.
- **Who:** Claude Code (content/pages); Christopher (ads, webinar)
- **Effort:** Ongoing build through Q4

---

## Summary View

| Phase | Key Outcomes | Lead Gen Impact |
|-------|-------------|-----------------|
| **NOW** (Apr 9–23) | Credible site, SEO indexed, lead capture on, auth bugs fixed | Tools start appearing in Google; email capture begins |
| **NEXT** (May–Jun) | Content engine running, pilot customers onboard, social proof live | Inbound leads from SEO + LinkedIn; first testimonials |
| **LATER** (Q3–Q4) | Data-driven optimization, case studies, channel partners, urgency prep | Compounding inbound; positioned for 2027 urgency wave |

---

## Critical Path — What Breaks If You Skip It

1. **Skip SEO (#3)?** → You stay invisible. No organic traffic ever.
2. **Skip email gates (#4)?** → Traffic comes but no one converts. Vanity metrics.
3. **Skip pilot customers (#9)?** → No social proof. Every prospect wonders "is anyone actually using this?"
4. **Skip positioning fix (#6)?** → You're selling fear that doesn't exist yet. Prospects bounce.
5. **Skip pricing fix (#1)?** → Prospects see conflicting prices and assume the site is abandoned or scammy.

---

## GitHub Issues Closed by This Roadmap

| Issue | Closed By | Phase |
|-------|-----------|-------|
| #520 (rate limiting) | Item 5 | NOW |
| #521 (stale nav) | Item 5 | NOW |
| #522 (QA presets) | Item 5 | NOW |
| #523 (password change) | Item 5 | NOW |
| #524 (SEO) | Items 3, 4, 7 | NOW + NEXT |
| #525 (positioning) | Item 6 | NOW |
| #526 (pricing page) | Item 1 | NOW |
| #640 (pricing inconsistency) | Item 1 | NOW |
| #641 (customer logos) | Items 9, 10 | NEXT |
| #642 (security certs) | Item 2 | NOW |
| #643 (footer) | DONE (PR #645) | — |
| #644 (free tools audit) | DONE (all working) | — |

---

*Generated April 9, 2026. Review and reprioritize bi-weekly.*
