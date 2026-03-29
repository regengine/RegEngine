'use client';

/**
 * Wrapper that lazy-loads @react-pdf/renderer and LabelPdfDocument.
 *
 * Keeps the ~500KB @react-pdf/renderer bundle out of the main chunk;
 * it is only downloaded when this component mounts (i.e. after label
 * generation succeeds).
 */

import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { FileDown, Loader2 } from 'lucide-react';
import type { LabelData } from '@/types/labels';

interface LabelPdfDownloadSectionProps {
  labels: LabelData[];
  productName: string;
  batchId: string;
}

export default function LabelPdfDownloadSection({
  labels,
  productName,
  batchId,
}: LabelPdfDownloadSectionProps) {
  const [PdfModule, setPdfModule] = useState<{
    PDFDownloadLink: typeof import('@react-pdf/renderer').PDFDownloadLink;
    LabelPdfDocument: typeof import('@/components/labels/LabelPdfDocument').LabelPdfDocument;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      import('@react-pdf/renderer'),
      import('@/components/labels/LabelPdfDocument'),
    ]).then(([pdfRenderer, labelDoc]) => {
      if (!cancelled) {
        setPdfModule({
          PDFDownloadLink: pdfRenderer.PDFDownloadLink,
          LabelPdfDocument: labelDoc.LabelPdfDocument,
        });
      }
    });
    return () => { cancelled = true; };
  }, []);

  if (!PdfModule) {
    return (
      <Button className="w-full" disabled>
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading PDF renderer...
      </Button>
    );
  }

  const { PDFDownloadLink, LabelPdfDocument } = PdfModule;

  return (
    <PDFDownloadLink
      document={
        <LabelPdfDocument
          labels={labels}
          productName={productName}
          batchId={batchId}
        />
      }
      fileName={`labels-${batchId}.pdf`}
      className="flex-1"
    >
      {({ loading }) => (
        <Button className="w-full" disabled={loading}>
          <FileDown className="mr-2 h-4 w-4" />
          {loading ? 'Generating PDF...' : 'Download PDF (Click & Print)'}
        </Button>
      )}
    </PDFDownloadLink>
  );
}
