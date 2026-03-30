'use client';

/**
 * Lazy-loads jspdf (already used for branded reports) to generate label PDFs.
 * Removed @react-pdf/renderer dependency — consolidating to a single PDF library.
 */

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { FileDown, Loader2 } from 'lucide-react';
import type { LabelData } from '@/types/labels';

interface LabelPdfDownloadSectionProps {
  labels: LabelData[];
  productName: string;
  batchId: string;
}

function extractGTIN(payload: string): string {
  const match = payload.match(/\/01\/(\d{14})/);
  return match ? match[1] : 'N/A';
}

export default function LabelPdfDownloadSection({
  labels,
  productName,
  batchId,
}: LabelPdfDownloadSectionProps) {
  const [generating, setGenerating] = useState(false);

  async function handleDownload() {
    setGenerating(true);
    try {
      const [{ default: jsPDF }, { default: QRCode }] = await Promise.all([
        import('jspdf'),
        import('qrcode'),
      ]);

      // Letter page in mm; ~2" x 2" labels with 3mm gap
      const PAGE_W = 215.9;
      const PAGE_H = 279.4;
      const MARGIN = 7;
      const LABEL_W = 50;
      const LABEL_H = 50;
      const GAP = 3;

      const cols = Math.floor((PAGE_W - 2 * MARGIN + GAP) / (LABEL_W + GAP));
      const rows = Math.floor((PAGE_H - 2 * MARGIN + GAP) / (LABEL_H + GAP));
      const labelsPerPage = cols * rows;

      const doc = new jsPDF({ unit: 'mm', format: 'letter' });

      for (let i = 0; i < labels.length; i++) {
        const posOnPage = i % labelsPerPage;

        if (posOnPage === 0 && i > 0) {
          doc.addPage();
        }

        const col = posOnPage % cols;
        const row = Math.floor(posOnPage / cols);
        const x = MARGIN + col * (LABEL_W + GAP);
        const y = MARGIN + row * (LABEL_H + GAP);
        const label = labels[i];

        // Border
        doc.setDrawColor(200, 200, 200);
        doc.setLineWidth(0.3);
        doc.rect(x, y, LABEL_W, LABEL_H);

        // Product name
        doc.setFontSize(7);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(0, 0, 0);
        const nameLines = doc.splitTextToSize(productName, LABEL_W - 4);
        doc.text(nameLines, x + LABEL_W / 2, y + 5, { align: 'center' });

        // QR code image (~22mm square, centered)
        const qrDataUrl = await QRCode.toDataURL(label.qr_payload, { width: 120, margin: 0 });
        const qrX = x + (LABEL_W - 22) / 2;
        doc.addImage(qrDataUrl, 'PNG', qrX, y + 11, 22, 22);

        // Serial number
        doc.setFontSize(5.5);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(40, 40, 40);
        const serial = label.serial.length > 28 ? label.serial.slice(-28) : label.serial;
        doc.text(serial, x + LABEL_W / 2, y + 37, { align: 'center', maxWidth: LABEL_W - 2 });

        // GTIN
        const gtin = extractGTIN(label.qr_payload);
        doc.setTextColor(100, 100, 100);
        doc.text(`GTIN: ${gtin}`, x + LABEL_W / 2, y + 42, { align: 'center', maxWidth: LABEL_W - 2 });
      }

      doc.save(`labels-${batchId}.pdf`);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Button className="flex-1" onClick={handleDownload} disabled={generating}>
      {generating ? (
        <>
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Generating PDF...
        </>
      ) : (
        <>
          <FileDown className="mr-2 h-4 w-4" />
          Download PDF (Click &amp; Print)
        </>
      )}
    </Button>
  );
}
