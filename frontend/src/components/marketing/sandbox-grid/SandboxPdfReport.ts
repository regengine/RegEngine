/**
 * Branded PDF compliance report generator using jsPDF + jspdf-autotable.
 *
 * Generates a professional FSMA 204 compliance assessment PDF with:
 *  - Executive summary with compliance score
 *  - Detailed findings table (failures + warnings)
 *  - Normalization diff (if available)
 *  - RegEngine branding and call-to-action
 */

import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

// ---------------------------------------------------------------------------
// Types (mirrors SandboxUpload interfaces)
// ---------------------------------------------------------------------------

interface RuleResult {
  rule_title: string;
  severity: string;
  result: string;
  why_failed: string | null;
  citation: string | null;
  remediation: string | null;
  category: string;
}

interface EventEvaluation {
  event_index: number;
  cte_type: string;
  traceability_lot_code: string;
  product_description: string;
  kde_errors: string[];
  rules_evaluated: number;
  rules_passed: number;
  rules_failed: number;
  rules_warned: number;
  compliant: boolean;
  all_results: RuleResult[];
}

interface NormalizationAction {
  field: string;
  original: string;
  normalized: string;
  action_type: string;
}

interface SandboxResult {
  total_events: number;
  compliant_events: number;
  non_compliant_events: number;
  total_kde_errors: number;
  total_rule_failures: number;
  submission_blocked: boolean;
  blocking_reasons: string[];
  events: EventEvaluation[];
  normalizations?: NormalizationAction[];
}

// ---------------------------------------------------------------------------
// Colors
// ---------------------------------------------------------------------------

const BRAND = { r: 79, g: 70, b: 229 };      // indigo-600
const DANGER = { r: 220, g: 38, b: 38 };      // red-600
const WARNING = { r: 217, g: 119, b: 6 };     // amber-600
const SUCCESS = { r: 22, g: 163, b: 74 };     // green-600
const GRAY = { r: 107, g: 114, b: 128 };      // gray-500
const LIGHT_GRAY = { r: 243, g: 244, b: 246 };// gray-100

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(numerator: number, denominator: number): string {
  if (denominator === 0) return '0%';
  return `${Math.round((numerator / denominator) * 100)}%`;
}

