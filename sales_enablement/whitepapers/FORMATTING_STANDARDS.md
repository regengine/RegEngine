# RegEngine White Paper Formatting Standards

**Document Version**: 1.0  
**Last Updated**: January 2026  
**Purpose**: Professional PDF publishing standards for RegEngine vertical white papers

---

## Document Structure

### Header (Every Page)

**Layout**:
- RegEngine logo (left, 40px height)
- Document title (center, 12pt semi-bold)
- Page number (right, 10pt regular, format: "Page X")
- Thin accent line below (1px, brand color)

**Spacing**:
- Top margin: 0.75 inches
- Header height: 0.5 inches
- Line to content: 0.25 inches

### Cover Page

**Required Elements**:
1. **Full-bleed hero image** (industry-specific)
   - Energy: Substations, transmission towers
   - Nuclear: Reactor facilities, cooling towers
   - Healthcare: Modern clinical environments
   - Finance: Trading floors, data centers
   
2. **Title** - 32pt bold, centered
3. **Subtitle** - 18pt regular, centered below title
4. **Publication** - "Prepared by RegEngine | [Month Year]"
5. **NO navigation or website elements**

**Industry-Specific Examples**:
```
Energy:     High-voltage transmission lines at sunset
Nuclear:    Containment dome with security perimeter
Healthcare: Clean room with regulatory monitors
Finance:    Secure data center with compliance dashboards
```

### Footer (Every Page)

