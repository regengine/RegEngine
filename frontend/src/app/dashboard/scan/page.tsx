'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
    Copy,
    Check,
    ExternalLink,
    QrCode,
    Scan,
    Smartphone,
    Wifi,
    WifiOff,
    Loader2,
    Package,
    Camera,
} from 'lucide-react';

/* ------------------------------------------------------------------ */
/*  QR Code generator — renders inline SVG via the `qrcode` package   */
/* ------------------------------------------------------------------ */
let qrcodeLib: typeof import('qrcode') | null = null;

function useQRCodeSVG(text: string) {
    const [svg, setSvg] = useState<string | null>(null);
    useEffect(() => {
        let cancelled = false;        (async () => {
            if (!qrcodeLib) {
                qrcodeLib = await import('qrcode');
            }
            const result = await qrcodeLib.toString(text, {
                type: 'svg',
                margin: 2,
                color: { dark: '#10b981', light: '#00000000' },
                width: 240,
            });
            if (!cancelled) setSvg(result);
        })();
        return () => { cancelled = true; };
    }, [text]);
    return svg;
}

/* ------------------------------------------------------------------ */
/*  Detect viewport — show scanner on mobile, QR share on desktop     */
/* ------------------------------------------------------------------ */
function useIsMobile() {
    const [mobile, setMobile] = useState(false);
    useEffect(() => {
        const mq = window.matchMedia('(max-width: 768px)');
        setMobile(mq.matches);
        const handler = (e: MediaQueryListEvent) => setMobile(e.matches);        mq.addEventListener('change', handler);
        return () => mq.removeEventListener('change', handler);
    }, []);
    return mobile;
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */
const card = 'rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-sm';

export default function ScanPage() {
    const isMobile = useIsMobile();
    const captureURL = typeof window !== 'undefined'
        ? `${window.location.origin}/mobile/capture`
        : 'https://regengine.co/mobile/capture';

    const qrSvg = useQRCodeSVG(captureURL);
    const [copied, setCopied] = useState(false);

    const handleCopy = useCallback(async () => {
        await navigator.clipboard.writeText(captureURL);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }, [captureURL]);

    return (
        <div className="p-4 sm:p-6 max-w-[980px] mx-auto space-y-6">
            {/* Header */}            <div>
                <h1 className="text-2xl font-bold text-[var(--re-text-primary)]">Field Capture</h1>
                <p className="text-sm text-[var(--re-text-muted)] mt-1 max-w-[640px]">
                    Scan barcodes and capture photos from the factory floor. Events flow directly into your compliance pipeline with offline support.
                </p>
            </div>

            {isMobile ? (
                /* ---- Mobile: direct link to scanner ---- */
                <div className={`${card} p-6`}>
                    <div className="flex flex-col items-center text-center gap-4">
                        <div className="w-14 h-14 rounded-2xl bg-[var(--re-brand)]/10 flex items-center justify-center">
                            <Scan className="h-7 w-7 text-[var(--re-brand)]" />
                        </div>
                        <div>
                            <h2 className="text-lg font-semibold text-[var(--re-text-primary)]">Open Scanner</h2>
                            <p className="text-sm text-[var(--re-text-muted)] mt-1">
                                Scan GS1 barcodes or capture evidence photos. Works offline.
                            </p>
                        </div>
                        <Link
                            href="/mobile/capture"
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-[var(--re-brand)] text-white font-medium text-sm hover:opacity-90 transition-opacity"
                        >
                            <Camera className="h-4 w-4" />
                            Launch Scanner
                        </Link>
                    </div>
                </div>            ) : (
                /* ---- Desktop: QR share card + instructions ---- */
                <div className="grid gap-6 md:grid-cols-2">
                    {/* QR Code card */}
                    <div className={`${card} p-6`}>
                        <div className="flex items-center gap-2.5 mb-4">
                            <QrCode className="h-5 w-5 text-[var(--re-brand)]" />
                            <h2 className="text-base font-semibold text-[var(--re-text-primary)]">Share with floor staff</h2>
                        </div>
                        <p className="text-sm text-[var(--re-text-muted)] mb-5">
                            Display this QR code on a tablet or print it. Floor operators scan it with their phone to open the capture tool — no app install required.
                        </p>

                        {/* QR Code */}
                        <div className="flex justify-center mb-5">
                            <div className="w-[240px] h-[240px] rounded-xl border border-[var(--re-surface-border)] bg-white/5 flex items-center justify-center p-4">
                                {qrSvg ? (
                                    <div dangerouslySetInnerHTML={{ __html: qrSvg }} />
                                ) : (
                                    <Loader2 className="h-6 w-6 text-[var(--re-text-disabled)] animate-spin" />
                                )}
                            </div>
                        </div>

                        {/* Copy link */}
                        <div className="flex items-center gap-2 p-3 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)]">
                            <code className="text-xs text-[var(--re-text-muted)] truncate flex-1">{captureURL}</code>                            <button
                                onClick={handleCopy}
                                className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium bg-[var(--re-brand)]/10 text-[var(--re-brand)] hover:bg-[var(--re-brand)]/20 transition-colors flex-shrink-0"
                            >
                                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                                {copied ? 'Copied' : 'Copy'}
                            </button>
                        </div>
                    </div>

                    {/* How it works card */}
                    <div className={`${card} p-6`}>
                        <div className="flex items-center gap-2.5 mb-4">
                            <Smartphone className="h-5 w-5 text-[var(--re-brand)]" />
                            <h2 className="text-base font-semibold text-[var(--re-text-primary)]">How it works</h2>
                        </div>

                        <div className="space-y-4">
                            {[
                                {
                                    step: '1',
                                    title: 'Operator scans QR code',
                                    detail: 'Opens the capture tool in their phone browser. No app download, no login required for scanning.',
                                },
                                {
                                    step: '2',
                                    title: 'Select CTE type & scan item',
                                    detail: 'Choose Shipping, Receiving, or Transformation. Point camera at GS1 barcode — GTIN, lot, expiry, and serial are extracted automatically.',
                                },                                {
                                    step: '3',
                                    title: 'Event ingests into pipeline',
                                    detail: 'Scanned data flows into your compliance pipeline as a CTE event. If offline, it queues locally and syncs when connection returns.',
                                },
                                {
                                    step: '4',
                                    title: 'Appears in your dashboard',
                                    detail: 'Events show up in Heartbeat, contribute to compliance scoring, and are included in recall traces and exports.',
                                },
                            ].map((item) => (
                                <div key={item.step} className="flex gap-3">
                                    <div className="w-7 h-7 rounded-lg bg-[var(--re-brand)]/10 flex items-center justify-center text-xs font-bold text-[var(--re-brand)] flex-shrink-0 mt-0.5">
                                        {item.step}
                                    </div>
                                    <div>
                                        <div className="text-sm font-medium text-[var(--re-text-primary)]">{item.title}</div>
                                        <p className="text-xs text-[var(--re-text-muted)] mt-0.5 leading-relaxed">{item.detail}</p>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Try it yourself */}
                        <div className="mt-5 pt-4 border-t border-[var(--re-surface-border)]">
                            <Link
                                href="/mobile/capture"
                                target="_blank"
                                className="inline-flex items-center gap-1.5 text-sm text-[var(--re-brand)] hover:opacity-80 transition-opacity"
                            >
                                Open scanner in new tab <ExternalLink className="h-3.5 w-3.5" />                            </Link>
                        </div>
                    </div>
                </div>
            )}

            {/* Supported formats */}
            <div className={`${card} p-5`}>
                <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-3">Supported barcode formats</h3>
                <div className="flex flex-wrap gap-2">
                    {[
                        'QR Code (GS1 Digital Link)',
                        'GS1-128',
                        'DataMatrix',
                        'EAN-13',
                        'UPC-A',
                        'Code 128',
                    ].map((fmt) => (
                        <span
                            key={fmt}
                            className="px-2.5 py-1 rounded-md bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] text-xs text-[var(--re-text-muted)]"
                        >
                            {fmt}
                        </span>
                    ))}
                </div>
                <p className="text-xs text-[var(--re-text-disabled)] mt-3">
                    GS1 barcodes are parsed automatically — GTIN, lot code, serial, expiry, and pack date are extracted and mapped to FSMA 204 KDEs.
                </p>
            </div>
        </div>
    );
}
