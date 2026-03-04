/**
 * PDF Document Component for Label Generation
 * Uses @react-pdf/renderer for client-side PDF generation
 *
 * Note: This component requires the following packages:
 * - @react-pdf/renderer
 * - qrcode
 *
 * Install with: npm install @react-pdf/renderer qrcode @types/qrcode
 */

'use client';

import React from 'react';
import type { LabelData } from '@/types/labels';

import { Document, Page, View, Text, Image, StyleSheet } from '@react-pdf/renderer';
import QRCode from 'qrcode';

interface LabelPdfDocumentProps {
  labels: LabelData[];
  productName: string;
  batchId: string;
}

/**
 * PDF styles for Avery 5160 or 2x2 label sheets
 * Dimensions: 2" x 2" labels
 */
const styles = StyleSheet.create({
  page: {
    padding: 10,
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  labelContainer: {
    width: '144pt', // 2 inches = 144 points
    height: '144pt',
    padding: 8,
    margin: 4,
    border: '1pt solid #ddd',
    flexDirection: 'column',
    justifyContent: 'space-between',
  },
  productName: {
    fontSize: 10,
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 4,
  },
  plu: {
    fontSize: 28,
    fontWeight: 'bold',
    textAlign: 'center',
    marginVertical: 8,
  },
  qrContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: 4,
  },
  qrImage: {
    width: 60,
    height: 60,
  },
  serialNumber: {
    fontSize: 8,
    textAlign: 'center',
    marginTop: 4,
  },
  gtin: {
    fontSize: 7,
    textAlign: 'center',
    color: '#666',
  },
});

/**
 * Generate QR code data URL from payload
 */
async function generateQRDataURL(payload: string): Promise<string> {
  return await QRCode.toDataURL(payload, { width: 200, margin: 1 });
}

/**
 * LabelPdfDocument Component
 *
 * Generates a PDF document with labels formatted for printing on Avery sheets
 * Each label includes:
 * - Product name
 * - PLU (if available)
 * - QR code
 * - Serial number
 * - GTIN
 *
 * @example
 * ```tsx
 * import { PDFDownloadLink } from '@react-pdf/renderer';
 *
 * <PDFDownloadLink
 *   document={<LabelPdfDocument labels={labels} productName="Tomatoes" batchId="batch-123" />}
 *   fileName={`labels-${batchId}.pdf`}
 * >
 *   {({ loading }) => loading ? 'Generating PDF...' : 'Download PDF'}
 * </PDFDownloadLink>
 * ```
 */
export const LabelPdfDocument: React.FC<LabelPdfDocumentProps> = ({
  labels,
  productName,
  batchId,
}) => {
  const [qrDataUrls, setQrDataUrls] = React.useState<Record<string, string>>({});

  React.useEffect(() => {
    async function generateQRCodes() {
      const urls: Record<string, string> = {};
      for (const label of labels) {
        urls[label.serial] = await generateQRDataURL(label.qr_payload);
      }
      setQrDataUrls(urls);
    }
    generateQRCodes();
  }, [labels]);

  return (
    <Document>
      <Page size="LETTER" style={styles.page}>
        {labels.map((label, index) => (
          <View key={label.serial} style={styles.labelContainer}>
            <Text style={styles.productName}>{productName}</Text>

            {label.packaging_level === 'item' && (
              <Text style={styles.plu}>
                PLU: {extractPLU(label.qr_payload) || 'N/A'}
              </Text>
            )}

            <View style={styles.qrContainer}>
              {qrDataUrls[label.serial] && (
                // eslint-disable-next-line jsx-a11y/alt-text -- @react-pdf/renderer Image does not support alt
                <Image
                  src={qrDataUrls[label.serial]}
                  style={styles.qrImage}
                />
              )}
            </View>

            <Text style={styles.serialNumber}>Serial: {label.serial}</Text>
            <Text style={styles.gtin}>GTIN: {extractGTIN(label.qr_payload)}</Text>
          </View>
        ))}
      </Page>
    </Document>
  );
};

/**
 * Helper function to extract GTIN from QR payload
 */
function extractGTIN(payload: string): string {
  const match = payload.match(/\/01\/(\d{14})/);
  return match ? match[1] : 'N/A';
}

/**
 * Helper function to extract PLU from metadata (if stored separately)
 */
function extractPLU(payload: string): string | null {
  // This would need to be implemented based on how PLU is stored
  // For now, return null
  return null;
}

export default LabelPdfDocument;
