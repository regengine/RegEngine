# Crawl & Ingestion Plan by Industry

For each industry, the plan identifies where to source compliance documents, how to fetch them, and how to process them for integration. Key endpoints (websites or databases), document formats, crawl frequency, and preprocessing notes are outlined below.

## Automotive

**Best Public Endpoints:**
* **NHTSA databases:** Recalls & Investigations (CSV/JSON/API).
* **Regulations:** FMVSS (eCFR HTML/XML), UNECE (PDF).
* **Enforcement:** NHTSA & DOJ press releases.

**Document Formats:** PDF (investigations, recalls), HTML (regulations), CSV/JSON (data feeds).

**Suggested Crawl Frequency:**
* Recalls/Investigations: **Weekly**
* Regulations: **Monthly**
* Enforcement: **Weekly**

**Pre-processing Notes:** Use APIs where possible. OCR for PDF investigation reports. Parse semi-structured recall text.

## Aerospace

**Best Public Endpoints:**
* **FAA:** Airworthiness Directives (PDF/Text), Advisory Circulars, Enforcement news.
* **NTSB:** Accident database.
* **Data Portals:** NASA ASRS.

**Document Formats:** PDF (ADs, reports), HTML (news), CSV (incident lists).

**Suggested Crawl Frequency:**
* Press releases/ASRS: **Weekly**
* ADs/Circulars: **Monthly**

**Pre-processing Notes:** NLP for accident reports. Custom parsers for AD sections.

## Gaming

**Best Public Endpoints:**
* **Regulators:** Nevada GCB, NJ DGE, UKGC, AUSTRAC.
* **Registries:** Licensee databases.
* **News:** Trade pubs.

**Document Formats:** HTML (news), PDF (decisions, minutes).

**Suggested Crawl Frequency:**
* Major sites: **Weekly**
* Broad search: **Monthly**

**Pre-processing Notes:** HTML parsing for snippets. Text extraction for meeting minutes. NLP to normalize terminology/fines.

## Food & Agriculture

**Best Public Endpoints:**
* **FDA:** Recalls, Enforcement Reports, Warning Letters.
* **USDA FSIS:** Recalls, Enforcement Reports.
* **CDC:** Outbreak alerts.

**Document Formats:** HTML (recalls, letters), PDF (FSIS reports), CSV (data feeds).

**Suggested Crawl Frequency:**
* Recalls/Warning Letters: **Weekly**
* FSIS Reports: **Monthly**
* Outbreaks: **Daily (during spikes)**

**Pre-processing Notes:** Use APIs/CSV where possible. OCR for older PDF warning letters. Map products/companies to entities.

## Energy

**Best Public Endpoints:**
* **FERC:** eLibrary (Orders), Enforcement Reports.
* **EPA:** ECHO database.
* **PHMSA:** Incident/Enforcement data.
* **NERC:** Penalty notices.

**Document Formats:** PDF (orders, notices), CSV/JSON (ECHO, PHMSA).

**Suggested Crawl Frequency:**
* FERC Press/Orders: **Weekly**
* Data Refreshes: **Monthly**

**Pre-processing Notes:** Prefer structured data (CSV). NLP for PDF orders to extract entity/penalty. Handle multi-part PDF attachments.

## Nuclear

**Best Public Endpoints:**
* **NRC:** ADAMS (public docs), Inspection Reports, LERs, Enforcement actions.
* **DOE:** Reports if public.

**Document Formats:** PDF (reports, LERs), HTML (summaries).

**Suggested Crawl Frequency:**
* Enforcement/News: **Weekly**
* Reports: **Monthly**

**Pre-processing Notes:** Heavy reliance on PDF parsing. Distinguish publicly available vs. sensitive info (avoid protected data).
