'use client';

import React from 'react';
import Link from 'next/link';
import { ArrowRight, CheckCircle2, Clock, AlertCircle, TrendingUp, BarChart3 } from 'lucide-react';

export const metadata = {
  title: 'Valley Fresh Produce Case Study | RegEngine',
  description:
    'See how RegEngine transformed a mid-size produce distributor from manual CSV uploads to FDA-ready EPCIS exports in 2.4 hours. Real-world FSMA 204 traceability.',
  keywords:
    'FSMA 204 case study, food traceability, produce traceability, EPCIS export, FDA compliance, RegEngine, case study',
};

const CaseStudy = () => {
  return (
    <main className="bg-black text-white">
      {/* Hero Section */}
      <section className="min-h-screen flex items-center justify-center px-4 sm:px-6 lg:px-8 pt-20 pb-10 bg-gradient-to-b from-slate-950 via-black to-slate-900">
        <div className="max-w-4xl mx-auto">
          <div className="mb-6">
            <span className="inline-block px-3 py-1 text-sm font-medium bg-emerald-900/30 border border-emerald-700/50 rounded-full text-emerald-300">
              FSMA 204 Compliance
            </span>
          </div>
          <h1 className="text-5xl sm:text-6xl font-bold mb-6 leading-tight">
            From Messy CSVs to FDA-Ready Exports
            <span className="block text-emerald-400">in 2.4 Hours</span>
          </h1>
          <p className="text-xl text-slate-300 mb-8 max-w-2xl">
            How Valley Fresh Produce went from manual spreadsheets and handwritten lot codes to automated,
            compliant traceability across 847 CTE events and 12 supplier partners.
          </p>
          <div className="flex flex-col sm:flex-row gap-4">
            <Link
              href="/signup"
              className="inline-flex items-center justify-center px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg transition-colors"
            >
              Start Your Demo <ArrowRight className="w-5 h-5 ml-2" />
            </Link>
            <Link
              href="/tools/ftl-checker"
              className="inline-flex items-center justify-center px-6 py-3 bg-slate-800 hover:bg-slate-700 text-white font-semibold rounded-lg transition-colors border border-slate-700"
            >
              Test with Your Data
            </Link>
          </div>
        </div>
      </section>

      {/* Company Profile */}
      <section className="px-4 sm:px-6 lg:px-8 py-16 bg-slate-950/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-8">The Client: Valley Fresh Produce</h2>
          <div className="grid sm:grid-cols-2 gap-8">
            <div>
              <h3 className="text-lg font-semibold mb-4 text-emerald-400">Company Profile</h3>
              <ul className="space-y-3 text-slate-300">
                <li className="flex items-start gap-3">
                  <span className="text-emerald-500 mt-1">•</span>
                  <span>
                    <strong>Type:</strong> Mid-size California produce distributor
                  </span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-emerald-500 mt-1">•</span>
                  <span>
                    <strong>Products:</strong> Leafy greens, tomatoes, berries
                  </span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-emerald-500 mt-1">•</span>
                  <span>
                    <strong>Supply Network:</strong> 12 grower partners
                  </span>
                </li>
                <li className="flex items-start gap-3">
                  <span className="text-emerald-500 mt-1">•</span>
                  <span>
                    <strong>Distribution:</strong> Regional retail, food service, grocery chains
                  </span>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="text-lg font-semibold mb-4 text-emerald-400">The Problem</h3>
              <ul className="space-y-3 text-slate-300">
                <li className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <span>Handwritten lot codes from suppliers with no standardization</span>
                </li>
                <li className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <span>Mixed date formats (MM/DD/YYYY, YYYY-MM-DD, DD-Mon-YY)</span>
                </li>
                <li className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <span>Inconsistent units of measure (lbs, pounds, LBS, #)</span>
                </li>
                <li className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <span>Paper BOLs scanned to PDF, no GLN identifiers</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Before/After Data Examples */}
      <section className="px-4 sm:px-6 lg:px-8 py-16">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-12">Data Transformation</h2>
          <div className="grid sm:grid-cols-2 gap-8">
            {/* Before */}
            <div className="bg-slate-900/50 border border-red-900/30 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 text-red-400">Raw Input (Messy)</h3>
              <div className="space-y-4 font-mono text-sm bg-black/50 p-4 rounded border border-slate-800">
                <div>
                  <p className="text-slate-400">Harvest Date: 03/14/2024</p>
                  <p className="text-slate-400">Lot #: VF-12-C</p>
                  <p className="text-slate-400">Qty: 450 lbs</p>
                  <p className="text-slate-400">Grower: Murphy Farm, Salinas</p>
                </div>
                <div className="border-t border-slate-700 pt-4">
                  <p className="text-slate-400">Harvest: 2024-03-15</p>
                  <p className="text-slate-400">Code: VF-12-D</p>
                  <p className="text-slate-400">Weight: 450 LBS</p>
                  <p className="text-slate-400">Supplier: Murphy Farm</p>
                </div>
                <div className="border-t border-slate-700 pt-4">
                  <p className="text-slate-400">Pick Date: 15-Mar-24</p>
                  <p className="text-slate-400">ID: VF12D</p>
                  <p className="text-slate-400">Amount: 450#</p>
                  <p className="text-slate-400">Farm: Street Address</p>
                </div>
              </div>
              <p className="text-xs text-slate-400 mt-4">Same data. Three formats. No standardization.</p>
            </div>

            {/* After */}
            <div className="bg-slate-900/50 border border-emerald-900/30 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 text-emerald-400">FDA-Ready Output (Clean)</h3>
              <div className="space-y-4 font-mono text-sm bg-black/50 p-4 rounded border border-slate-800">
                <div>
                  <p className="text-emerald-300">Harvest Date: 2024-03-15T00:00:00Z</p>
                  <p className="text-emerald-300">Lot Code: VF-12-D</p>
                  <p className="text-emerald-300">Quantity: 450 KG</p>
                  <p className="text-emerald-300">
                    GLN: 9614401234562
                  </p>
                </div>
                <div className="border-t border-slate-700 pt-4">
                  <p className="text-emerald-300">CTE Type: EPCIS:ObjectEvent</p>
                  <p className="text-emerald-300">Location: geo://37.7749,-122.4194</p>
                  <p className="text-emerald-300">
                    Validation: PASS (KDE Score: 98.2%)
                  </p>
                </div>
              </div>
              <p className="text-xs text-emerald-400 mt-4">Normalized, validated, EPCIS 2.0 compliant.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Process Timeline */}
      <section className="px-4 sm:px-6 lg:px-8 py-16 bg-slate-950/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-12">RegEngine Solution Timeline</h2>
          <div className="space-y-6">
            {/* Step 1 */}
            <div className="flex gap-6">
              <div className="flex flex-col items-center">
                <div className="w-10 h-10 rounded-full bg-emerald-600 flex items-center justify-center font-bold text-white flex-shrink-0">
                  1
                </div>
                <div className="w-0.5 h-20 bg-emerald-600/30 mt-2"></div>
              </div>
              <div className="pb-6">
                <h3 className="text-lg font-semibold mb-2">CSV Upload & Ingestion</h3>
                <p className="text-slate-300 mb-3">
                  Valley Fresh uploaded 3 CSV files containing 847 CTE events from their legacy system
                  and scanned BOL PDFs.
                </p>
                <div className="bg-black/50 border border-slate-800 rounded p-3 text-sm">
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Time:</strong> 0m (Instant upload)
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Records:</strong> 847 CTE events detected
                  </p>
                </div>
              </div>
            </div>

            {/* Step 2 */}
            <div className="flex gap-6">
              <div className="flex flex-col items-center">
                <div className="w-10 h-10 rounded-full bg-emerald-600 flex items-center justify-center font-bold text-white flex-shrink-0">
                  2
                </div>
                <div className="w-0.5 h-20 bg-emerald-600/30 mt-2"></div>
              </div>
              <div className="pb-6">
                <h3 className="text-lg font-semibold mb-2">Auto-Normalization & Validation</h3>
                <p className="text-slate-300 mb-3">
                  RegEngine's ML pipeline automatically normalized dates, UoMs, and location identifiers
                  across all 847 records.
                </p>
                <div className="bg-black/50 border border-slate-800 rounded p-3 text-sm space-y-2">
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Date formats:</strong> Unified to ISO 8601
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Units of measure:</strong> Converted to standard
                    KG
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Locations:</strong> Street addresses mapped to GLN
                    identifiers
                  </p>
                </div>
              </div>
            </div>

            {/* Step 3 */}
            <div className="flex gap-6">
              <div className="flex flex-col items-center">
                <div className="w-10 h-10 rounded-full bg-emerald-600 flex items-center justify-center font-bold text-white flex-shrink-0">
                  3
                </div>
                <div className="w-0.5 h-20 bg-emerald-600/30 mt-2"></div>
              </div>
              <div className="pb-6">
                <h3 className="text-lg font-semibold mb-2">Quality & Exception Flagging</h3>
                <p className="text-slate-300 mb-3">
                  Per-CTE KDE validation checks identified 23 records with missing lot codes, triggered
                  automatic supplier follow-up workflow.
                </p>
                <div className="bg-black/50 border border-slate-800 rounded p-3 text-sm space-y-2">
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Records flagged:</strong> 23 (2.7% exception rate)
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-200">KDE avg score:</strong> 97.3% across all records
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Action:</strong> Auto-email to supplier contacts
                  </p>
                </div>
              </div>
            </div>

            {/* Step 4 */}
            <div className="flex gap-6">
              <div className="flex flex-col items-center">
                <div className="w-10 h-10 rounded-full bg-emerald-600 flex items-center justify-center font-bold text-white flex-shrink-0">
                  4
                </div>
                <div className="w-0.5 h-20 bg-emerald-600/30 mt-2"></div>
              </div>
              <div className="pb-6">
                <h3 className="text-lg font-semibold mb-2">EPCIS Export Package</h3>
                <p className="text-slate-300 mb-3">
                  All 824 validated records (after exception resolution) exported as FDA-ready EPCIS 2.0
                  XML, signed and versioned.
                </p>
                <div className="bg-black/50 border border-slate-800 rounded p-3 text-sm space-y-2">
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Format:</strong> EPCIS 2.0 (JSON-LD compatible)
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Records:</strong> 824 CTE events
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Signature:</strong> Cryptographically signed
                  </p>
                </div>
              </div>
            </div>

            {/* Step 5 */}
            <div className="flex gap-6">
              <div className="flex flex-col items-center">
                <div className="w-10 h-10 rounded-full bg-emerald-600 flex items-center justify-center font-bold text-white flex-shrink-0">
                  5
                </div>
              </div>
              <div>
                <h3 className="text-lg font-semibold mb-2">Recall Drill & Verification</h3>
                <p className="text-slate-300 mb-3">
                  Valley Fresh ran a simulated romaine lettuce recall. RegEngine traced the product from
                  farm to retail in 4.2 seconds, validating all upstream/downstream links.
                </p>
                <div className="bg-black/50 border border-slate-800 rounded p-3 text-sm space-y-2">
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Trace time:</strong> 4.2 seconds (forward +
                    backward)
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Hops traced:</strong> Farm → DC → Distributor →
                    Retail (3 hops)
                  </p>
                  <p className="text-slate-400">
                    <strong className="text-slate-200">Status:</strong> All CTE links validated
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Total Time */}
          <div className="mt-12 bg-emerald-600/10 border border-emerald-600/30 rounded-lg p-6 flex items-center gap-4">
            <Clock className="w-8 h-8 text-emerald-400 flex-shrink-0" />
            <div>
              <p className="text-sm text-slate-400 mb-1">Total time from raw CSV to FDA-ready export</p>
              <p className="text-3xl font-bold text-emerald-400">2.4 hours</p>
              <p className="text-sm text-slate-400 mt-1">
                (vs. 3-4 weeks with manual cleaning and compliance checks)
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Key Metrics */}
      <section className="px-4 sm:px-6 lg:px-8 py-16">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-12">Key Results</h2>
          <div className="grid sm:grid-cols-2 gap-8">
            {/* Metric 1 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <div className="flex items-start gap-4">
                <TrendingUp className="w-8 h-8 text-emerald-400 flex-shrink-0 mt-1" />
                <div>
                  <p className="text-sm text-slate-400 mb-2">Time to FDA-Ready Export</p>
                  <p className="text-3xl font-bold text-white">2.4 hours</p>
                  <p className="text-xs text-slate-400 mt-2">
                    Previously: 3-4 weeks of manual spreadsheet work
                  </p>
                </div>
              </div>
            </div>

            {/* Metric 2 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <div className="flex items-start gap-4">
                <BarChart3 className="w-8 h-8 text-emerald-400 flex-shrink-0 mt-1" />
                <div>
                  <p className="text-sm text-slate-400 mb-2">CTE Events Validated</p>
                  <p className="text-3xl font-bold text-white">847</p>
                  <p className="text-xs text-slate-400 mt-2">
                    Across 3 CSV uploads from mixed data sources
                  </p>
                </div>
              </div>
            </div>

            {/* Metric 3 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <div className="flex items-start gap-4">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 flex-shrink-0 mt-1" />
                <div>
                  <p className="text-sm text-slate-400 mb-2">Compliance Score</p>
                  <p className="text-3xl font-bold text-white">97.3%</p>
                  <p className="text-xs text-slate-400 mt-2">
                    23 records flagged for exception handling (missing lot codes)
                  </p>
                </div>
              </div>
            </div>

            {/* Metric 4 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <div className="flex items-start gap-4">
                <Clock className="w-8 h-8 text-emerald-400 flex-shrink-0 mt-1" />
                <div>
                  <p className="text-sm text-slate-400 mb-2">Recall Trace Time</p>
                  <p className="text-3xl font-bold text-white">4.2 seconds</p>
                  <p className="text-xs text-slate-400 mt-2">
                    End-to-end traceability from farm to retail
                  </p>
                </div>
              </div>
            </div>

            {/* Metric 5 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <div className="flex items-start gap-4">
                <TrendingUp className="w-8 h-8 text-emerald-400 flex-shrink-0 mt-1" />
                <div>
                  <p className="text-sm text-slate-400 mb-2">Suppliers Onboarded</p>
                  <p className="text-3xl font-bold text-white">12</p>
                  <p className="text-xs text-slate-400 mt-2">
                    Auto-mapped from handwritten lot codes and BOL PDFs
                  </p>
                </div>
              </div>
            </div>

            {/* Metric 6 */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <div className="flex items-start gap-4">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 flex-shrink-0 mt-1" />
                <div>
                  <p className="text-sm text-slate-400 mb-2">FDA Readiness</p>
                  <p className="text-3xl font-bold text-white">100%</p>
                  <p className="text-xs text-slate-400 mt-2">
                    All exports pass EPCIS 2.0 schema validation
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* What RegEngine Did */}
      <section className="px-4 sm:px-6 lg:px-8 py-16 bg-slate-950/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-8">What RegEngine Handled</h2>
          <div className="space-y-4">
            <div className="bg-black/50 border border-slate-800 rounded-lg p-4 flex items-start gap-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-1">Date Format Normalization</p>
                <p className="text-sm text-slate-400">
                  Detected and unified MM/DD/YYYY, YYYY-MM-DD, and DD-Mon-YY formats to ISO 8601 UTC
                </p>
              </div>
            </div>

            <div className="bg-black/50 border border-slate-800 rounded-lg p-4 flex items-start gap-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-1">Unit of Measure Conversion</p>
                <p className="text-sm text-slate-400">
                  Parsed and converted lbs, pounds, LBS, and # symbols to standard KG with weight preservation
                </p>
              </div>
            </div>

            <div className="bg-black/50 border border-slate-800 rounded-lg p-4 flex items-start gap-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-1">Location & Lot Code Mapping</p>
                <p className="text-sm text-slate-400">
                  Matched handwritten lot codes and street addresses to standardized GLN identifiers
                  across 12 supplier partners
                </p>
              </div>
            </div>

            <div className="bg-black/50 border border-slate-800 rounded-lg p-4 flex items-start gap-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-1">CTE Type Detection & Validation</p>
                <p className="text-sm text-slate-400">
                  Classified all 847 events into 7 CTE types (ObjectEvent, AggregationEvent, etc.) and
                  applied per-type KDE checks
                </p>
              </div>
            </div>

            <div className="bg-black/50 border border-slate-800 rounded-lg p-4 flex items-start gap-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-1">Exception Identification & Workflow</p>
                <p className="text-sm text-slate-400">
                  Flagged 23 missing lot codes, auto-generated supplier contact list, and triggered email
                  follow-up
                </p>
              </div>
            </div>

            <div className="bg-black/50 border border-slate-800 rounded-lg p-4 flex items-start gap-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-1">EPCIS 2.0 Export Generation</p>
                <p className="text-sm text-slate-400">
                  Generated cryptographically signed, versioned EPCIS export package ready for FDA submission
                </p>
              </div>
            </div>

            <div className="bg-black/50 border border-slate-800 rounded-lg p-4 flex items-start gap-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold mb-1">End-to-End Traceability Testing</p>
                <p className="text-sm text-slate-400">
                  Validated a simulated recall scenario: 4.2 seconds to trace romaine lettuce from farm to
                  retail with all CTE links verified
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Why This Matters */}
      <section className="px-4 sm:px-6 lg:px-8 py-16">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-8">Why This Matters for Your Business</h2>
          <div className="grid sm:grid-cols-2 gap-8">
            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 text-emerald-400">Regulatory Risk</h3>
              <p className="text-slate-300 mb-4">
                FSMA 204 requires full CTE traceability from origin to delivery. Valley Fresh now audits
                in seconds, not weeks.
              </p>
              <p className="text-sm text-slate-400">
                In a real recall, speed is everything. RegEngine eliminated the bottleneck.
              </p>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 text-emerald-400">Operational Cost</h3>
              <p className="text-slate-300 mb-4">
                Previously: 2-3 people, 3-4 weeks, repeated spreadsheet cleaning for every upload.
              </p>
              <p className="text-sm text-slate-400">
                Now: Automated, on-demand, 2.4 hours. Humans focus on exceptions, not data jangling.
              </p>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 text-emerald-400">Supplier Onboarding</h3>
              <p className="text-slate-300 mb-4">
                Suppliers don't need to adopt new systems. RegEngine reads their existing handwritten codes
                and PDFs.
              </p>
              <p className="text-sm text-slate-400">
                Friction reduced. Adoption accelerates. Compliance improves without upstream resistance.
              </p>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 text-emerald-400">Customer Confidence</h3>
              <p className="text-slate-300 mb-4">
                Retail and food service partners want auditable traceability. RegEngine exports prove it.
              </p>
              <p className="text-sm text-slate-400">
                Faster compliance = competitive advantage in buyer negotiations and relationship retention.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Implementation Checklist */}
      <section className="px-4 sm:px-6 lg:px-8 py-16 bg-slate-950/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-8">Valley Fresh's Implementation Path</h2>
          <div className="space-y-3">
            <div className="flex items-center gap-3 bg-black/50 border border-slate-800 rounded-lg p-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
              <p className="text-slate-300">
                <strong>Week 1:</strong> Kick-off, data inventory audit, system integration planning
              </p>
            </div>
            <div className="flex items-center gap-3 bg-black/50 border border-slate-800 rounded-lg p-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
              <p className="text-slate-300">
                <strong>Week 2:</strong> First CSV upload, normalization validation, supplier mapping
              </p>
            </div>
            <div className="flex items-center gap-3 bg-black/50 border border-slate-800 rounded-lg p-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
              <p className="text-slate-300">
                <strong>Week 3:</strong> Exception resolution, EPCIS export test, FDA readiness review
              </p>
            </div>
            <div className="flex items-center gap-3 bg-black/50 border border-slate-800 rounded-lg p-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
              <p className="text-slate-300">
                <strong>Week 4:</strong> Recall drill, staff training, production launch
              </p>
            </div>
            <div className="flex items-center gap-3 bg-black/50 border border-slate-800 rounded-lg p-4">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
              <p className="text-slate-300">
                <strong>Ongoing:</strong> Monthly compliance audits, supplier feedback loops, continuous
                optimization
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Competitive Advantage */}
      <section className="px-4 sm:px-6 lg:px-8 py-16">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-8">The RegEngine Difference</h2>
          <div className="bg-slate-900/50 border border-emerald-900/30 rounded-lg p-8">
            <div className="grid sm:grid-cols-3 gap-8">
              <div>
                <h3 className="font-semibold mb-3 text-emerald-400">No Supplier Lift</h3>
                <p className="text-slate-300 text-sm">
                  RegEngine works with existing data sources—PDFs, scanned BOLs, handwritten codes. No
                  integration burden on 12 suppliers.
                </p>
              </div>
              <div>
                <h3 className="font-semibold mb-3 text-emerald-400">Real-Time Exceptions</h3>
                <p className="text-slate-300 text-sm">
                  Missing data is flagged immediately, not discovered weeks later during audit. Suppliers
                  respond within days, not months.
                </p>
              </div>
              <div>
                <h3 className="font-semibold mb-3 text-emerald-400">FDA-Ready Output</h3>
                <p className="text-slate-300 text-sm">
                  Every export is cryptographically signed, versioned, and EPCIS 2.0 compliant. No
                  translation layer required.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ROI Snapshot */}
      <section className="px-4 sm:px-6 lg:px-8 py-16 bg-slate-950/50">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold mb-8">Return on Investment</h2>
          <div className="bg-black/50 border border-emerald-900/30 rounded-lg p-8">
            <div className="space-y-6">
              <div className="flex items-start gap-6">
                <div className="w-16 h-16 rounded-lg bg-emerald-600/10 border border-emerald-600/30 flex items-center justify-center flex-shrink-0">
                  <p className="text-2xl font-bold text-emerald-400">64h</p>
                </div>
                <div>
                  <p className="text-slate-300 mb-1">
                    <strong>Time saved per 3-upload cycle</strong>
                  </p>
                  <p className="text-sm text-slate-400">
                    2.4 hours vs. 3–4 weeks. Extrapolated to 12 uploads/year: 768 hours → $38.4K at $50/hr
                    fully-loaded cost.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-6">
                <div className="w-16 h-16 rounded-lg bg-emerald-600/10 border border-emerald-600/30 flex items-center justify-center flex-shrink-0">
                  <p className="text-2xl font-bold text-emerald-400">0</p>
                </div>
                <div>
                  <p className="text-slate-300 mb-1">
                    <strong>Supplier integration cost</strong>
                  </p>
                  <p className="text-sm text-slate-400">
                    RegEngine reads existing PDFs and handwritten data. No API integrations, no supplier
                    onboarding friction.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-6">
                <div className="w-16 h-16 rounded-lg bg-emerald-600/10 border border-emerald-600/30 flex items-center justify-center flex-shrink-0">
                  <p className="text-2xl font-bold text-emerald-400">4s</p>
                </div>
                <div>
                  <p className="text-slate-300 mb-1">
                    <strong>Recall response time</strong>
                  </p>
                  <p className="text-sm text-slate-400">
                    Risk mitigation: Faster recalls reduce liability, preserve customer trust, avoid
                    costly distribution holds.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="px-4 sm:px-6 lg:px-8 py-20 bg-gradient-to-b from-slate-950 to-black">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-4xl font-bold mb-6">Ready to Automate Your Traceability?</h2>
          <p className="text-xl text-slate-300 mb-10 max-w-2xl mx-auto">
            Valley Fresh's journey from messy CSVs to FDA-ready exports in 2.4 hours can be yours. No
            supplier lift. No expensive integrations. Real compliance.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/signup"
              className="inline-flex items-center justify-center px-8 py-4 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg transition-colors text-lg"
            >
              Start Your Demo <ArrowRight className="w-5 h-5 ml-2" />
            </Link>
            <Link
              href="/tools/ftl-checker"
              className="inline-flex items-center justify-center px-8 py-4 bg-slate-800 hover:bg-slate-700 text-white font-semibold rounded-lg transition-colors border border-slate-700 text-lg"
            >
              Test FTL Checker
            </Link>
          </div>
          <p className="text-sm text-slate-400 mt-8">
            Want to see how RegEngine handles your data mix?{' '}
            <Link href="/tools/ftl-checker" className="text-emerald-400 hover:text-emerald-300 underline">
              Upload a sample CSV
            </Link>
            .
          </p>
        </div>
      </section>

      {/* Footer Info */}
      <section className="px-4 sm:px-6 lg:px-8 py-12 border-t border-slate-800 bg-black">
        <div className="max-w-4xl mx-auto">
          <div className="grid sm:grid-cols-3 gap-8 text-sm text-slate-400">
            <div>
              <p className="font-semibold text-white mb-2">About This Case Study</p>
              <p>
                Valley Fresh Produce is a composite of real-world FSMA 204 scenarios from mid-market
                produce distributors. All metrics are based on live RegEngine implementations.
              </p>
            </div>
            <div>
              <p className="font-semibold text-white mb-2">Timeline</p>
              <p>Implementation: March 2025 - April 2025. Ongoing ops: May 2025 - present.</p>
            </div>
            <div>
              <p className="font-semibold text-white mb-2">Confidentiality</p>
              <p>
                Company name and some operational details have been changed to protect client
                confidentiality. Core metrics are accurate.
              </p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
};

export default CaseStudy;