function truncate(str: string, max: number): string {
  if (str.length <= max) return str;
  return str.slice(0, max - 1) + '\u2026';
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function generateComplianceReport(result: SandboxResult): void {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 15;
  const contentWidth = pageWidth - margin * 2;
  const now = new Date().toLocaleString();
  let y = margin;

  // ---- Header bar ----
  doc.setFillColor(BRAND.r, BRAND.g, BRAND.b);
  doc.rect(0, 0, pageWidth, 22, 'F');
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(16);
  doc.setTextColor(255, 255, 255);
  doc.text('RegEngine', margin, 14);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(10);
  doc.text('FSMA 204 Compliance Assessment', pageWidth - margin, 10, { align: 'right' });
  doc.setFontSize(8);
  doc.text(now, pageWidth - margin, 16, { align: 'right' });
  y = 30;

  // ---- Compliance score ----
  const score = pct(result.compliant_events, result.total_events);
  const scoreColor = result.compliant_events === result.total_events ? SUCCESS
    : result.non_compliant_events > result.total_events / 2 ? DANGER : WARNING;

  doc.setFontSize(28);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(scoreColor.r, scoreColor.g, scoreColor.b);
  doc.text(score, margin, y + 10);

  doc.setFontSize(10);
  doc.setTextColor(GRAY.r, GRAY.g, GRAY.b);
  doc.text('Compliance Score', margin + 32, y + 4);
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.text(
    `${result.compliant_events} of ${result.total_events} events passed all rules`,
    margin + 32, y + 10,
  );
  y += 20;

  // ---- Summary stats boxes ----
  const boxWidth = (contentWidth - 9) / 4;
  const stats = [
    { label: 'Total Events', value: String(result.total_events), color: GRAY },
    { label: 'Compliant', value: String(result.compliant_events), color: SUCCESS },
    { label: 'Non-Compliant', value: String(result.non_compliant_events), color: DANGER },
    { label: 'Rule Failures', value: String(result.total_rule_failures), color: WARNING },
  ];

  for (let i = 0; i < stats.length; i++) {
    const x = margin + i * (boxWidth + 3);
    doc.setFillColor(LIGHT_GRAY.r, LIGHT_GRAY.g, LIGHT_GRAY.b);
    doc.roundedRect(x, y, boxWidth, 18, 2, 2, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(14);
    doc.setTextColor(stats[i].color.r, stats[i].color.g, stats[i].color.b);
    doc.text(stats[i].value, x + boxWidth / 2, y + 9, { align: 'center' });
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(7);
    doc.setTextColor(GRAY.r, GRAY.g, GRAY.b);
    doc.text(stats[i].label, x + boxWidth / 2, y + 15, { align: 'center' });
  }
  y += 24;

  // ---- Blocking banner ----
  if (result.submission_blocked) {
    doc.setFillColor(254, 242, 242);
    doc.setDrawColor(DANGER.r, DANGER.g, DANGER.b);
    doc.roundedRect(margin, y, contentWidth, 14, 2, 2, 'FD');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(9);
    doc.setTextColor(DANGER.r, DANGER.g, DANGER.b);
    doc.text(
      `FDA SUBMISSION BLOCKED \u2014 ${result.blocking_reasons.length} critical defect${result.blocking_reasons.length !== 1 ? 's' : ''}`,
      margin + 4, y + 6,
    );
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(7);
    const topReasons = result.blocking_reasons.slice(0, 3).join('; ');
    doc.text(truncate(topReasons, 120), margin + 4, y + 11);
    y += 18;
  }

  // ---- Detailed findings table ----
  const findings: string[][] = [];
  for (const ev of result.events) {
    // KDE errors
    for (const err of ev.kde_errors) {
      findings.push([
        String(ev.event_index + 1),
        truncate(ev.traceability_lot_code, 18),
        ev.cte_type,
        'KDE Error',
        truncate(err, 60),
        '',
      ]);
    }
    // Rule failures and warnings
    for (const r of ev.all_results) {
      if (r.result !== 'fail' && r.result !== 'warn') continue;
      findings.push([
        String(ev.event_index + 1),
        truncate(ev.traceability_lot_code, 18),
        ev.cte_type,
        r.severity === 'critical' ? 'Critical' : r.result === 'warn' ? 'Warning' : 'Failure',
        truncate(r.rule_title, 40),
        r.citation ? truncate(r.citation, 20) : '',
      ]);
    }
  }

  if (findings.length > 0) {
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(11);
    doc.setTextColor(30, 30, 30);
    doc.text('Detailed Findings', margin, y + 6);
    y += 10;

    autoTable(doc, {
      startY: y,
      head: [['#', 'Lot Code', 'CTE Type', 'Severity', 'Issue', 'Citation']],
      body: findings,
      margin: { left: margin, right: margin },
      styles: { fontSize: 7, cellPadding: 2 },
      headStyles: {
        fillColor: [BRAND.r, BRAND.g, BRAND.b],
        textColor: 255,
        fontStyle: 'bold',
      },
      columnStyles: {
        0: { cellWidth: 8 },
        1: { cellWidth: 28 },
        2: { cellWidth: 24 },
        3: { cellWidth: 18 },
        4: { cellWidth: 'auto' },
        5: { cellWidth: 28 },
      },
      didParseCell(data) {
        if (data.section === 'body' && data.column.index === 3) {
          const val = String(data.cell.raw);
          if (val === 'Critical' || val === 'KDE Error') {
            data.cell.styles.textColor = [DANGER.r, DANGER.g, DANGER.b];
            data.cell.styles.fontStyle = 'bold';
          } else if (val === 'Warning') {
            data.cell.styles.textColor = [WARNING.r, WARNING.g, WARNING.b];
          }
        }
      },
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    y = (doc as any).lastAutoTable.finalY + 6;
  }

  // ---- Normalization diff ----
  if (result.normalizations && result.normalizations.length > 0) {
    // Check if we need a new page
    if (y > 240) {
      doc.addPage();
      y = margin;
    }

    doc.setFont('helvetica', 'bold');
    doc.setFontSize(11);
    doc.setTextColor(30, 30, 30);
    doc.text('What RegEngine Normalized', margin, y + 6);
    y += 10;

    const normRows = result.normalizations.map((n) => [
      n.action_type === 'header_alias' ? 'Header'
        : n.action_type === 'uom_normalize' ? 'Unit'
        : n.action_type === 'cte_type_normalize' ? 'CTE Type'
        : n.action_type,
      n.original,
      '\u2192',
      n.normalized,
      n.field,
    ]);

    autoTable(doc, {
      startY: y,
      head: [['Type', 'Your Data', '', 'Cleaned', 'Field']],
      body: normRows,
      margin: { left: margin, right: margin },
      styles: { fontSize: 7, cellPadding: 2 },
      headStyles: {
        fillColor: [BRAND.r, BRAND.g, BRAND.b],
        textColor: 255,
        fontStyle: 'bold',
      },
      columnStyles: {
        0: { cellWidth: 18 },
        1: { cellWidth: 40 },
        2: { cellWidth: 8, halign: 'center' },
        3: { cellWidth: 40 },
        4: { cellWidth: 'auto' },
      },
      didParseCell(data) {
        if (data.section === 'body') {
          if (data.column.index === 1) {
            data.cell.styles.textColor = [DANGER.r, DANGER.g, DANGER.b];
            data.cell.styles.fontStyle = 'bold';
          } else if (data.column.index === 3) {
            data.cell.styles.textColor = [SUCCESS.r, SUCCESS.g, SUCCESS.b];
            data.cell.styles.fontStyle = 'bold';
          }
        }
      },
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    y = (doc as any).lastAutoTable.finalY + 6;
  }

  // ---- Passed events summary ----
  const passedEvents = result.events.filter((ev) => ev.compliant);
  if (passedEvents.length > 0 && passedEvents.length < result.total_events) {
    if (y > 250) {
      doc.addPage();
      y = margin;
    }

    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor(SUCCESS.r, SUCCESS.g, SUCCESS.b);
    const passedTlcs = passedEvents.slice(0, 10).map((e) => e.traceability_lot_code).join(', ');
    doc.text(
      `\u2713 ${passedEvents.length} event${passedEvents.length !== 1 ? 's' : ''} fully compliant: ${truncate(passedTlcs, 100)}`,
      margin, y,
    );
    y += 8;
  }

  // ---- Footer on every page ----
  const totalPages = doc.getNumberOfPages();
  for (let p = 1; p <= totalPages; p++) {
    doc.setPage(p);
    const pageH = doc.internal.pageSize.getHeight();
    doc.setDrawColor(BRAND.r, BRAND.g, BRAND.b);
    doc.line(margin, pageH - 14, pageWidth - margin, pageH - 14);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(7);
    doc.setTextColor(GRAY.r, GRAY.g, GRAY.b);
    doc.text('Generated by RegEngine \u2014 www.regengine.co', margin, pageH - 9);
    doc.text(`Page ${p} of ${totalPages}`, pageWidth - margin, pageH - 9, { align: 'right' });
    doc.setFontSize(7);
    doc.setTextColor(BRAND.r, BRAND.g, BRAND.b);
    doc.text(
      'Ready to automate compliance? Visit regengine.co/demo',
      pageWidth / 2, pageH - 9, { align: 'center' },
    );
  }

  doc.save('RegEngine-FSMA204-Report.pdf');
}