**Layout**:
- Copyright notice (left): "© 2026 RegEngine Inc. | Confidential"
- Website (right): "regengine.co"
- Font: 9pt light, gray color (#666666)

**Spacing**:
- Bottom margin: 0.75 inches
- Footer height: 0.3 inches

---

## Typography

| Element | Font Family | Size | Weight | Color |
|---------|------------|------|--------|-------|
| **H1** (section titles) | Sans-serif | 24pt | Bold | #1a1a1a |
| **H2** (subsections) | Sans-serif | 18pt | Semi-bold | #333333 |
| **H3** (sub-subsections) | Sans-serif | 14pt | Semi-bold | #444444 |
| **Body text** | Serif or clean sans | 11pt | Regular | #333333 |
| **Captions/footnotes** | Sans-serif | 9pt | Light | #666666 |
| **Pull quotes** | Sans-serif | 14pt | Italic | #1a5f7a |
| **Code blocks** | Monospace | 10pt | Regular | #2d2d2d |

**Font Recommendations**:
- **Primary Sans**: Inter, Helvetica Neue, or Roboto
- **Primary Serif**: Georgia, Merriweather, or Charter
- **Monospace**: Fira Code, Consolas, or Monaco

**Line Height**:
- Body text: 1.6
- Headings: 1.3
- Code blocks: 1.4

---

## Visual Elements

### Tables

**Styling Rules**:
- Alternating row shading (light gray #f5f5f5 / white)
- Header row: Brand color background, white text, bold
- No excessive borders—1px solid #ddd for cell separation only
- Padding: 8px vertical, 12px horizontal
- Font: 10pt for content, 11pt for headers

**Example**:
```
┌───────────────────────────────────────────────────┐
│ Metric        │ Before    │ After     │ Impact   │ ← Header (brand color bg)
├───────────────────────────────────────────────────┤
│ Evidence Hrs  │ 200/mo    │ 10/mo     │ 95% ↓    │ ← White row
│ Audit Prep    │ 6 months  │ 2 days    │ 99% ↓    │ ← Gray row (#f5f5f5)
│ Violations    │ 2-3/year  │ 0         │ 100% ↓   │ ← White row
└───────────────────────────────────────────────────┘
```

### Code/Technical Blocks

**Styling**:
- Light gray background (#f8f8f8)
- Border: 1px solid #e0e0e0
- Border-radius: 4px
- Padding: 16px
- Monospace font
- Max width: Avoid horizontal scrolling

**Usage Guidance**:
- **Use sparingly** - Convert to diagrams for executive audiences
- **Limit to technical appendices** when possible
- **Add captions** explaining what the code demonstrates

**Example**:
```
┌─────────────────────────────────────────┐
│ Configuration Snapshot #1               │
│ ├─ Hash: a4f2b8c1d9e3f7a2...          │
│ ├─ Content: Firewall Rules            │
│ └─ Timestamp: 2026-01-28 10:00:00     │
└─────────────────────────────────────────┘
Caption: Cryptographic hash chain example
```

### Charts (Replace Text Tables Where Possible)

**When to Use Charts**:
- ROI projections → Line or bar chart
- Before/after comparisons → Side-by-side infographic
- Cost breakdowns → Pie or stacked bar
- Market share → Donut chart
- Timeline → Gantt or horizontal bar

**Chart Standards**:
- Brand color palette only
- Clear axis labels
- Data values shown on bars/points
- Legend positioned top-right or bottom
- Title above chart (14pt semi-bold)
- Source attribution below (9pt light)

### Callout Boxes

**Key Stats Box**:
- Colored left sidebar (4px wide, brand color)
- Light background (#f0f7ff for blue theme)
- Large number (32pt bold)
- Context text (11pt regular)
- Padding: 16px
- Border-radius: 4px

**Example**:
```
┌────────────────────────────┐
│ │ 95%                     │
│ │ Reduction in violation  │
│ │ risk with automated     │
│ │ drift detection         │
└────────────────────────────┘
   ↑ Brand color sidebar
```

**Warning/Note Box**:
- Subtle border (1px solid #ddd)
- Icon (left aligned, 20px)
- Muted background (#fff8e1 for warnings, #f0f7ff for notes)
- Padding: 12px
- Border-radius: 4px

---

## Content Cleanup Rules

### 1. Remove All Website Navigation

**Items to Remove**:
- ❌ Top navigation menus (Home, Products, About)
- ❌ Sidebar navigation
- ❌ Footer website links (except copyright/URL)
- ❌ Social media icons
- ❌ Live chat widgets

**Keep**:
- ✅ Internal document navigation (Table of Contents with page numbers)
- ✅ Clickable hyperlinks within content (blue underline)
- ✅ Email addresses (linked is OK)

### 2. Standardize Dates

**Rules**:
- **Publication date**: "January 2026" (month + year)
- **Document version**: "Version 1.0 (January 2026)"
- **Last updated**: "Last Updated: January 28, 2026"
- **Data dates in content**: ISO format "2026-01-28" or "Q4 2025"

**Avoid Mixing**:
- ❌ "2025 results" + "January 2026 publication" (confusing)
- ✅ "Q4 2025 results" + "January 2026 publication" (clear)

### 3. Case Studies

**Attribution Rules**:

**Option A - Named**:
```
"Mid-Size Transmission Operator"
Location: Pacific Northwest
Assets: 25 substations
```

**Option B - Anonymized (Explicit)**:
```
"Anonymized case study from energy sector"
Company profile: Regional transmission operator
```

**Not Acceptable**:
- ❌ "A company we work with..." (too vague)
- ❌ "Major utility in the Western US" (sounds made up)

### 4. Quotes

**Full Attribution Required**:
```
"This was the most transparent audit we've ever conducted."
— Jane Smith, Lead Auditor, WECC Regional Entity
```

**Or Remove**:
If you can't get permission to use name:
- ❌ "WECC Lead Auditor" (anonymous quote looks fake)
- ✅ Remove the quote entirely

### 5. Executive Summary

**Format**:
- Maximum **5 bullet points**
- Each bullet **under 15 words**
- Focus on outcomes, not features

**Example - Good**:
```
• NERC compliance costs reduced from $688K to $330K annually
• Audit preparation time cut from 6 months to→ 2 days
• Zero CIP-010 violations since deployment (was 2-3/year)
• 95% reduction in manual evidence collection hours
• Cryptographic proof eliminates auditor evidence questions
```

**Example - Bad** (too long, too technical):
```
• RegEngine employs SHA-256 cryptographic hashing to create tamper-evident 
  evidence chains that provide mathematical proof of data integrity for NERC 
  auditors during tri-annual compliance reviews
```

### 6. Remove Orphan CTAs

**Buttons/CTAs to Remove from PDFs**:
- ❌ "Schedule Demo" buttons
- ❌ "Start Free Trial" CTAs
- ❌ "Contact Sales" buttons scattered throughout

**Keep**:
- ✅ Contact information in final section
- ✅ Email links (as hyperlinks)
- ✅ "Next Steps" section at end

---

## File Output

### PDF Specifications

**Format**:
- PDF/A-1b (archival quality)
- 300 DPI for all images
- Embedded fonts
- Hyperlinks preserved
- Bookmarks for major sections

**Page Setup**:
- Size: 8.5" × 11" (US Letter)
- Orientation: Portrait
- Margins: 0.75" all sides (0.5" for header/footer)
- Bleed: 0.125" (if professional printing)

### Additional Formats

**PowerPoint Summary Deck**:
- 5-7 slides maximum
- Slide 1: Cover (same as PDF)
- Slide 2: Executive Summary
- Slides 3-5: Key sections (Problem, Solution, ROI)
- Slide 6: Case Study
- Slide 7: Next Steps + Contact

**Editable Source**:
- Markdown (.md) for version control
- Google Docs for collaboration reviews
- InDesign (.indd) for professional layouts (optional)

### Naming Convention

**Format**: `RegEngine_[Vertical]_WhitePaper_[YYYY-MM].pdf`

**Examples**:
- `RegEngine_Energy_WhitePaper_2026-01.pdf`
- `RegEngine_Nuclear_WhitePaper_2026-01.pdf`
- `RegEngine_Healthcare_WhitePaper_2026-02.pdf`

---

## Quality Checklist Before Publishing

Use this checklist for every white paper before final export:

### Content Review
- [ ] **No web template artifacts** (navigation menus, sidebars, chat widgets removed)
- [ ] **Dates standardized** (publication date, data dates consistent)
- [ ] **Case studies properly attributed** (full name OR explicit "anonymized" label)
- [ ] **Quotes have full attribution** (name + title + org) OR removed
- [ ] **Executive summary ≤5 bullets**, each <15 words
- [ ] **No orphan CTAs** ("Schedule Demo" buttons removed from body)

### Visual QA
- [ ] **All images have alt text** (for accessibility)
- [ ] **Page breaks don't split tables/charts** (keep elements together)
- [ ] **Consistent spacing** (section breaks, paragraph spacing uniform)
- [ ] **Tables use alternating shading** (headers have brand color bg)
- [ ] **Charts readable at print size** (labels not too small)

### Technical QA
- [ ] **Links are live** (clickable email, URLs) OR removed for print version
- [ ] **Fonts embedded** (PDF renders on any system)
- [ ] **Images at 300 DPI** (print quality)
- [ ] **File size <10MB** (email-friendly)

### Compliance QA
- [ ] **Legal review complete** (if quoting regulations)
- [ ] **Competitor claims verified** (pricing, features accurate as of date)
- [ ] **ROI calculations documented** (assumptions clearly stated)
- [ ] **Copyright notice present** (footer on every page)

---

## Brand Color Palette

Use these colors for consistency across all white papers:

| Element | Hex Code | Usage |
|---------|----------|-------|
| **Primary Green** | #10b981 | Headers, CTAs, chart primary |
| **Secondary Teal** | #14b8a6 | Gradients, accents |
| **Dark Gray** | #1a1a1a | Body text, headings |
| **Medium Gray** | #666666 | Captions, footnotes |
| **Light Gray** | #f5f5f5 | Table shading, backgrounds |
| **Alert Yellow** | #fbbf24 | Warning callouts |
| **Info Blue** | #3b82f6 | Note callouts |

---

## Print Production Notes

### For Professional Printing

**PDF Settings**:
- Color mode: CMYK (not RGB)
- Crop marks: Yes
- Bleed: 0.125 inches
- Resolution: 300 DPI minimum

**Paper Recommendations**:
- Weight: 80-100lb text
- Finish: Matte or satin
- Binding: Saddle-stitch (≤16 pages) or perfect-bound (>16 pages)

### For Digital Distribution

**PDF Settings**:
- Color mode: RGB
- Optimize for web: Yes (reduces file size)
- Security: Allow printing, no editing
- Compression: Medium (balances quality/size)

---

**Document Maintained By**: RegEngine Marketing Team  
**Questions**: marketing@regengine.co
