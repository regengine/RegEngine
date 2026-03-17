'use client';

import { useState, useRef, useEffect } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { parseGS1, isFSMACompatible } from '@/lib/gs1-parser';
import type { GS1ParsedData } from '@/lib/gs1-parser';
import styles from './scan.module.css';

const Html5Qrcode = dynamic(
  async () => {
    const module = await import('html5-qrcode');
    return { default: module.Html5Qrcode };
  },
  { ssr: false }
);

export default function ScanPage() {
  const [parsed, setParsed] = useState<GS1ParsedData | null>(null);
  const [rawBarcode, setRawBarcode] = useState('');
  const [manualInput, setManualInput] = useState('');
  const [scanHistory, setScanHistory] = useState<string[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [eventType, setEventType] = useState('Receiving');
  const [quantity, setQuantity] = useState('');
  const [uom, setUom] = useState('cases');
  const [locationGLN, setLocationGLN] = useState('');

  const scannerRef = useRef<HTMLDivElement>(null);
  const qrCodeRef = useRef<any>(null);

  const handleParse = (barcode: string) => {
    if (!barcode.trim()) return;

    const result = parseGS1(barcode);
    setParsed(result);
    setRawBarcode(barcode);
    setManualInput('');
    setCameraError(null);

    setScanHistory((prev) => {
      const updated = [barcode, ...prev].slice(0, 5);
      return updated;
    });
  };

  const startCamera = async () => {
    if (!scannerRef.current) return;

    try {
      setCameraError(null);
      const html5qrcode = new Html5Qrcode('scanner-container');

      qrCodeRef.current = html5qrcode;

      await html5qrcode.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        (decodedText) => {
          handleParse(decodedText);
        },
        () => {}
      );

      setIsScanning(true);
    } catch (err) {
      const errorMsg =
        err instanceof Error ? err.message : 'Camera access denied or unavailable';
      setCameraError(errorMsg);
      setIsScanning(false);
    }
  };

  const stopCamera = async () => {
    if (qrCodeRef.current) {
      try {
        await qrCodeRef.current.stop();
        await qrCodeRef.current.clear();
      } catch (err) {
        console.error('Error stopping camera:', err);
      }
      qrCodeRef.current = null;
    }
    setIsScanning(false);
  };

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  const isCompatible = parsed ? isFSMACompatible(parsed) : false;

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return 'Not provided';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <FreeToolPageShell
      title="Scan & Ingest"
      subtitle="Scan a GS1 barcode with your camera or paste a barcode string to extract FSMA-compatible traceability data"
      relatedToolIds={['cte-mapper', 'kde-checker', 'ftl-checker']}
    >
      <div className={styles.container}>
        {/* LEFT COLUMN: Scanner */}
        <div className={styles.leftColumn}>
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Camera Scanner</h3>

            {cameraError ? (
              <div className={styles.errorBanner}>
                <p className={styles.errorText}>{cameraError}</p>
                <p className={styles.errorHint}>
                  Camera unavailable. Use manual input below or check permissions.
                </p>
              </div>
            ) : (
              <div
                id="scanner-container"
                ref={scannerRef}
                className={styles.scannerContainer}
              />
            )}

            <button
              onClick={isScanning ? stopCamera : startCamera}
              disabled={!!cameraError}
              className={`${styles.button} ${isScanning ? styles.buttonSecondary : styles.buttonPrimary}`}
            >
              {isScanning ? 'Stop Camera' : 'Start Camera'}
            </button>

            <div className={styles.formatBadges}>
              <span className={styles.badge}>QR Code</span>
              <span className={styles.badge}>GS1-128</span>
              <span className={styles.badge}>DataMatrix</span>
              <span className={styles.badge}>EAN-13</span>
              <span className={styles.badge}>Code 128</span>
            </div>
          </div>

          {/* Manual Input */}
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Manual Input</h3>
            <div className={styles.inputGroup}>
              <input
                type="text"
                value={manualInput}
                onChange={(e) => setManualInput(e.target.value)}
                placeholder="Paste or type barcode string…"
                className={styles.input}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    handleParse(manualInput);
                  }
                }}
              />
              <button
                onClick={() => handleParse(manualInput)}
                className={`${styles.button} ${styles.buttonPrimary}`}
              >
                Parse
              </button>
            </div>
          </div>

          {/* Scan History */}
          {scanHistory.length > 0 && (
            <div className={styles.section}>
              <h3 className={styles.sectionTitle}>Scan History</h3>
              <ul className={styles.historyList}>
                {scanHistory.map((barcode, idx) => (
                  <li key={idx}>
                    <button
                      onClick={() => handleParse(barcode)}
                      className={styles.historyButton}
                    >
                      {barcode.substring(0, 40)}
                      {barcode.length > 40 ? '…' : ''}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Results */}
        <div className={styles.rightColumn}>
          {parsed ? (
            <>
              {/* Status Badges */}
              <div className={styles.badgeRow}>
                <span
                  className={`${styles.statusBadge} ${
                    parsed.sourceFormat !== 'unknown'
                      ? styles.badgeSuccess
                      : styles.badgeWarning
                  }`}
                >
                  {parsed.sourceFormat === 'gs1-ai'
                    ? 'GS1-AI'
                    : parsed.sourceFormat === 'gs1-digital-link'
                      ? 'GS1 Digital Link'
                      : 'Unknown Format'}
                </span>
                <span
                  className={`${styles.statusBadge} ${
                    isCompatible ? styles.badgeSuccess : styles.badgeError
                  }`}
                >
                  {isCompatible ? '✓ FSMA Compatible' : '✗ Not FSMA Compatible'}
                </span>
              </div>

              {/* Parsed Fields Grid */}
              <div className={styles.section}>
                <h3 className={styles.sectionTitle}>Parsed Fields</h3>
                <div className={styles.fieldsGrid}>
                  <div className={styles.field}>
                    <label className={styles.fieldLabel}>GTIN</label>
                    <div className={styles.fieldValue}>
                      {parsed.gtin || 'Not found'}
                      {parsed.gtin && (
                        <span
                          className={
                            parsed.isValidGTIN
                              ? styles.validIndicator
                              : styles.invalidIndicator
                          }
                        >
                          {parsed.isValidGTIN ? ' ✓' : ' ✗'}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className={styles.field}>
                    <label className={styles.fieldLabel}>
                      Traceability Lot Code (TLC)
                    </label>
                    <div className={styles.fieldValue}>
                      {parsed.tlc || 'Not found'}
                    </div>
                  </div>

                  <div className={styles.field}>
                    <label className={styles.fieldLabel}>Serial Number</label>
                    <div className={styles.fieldValue}>
                      {parsed.serial || 'Not found'}
                    </div>
                  </div>

                  <div className={styles.field}>
                    <label className={styles.fieldLabel}>Pack Date</label>
                    <div className={styles.fieldValue}>
                      {formatDate(parsed.packDate)}
                    </div>
                  </div>

                  <div className={styles.field}>
                    <label className={styles.fieldLabel}>Expiry Date</label>
                    <div className={styles.fieldValue}>
                      {formatDate(parsed.expiryDate)}
                    </div>
                  </div>
                </div>
              </div>

              {/* CTE Form Preview */}
              <div className={styles.section}>
                <h3 className={styles.sectionTitle}>
                  Auto-filled CTE Form Preview
                </h3>

                <div className={styles.formGroup}>
                  <label className={styles.label}>Event Type</label>
                  <select
                    value={eventType}
                    onChange={(e) => setEventType(e.target.value)}
                    className={styles.input}
                  >
                    <option>Receiving</option>
                    <option>Shipping</option>
                    <option>Transformation</option>
                    <option>Aggregation</option>
                  </select>
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label}>Product Description</label>
                  <input
                    type="text"
                    placeholder="From GTIN lookup…"
                    disabled
                    className={styles.input}
                  />
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label}>Lot Code</label>
                  <input
                    type="text"
                    value={parsed.tlc || ''}
                    disabled
                    className={styles.input}
                  />
                </div>

                <div className={styles.twoCol}>
                  <div className={styles.formGroup}>
                    <label className={styles.label}>Quantity</label>
                    <input
                      type="number"
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                      placeholder="0"
                      className={styles.input}
                    />
                  </div>

                  <div className={styles.formGroup}>
                    <label className={styles.label}>Unit of Measure</label>
                    <select
                      value={uom}
                      onChange={(e) => setUom(e.target.value)}
                      className={styles.input}
                    >
                      <option>cases</option>
                      <option>lbs</option>
                      <option>kg</option>
                      <option>each</option>
                    </select>
                  </div>
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label}>Location GLN</label>
                  <input
                    type="text"
                    value={locationGLN}
                    onChange={(e) => setLocationGLN(e.target.value)}
                    placeholder="Global Location Number"
                    className={styles.input}
                  />
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label}>Timestamp</label>
                  <input
                    type="text"
                    value={new Date().toISOString()}
                    disabled
                    className={styles.input}
                  />
                </div>
              </div>

              {/* Ingest Button */}
              <div className={styles.section}>
                <Link href="/onboarding">
                  <button className={`${styles.button} ${styles.buttonIngest}`}>
                    Ingest Event
                  </button>
                </Link>
                <p className={styles.ingestNote}>
                  Requires RegEngine account to save events
                </p>
              </div>

              {/* Raw Barcode */}
              <div className={styles.section}>
                <h3 className={styles.sectionTitle}>Raw Barcode String</h3>
                <pre className={styles.codeBlock}>{rawBarcode}</pre>
              </div>
            </>
          ) : (
            <div className={styles.placeholder}>
              <p className={styles.placeholderText}>
                Scan a barcode or paste one manually to see parsed results
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Privacy Note */}
      <div className={styles.privacyNote}>
        <p className={styles.privacyText}>
          🔒 100% client-side parsing. No barcode data is transmitted until you
          explicitly ingest.
        </p>
      </div>
    </FreeToolPageShell>
  );
}
