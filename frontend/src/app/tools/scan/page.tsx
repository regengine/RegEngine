'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { Lock } from 'lucide-react';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { EmailGate } from '@/components/tools/EmailGate';
import { parseGS1, isFSMACompatible } from '@/lib/gs1-parser';
import { trackToolRunCompleted, trackToolRunStarted } from '@/lib/conversion-events';
import type { GS1ParsedData } from '@/lib/gs1-parser';
import styles from './scan.module.css';

export default function ScanPage() {
  const [parsed, setParsed] = useState<GS1ParsedData | null>(null);
  const [rawBarcode, setRawBarcode] = useState<string>('');
  const [manualInput, setManualInput] = useState<string>('');
  const [scanHistory, setScanHistory] = useState<string[]>([]);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [eventType, setEventType] = useState<string>('Receiving');
  const [quantity, setQuantity] = useState<string>('');
  const [uom, setUom] = useState<string>('cases');
  const [locationGLN, setLocationGLN] = useState<string>('');

  const scannerRef = useRef<HTMLDivElement>(null);
  const qrCodeRef = useRef<any>(null);
  const cameraRunPending = useRef(false);
  const lastCameraBarcode = useRef<string | null>(null);

  const handleParse = (barcode: string, fromCamera = false): void => {
    if (!barcode.trim()) return;
    if (fromCamera && lastCameraBarcode.current === barcode) return;

    if (!fromCamera || !cameraRunPending.current) trackToolRunStarted('scan');
    if (fromCamera) {
      cameraRunPending.current = false;
      lastCameraBarcode.current = barcode;
    }
    let result: GS1ParsedData;
    try {
      result = parseGS1(barcode);
    } catch (error) {
      trackToolRunCompleted('scan', 'error');
      throw error;
    }
    setParsed(result);
    setRawBarcode(barcode);
    setManualInput('');
    setCameraError(null);

    setScanHistory((prev) => {
      const updated = [barcode, ...prev].slice(0, 5);
      return updated;
    });
    trackToolRunCompleted('scan', 'success');
  };

  const startCamera = async (): Promise<void> => {
    if (!scannerRef.current) return;

    trackToolRunStarted('scan');
    cameraRunPending.current = true;
    lastCameraBarcode.current = null;
    try {
      setCameraError(null);
      const { Html5Qrcode } = await import('html5-qrcode');
      const html5qrcode = new Html5Qrcode('scanner-container');

      qrCodeRef.current = html5qrcode;

      await html5qrcode.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 250, height: 250 } },
        (decodedText: string) => {
          handleParse(decodedText, true);
        },
        () => {}
      );

      setIsScanning(true);
    } catch (err) {
      const errorMsg =
        err instanceof Error ? err.message : 'Camera access denied or unavailable';
      setCameraError(errorMsg);
      setIsScanning(false);
      if (cameraRunPending.current) trackToolRunCompleted('scan', 'error');
      cameraRunPending.current = false;
    }
  };

  const stopCamera = async (): Promise<void> => {
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
    cameraRunPending.current = false;
  };

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  const isCompatible = parsed ? isFSMACompatible(parsed) : false;

  const formatDate = (dateStr?: string): string => {
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
    <EmailGate toolName="scan">
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
              <div className={styles.errorBanner} role="alert">
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
              type="button"
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
              <label htmlFor="scan-manual-input" className="sr-only">
                Paste or type barcode string…
              </label>
              <input
                id="scan-manual-input"
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
                type="button"
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
                      type="button"
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
                  {parsed.sourceFormat === 'gs1_ai'
                    ? 'GS1-AI'
                    : parsed.sourceFormat === 'digital_link'
                      ? 'GS1 Digital Link'
                      : 'Unknown Format'}
                </span>
                <span
                  className={`${styles.statusBadge} ${
                    isCompatible ? styles.badgeSuccess : styles.badgeError
                  }`}
                >
                  {isCompatible ? '✓ Likely FSMA-relevant fields detected' : '✗ Insufficient FSMA fields for a complete Key Data Element (KDE) set'}
                </span>
              </div>

              {/* Parsed Fields Grid */}
              <div className={styles.section}>
                <h3 className={styles.sectionTitle}>Parsed Fields</h3>
                <div className={styles.fieldsGrid}>
                  <div className={styles.field}>
                    <span className={styles.fieldLabel}>GTIN</span>
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
                    <span className={styles.fieldLabel}>
                      Traceability Lot Code (TLC)
                    </span>
                    <div className={styles.fieldValue}>
                      {parsed.tlc || 'Not found'}
                    </div>
                  </div>

                  <div className={styles.field}>
                    <span className={styles.fieldLabel}>Serial Number</span>
                    <div className={styles.fieldValue}>
                      {parsed.serial || 'Not found'}
                    </div>
                  </div>

                  <div className={styles.field}>
                    <span className={styles.fieldLabel}>Pack Date</span>
                    <div className={styles.fieldValue}>
                      {formatDate(parsed.packDate)}
                    </div>
                  </div>

                  <div className={styles.field}>
                    <span className={styles.fieldLabel}>Expiry Date</span>
                    <div className={styles.fieldValue}>
                      {formatDate(parsed.expiryDate)}
                    </div>
                  </div>
                </div>
              </div>

              {/* CTE Form Preview */}
              <div className={styles.section}>
                <h3 className={styles.sectionTitle}>
                  Auto-filled Critical Tracking Event (CTE) Form Preview
                </h3>

                <div className={styles.formGroup}>
                  <label className={styles.label} htmlFor="scan-event-type">Event Type</label>
                  <select
                    id="scan-event-type"
                    value={eventType}
                    onChange={(e) => setEventType(e.target.value)}
                    className={styles.input}
                  >
                    <option>Harvesting (§1.1325)</option>
                    <option>Cooling (§1.1325)</option>
                    <option>Initial Packing (§1.1330)</option>
                    <option>First Land-Based Receiving for seafood (§1.1335)</option>
                    <option>Shipping (§1.1340)</option>
                    <option>Receiving (§1.1345)</option>
                    <option>Transformation (§1.1350)</option>
                  </select>
                  <p className="mt-1 text-label text-re-text-tertiary">
                    Selecting Receiving? §1.1305(j) may exempt restaurants and retail food establishments. Confirm your role first.
                  </p>
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label} htmlFor="scan-product-description">Product Description</label>
                  <input
                    id="scan-product-description"
                    type="text"
                    placeholder="From GTIN lookup…"
                    disabled
                    className={styles.input}
                  />
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label} htmlFor="scan-lot-code">Lot Code</label>
                  <input
                    id="scan-lot-code"
                    type="text"
                    value={parsed.tlc || ''}
                    disabled
                    className={styles.input}
                  />
                </div>

                <div className={styles.twoCol}>
                  <div className={styles.formGroup}>
                    <label className={styles.label} htmlFor="scan-quantity">Quantity</label>
                    <input
                      id="scan-quantity"
                      type="number"
                      value={quantity}
                      onChange={(e) => setQuantity(e.target.value)}
                      placeholder="0"
                      className={styles.input}
                    />
                  </div>

                  <div className={styles.formGroup}>
                    <label className={styles.label} htmlFor="scan-uom">Unit of Measure</label>
                    <select
                      id="scan-uom"
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
                  <label className={styles.label} htmlFor="scan-location-gln">Location GLN</label>
                  <input
                    id="scan-location-gln"
                    type="text"
                    value={locationGLN}
                    onChange={(e) => setLocationGLN(e.target.value)}
                    placeholder="Global Location Number"
                    className={styles.input}
                  />
                </div>

                <div className={styles.formGroup}>
                  <label className={styles.label} htmlFor="scan-timestamp">Timestamp</label>
                  <input
                    id="scan-timestamp"
                    type="text"
                    value={new Date().toISOString()}
                    disabled
                    className={styles.input}
                  />
                </div>
              </div>

              {/* Ingest Button */}
              <div className={styles.section}>
                {/* One control, not a <button> nested inside a <Link>: the nested
                    pair was invalid HTML and double-fired on keyboard activation. */}
                <Link href="/onboarding" className={`${styles.button} ${styles.buttonIngest}`}>
                  Ingest Event
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
        <Lock aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} />
        <p className={styles.privacyText}>
          100% client-side parsing. No barcode data is transmitted until you
          explicitly ingest.
        </p>
      </div>
      </FreeToolPageShell>
    </EmailGate>
  );
}
