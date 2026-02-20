# The Handoff Problem: Why Your Lot Code Dies at the Loading Dock

**Under FSMA 204, every custody transfer is a data cliff. Most supply chains aren't ready for it.**

---

Picture a Tuesday morning at a regional distribution center. Two hundred pallets rolling in from six suppliers before noon. Each one has a lot code — somewhere. Maybe it's on the BOL. Maybe it's printed on the case in a format your WMS can't parse. Maybe it's in an email your receiving clerk hasn't opened yet.

Now picture the FDA calling that afternoon: "We need all traceability records for product X, lot range Y, for the last 90 days. You have 24 hours."

That's the scenario FSMA 204 was designed for. And the reason most operations will struggle with it has nothing to do with software — it's what happens to data every time product changes hands.

---

## How "One-Up, One-Back" Created a Data Cliff Culture

Before FSMA 204, the federal standard for food traceability was simple: know who you got it from, know who you sent it to. That was the Bioterrorism Act's "one-up, one-back" requirement, and it's been the law since 2002.

It worked — barely — for its intended purpose. But it created a culture where traceability data only needed to survive one handoff in each direction. Your lot code only had to make sense to *you* and your immediate trading partner. What happened three nodes upstream? Not your problem.

FSMA 204 changed the game. The rule requires end-to-end traceability for foods on the Food Traceability List — from the field or fishing vessel through every shipping, receiving, and transformation event, all the way to retail or foodservice. The data doesn't just need to exist at each node. It needs to *link* across nodes through a common thread: the Traceability Lot Code.

And that's where things break.

---

## The TLC Definition Gap: "Unique" Doesn't Mean What You Think

FDA defines a Traceability Lot Code as "a descriptor, often alphanumeric, used to uniquely identify a traceability lot within the records of the firm that assigned the traceability lot code."

Read that carefully. The TLC must be unique *within the assigning firm's records*. But FSMA 204 requires that TLC to travel through the entire supply chain — across firms with different systems, different conventions, and different definitions of "unique."

Here's what lot codes actually look like in the wild:

- **Farm A** uses Julian date + field number: `122-F3` (May 2nd, Field 3)
- **Packer B** uses sequential production numbers: `PKG-2025-04417`
- **Distributor C** uses their ERP's auto-generated ID: `7891234`
- **Processor D** uses facility code + line + shift: `PHX-L2-N-0502`

Each of these is "unique" within its own operation. None of them is inherently meaningful to the next company in the chain. And when Processor D transforms Farm A's tomatoes and Packer B's onions into pico de gallo, they assign a *new* TLC — but must maintain linkage to every input TLC.

FDA acknowledged this problem during the rulemaking process. Industry commenters pointed out that supply chain systems are not fully interoperable, and a TLC designated at the beginning of the supply chain may not be compatible with downstream systems. FDA's response was essentially: interoperability isn't strictly necessary to exchange TLC information.

Technically true. Operationally brutal.

---

## The GS1 Almost-Solution

The closest thing the industry has to a common language is GS1 standards — specifically, using a Global Trade Item Number (GTIN) plus a lot/batch code to construct a globally unique TLC. Industry workgroups recommend this approach, and it's the backbone of the Produce Traceability Initiative's FSMA 204 guidance.

But adoption is nowhere near universal. Many software systems in the food industry can't track inventory by lot code at all. Among those that can handle GS1-128 barcodes, many can't parse them automatically — they require manual intervention to extract the lot code, weights, production dates, and other data elements. And when a non-standard code arrives? Most systems have no fallback logic.

This means the GS1 standard is the *right answer* for companies that can implement it, but it doesn't solve the problem for the thousands of small and mid-size operators who are still running on spreadsheets, paper BOLs, and email attachments.

---

## The Trade Sensitivity Wrinkle

FSMA 204 requires that when you ship product, you provide the TLC *and* the TLC source — the location where that lot code was originally assigned. For a grower shipping to a packer, that's straightforward. But for a distributor shipping to a retailer, revealing the TLC source means revealing who your upstream supplier is. And in the food industry, supplier relationships are closely guarded.

FDA created a workaround: the TLC Source Reference. Instead of sharing the actual source location, you can share an FDA Food Facility Registration Number, a URL, or another unique identifier that FDA can use to look up the source during an investigation — without exposing it to your trading partners.

It's a reasonable compromise. It's also another data element that must be maintained, transmitted accurately at every handoff, and retrievable within 24 hours. Every workaround adds complexity, and complexity is where handoffs fail.

---

## Where Handoffs Actually Break

Based on the rule's requirements and real-world supply chain operations, here are the most common failure points when product changes custody:

**1. The TLC doesn't travel with the product.**
The lot code exists in the shipper's system but isn't on the physical case, the ASN, or the BOL. The receiver has no way to capture it at the dock.

**2. The TLC arrives in an unparseable format.**
The barcode is there, but the receiver's system can't decode it — wrong symbology, missing application identifiers, or simply a format the WMS wasn't configured to handle.

**3. KDEs are split across multiple documents.**
The TLC is on the case label. The quantity is on the BOL. The ship date is in the ASN. The TLC source reference is in an email from last week. Assembling a complete record requires manual stitching across formats and systems.

**4. Transformation breaks the chain.**
When inputs are combined into a new product, the processor must assign a new TLC and link it to all input TLCs. If any input arrived without a clean TLC, the linkage is broken from that point backward.

**5. The 24-hour clock exposes everything.**
All of these problems are manageable in normal operations — you can chase down missing data, call suppliers, dig through emails. But FSMA 204's 24-hour retrieval mandate means you need records assembled and sortable *before* the phone rings. There's no time to reconstruct what should have been captured at the dock.

---

## Diagnosing Your Handoff Readiness

The good news is that each of these failure points is identifiable — and fixable — before the July 2028 enforcement floor arrives.

We built a set of free diagnostic tools specifically for this:

- **[TLC Quality Check](/tools/tlc-validator)** — Paste in your lot codes and see whether they're robust enough to survive the supply chain: uniqueness, parseability, date/facility components, GS1 compatibility.

- **[KDE Completeness Checker](/tools/kde-checker)** — Select your role in the supply chain and see exactly which data elements you need to *maintain* vs. *provide* to trading partners at each Critical Tracking Event.

- **[CTE Coverage Mapper](/tools/cte-mapper)** — Map your supply chain nodes and see which CTEs apply at each handoff, plus the "who owes what to whom" data exchange requirements.

- **[Recall Readiness Score](/tools/recall-readiness)** — A 2-minute assessment that grades your ability to respond to an FDA records request within 24 hours.

Each tool takes 2–5 minutes and gives you an immediate diagnostic. No login required.

---

## The Operational Reality

FSMA 204 didn't create the handoff problem. It exposed it. The food industry has been running on relationship-based, informal data exchange for decades — and it mostly worked because no one was stress-testing the data.

The 24-hour retrieval mandate is that stress test. And the companies that will pass it are the ones that treat every custody transfer as a data event, not just a physical one.

The lot code doesn't need to be perfect. It needs to be *capturable, linkable, and retrievable* — at every handoff, in every direction, within 24 hours.

That's the standard. July 2028 is the deadline. The loading dock is where it starts.

---

*RegEngine builds traceability infrastructure for food operators navigating FSMA 204. [Run your free readiness diagnostic →](/tools)*
