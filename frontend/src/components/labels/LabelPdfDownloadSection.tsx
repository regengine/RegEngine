'use client';

/**
 * Wrapper that lazy-loads @react-pdf/renderer and LabelPdfDocument.
 *
 * Keeps the ~500KB @react-pdf/renderer bundle out of the main chunk;
 * it is only downloaded when this component mounts (i.e. after label
 * generation succeeds).
 */

import React from 'react';
import { PDFDownloadLink } from '@react-pdf/renderer';
import { LabelPdfDocument } from '@/components/labels/LabelPdfDocument';
import { Button } from '@/components/ui/button';
import { FileDown } from 'lucide-react';
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
