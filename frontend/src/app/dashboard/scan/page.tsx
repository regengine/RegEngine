'use client';

import { useCallback, useEffect, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { useTenant } from '@/lib/tenant-context';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
    Copy,
    Check,
    ExternalLink,
    QrCode,
    Scan,
    Smartphone,
    Camera,
} from 'lucide-react';

/* ------------------------------------------------------------------ */
/*  QR Code generator — renders inline SVG via the `qrcode` package   */
/* ------------------------------------------------------------------ */
let qrcodeLib: typeof import('qrcode') | null = null;
const SAFE_SCAN_TENANT_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

function toSafeSvgDataUrl(svg: string): string | null {
    const trimmedSvg = svg.trim();
    if (
        !trimmedSvg.startsWith('<svg') ||
        /<script\b|<foreignObject\b|\son[a-z]+\s*=|javascript:/i.test(trimmedSvg)
    ) {
        return null;
    }
    return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(trimmedSvg)}`;
}

function useQRCodeSvgDataUrl(text: string) {
    const [svgDataUrl, setSvgDataUrl] = useState<string | null>(null);
    useEffect(() => {
        let cancelled = false;
        (async () => {
            if (!qrcodeLib) {
                qrcodeLib = await import('qrcode');
            }
            const result = await qrcodeLib.toString(text, {
                type: 'svg',
                margin: 2,
                color: { dark: '#10b981', light: '#00000000' },
                width: 240,
            });
            if (!cancelled) setSvgDataUrl(toSafeSvgDataUrl(result));
        })();
        return () => { cancelled = true; };
    }, [text]);
    return svgDataUrl;
}

/* ------------------------------------------------------------------ */
/*  Detect viewport — show scanner on mobile, QR share on desktop     */
/* ------------------------------------------------------------------ */
const MOBILE_MEDIA_QUERY = '(max-width: 768px)';

function subscribeToMobileQuery(onStoreChange: () => void) {
    const mq = window.matchMedia(MOBILE_MEDIA_QUERY);
    mq.addEventListener('change', onStoreChange);
    return () => mq.removeEventListener('change', onStoreChange);
}

function useIsMobile() {
    // useSyncExternalStore is the SSR-safe way to read a browser-only value:
    // the server snapshot is `false`, the client reads matchMedia directly, and
    // there is no setState-in-effect (so no extra render after hydration).
    return useSyncExternalStore(
        subscribeToMobileQuery,
        () => window.matchMedia(MOBILE_MEDIA_QUERY).matches,
        () => false,
    );
}

const HOW_IT_WORKS = [
    {
        step: '1',
        title: 'Operator scans QR code',
        detail: 'Opens the capture tool in their phone browser. No app download, no login required for scanning.',
    },
    {
        step: '2',
        title: 'Select event type & scan item',
        detail: 'Choose what you\'re doing: Receiving, Shipping, or Transforming. Point your camera at the barcode — product number, lot code, expiry, and serial are extracted automatically.',
    },
    {
        step: '3',
        title: 'Event ingests into pipeline',
        detail: 'Scanned data flows into your compliance pipeline as a traceability event. If offline, it queues locally and syncs when connection returns.',
    },
    {
        step: '4',
        title: 'Appears in your dashboard',
        detail: 'Events show up in Heartbeat, contribute to compliance scoring, and are included in recall traces and exports.',
    },
] as const;

const BARCODE_FORMATS = [
    'QR Code (GS1 Digital Link)',
    'GS1-128',
    'DataMatrix',
    'EAN-13',
    'UPC-A',
    'Code 128',
] as const;

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */
export default function ScanPage() {
    if (!experimentalFeaturesEnabled()) {
        return (
            <FeatureNotEnabled
                featureName="Field Capture"
                backHref="/dashboard"
                backLabel="Back to dashboard"
            />
        );
    }
    return <ScanPageContent />;
}

function ScanPageContent() {
    const isMobile = useIsMobile();
    const { tenantId } = useTenant();
    const safeTenantId = SAFE_SCAN_TENANT_ID.test(tenantId) ? tenantId : null;
    const capturePath = safeTenantId
        ? `/fsma/field-capture?tenant_id=${encodeURIComponent(safeTenantId)}`
        : '/fsma/field-capture';
    const captureURL = typeof window !== 'undefined'
        ? `${window.location.origin}${capturePath}`
        : `https://regengine.co${capturePath}`;

    const qrSvgDataUrl = useQRCodeSvgDataUrl(captureURL);
    const [copied, setCopied] = useState(false);

    const handleCopy = useCallback(async () => {
        await navigator.clipboard.writeText(captureURL);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }, [captureURL]);

    return (
        <PageContainer>
            <PageHeader
                title="Field Capture"
                description="Scan barcodes and capture photos from the factory floor. Events flow directly into your compliance pipeline with offline support."
            />

            <div className="space-y-6">
                <p className="text-small text-re-text-tertiary">
                    {safeTenantId
                        ? `Shared capture links stay scoped to workspace ${safeTenantId}.`
                        : 'Shared capture links use the active dashboard workspace once a session is established.'}
                </p>

                {isMobile ? (
                    /* ---- Mobile: direct link to scanner ---- */
                    <Card>
                        <CardContent className="flex flex-col items-center gap-4 text-center">
                            <Scan className="h-6 w-6 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                            <div>
                                <h2 className="text-subheading text-re-text-primary">Open Scanner</h2>
                                <p className="mt-1 text-ui text-re-text-secondary">
                                    Scan barcodes or capture evidence photos. Works offline.
                                </p>
                            </div>
                            <Button asChild size="lg">
                                <Link href={capturePath}>
                                    <Camera className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                    Launch Scanner
                                </Link>
                            </Button>
                        </CardContent>
                    </Card>
                ) : (
                    /* ---- Desktop: QR share card + instructions ---- */
                    <div className="grid gap-6 md:grid-cols-2">
                        {/* QR Code card */}
                        <Card>
                            <CardHeader>
                                <div className="flex min-w-0 items-center gap-2.5">
                                    <QrCode className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <h2 className="text-subheading text-re-text-primary">Share with floor staff</h2>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <p className="text-ui text-re-text-secondary">
                                    Display this QR code on a tablet or print it. Floor operators scan it with their phone to open the capture tool — no app install required.
                                </p>

                                {/* QR Code */}
                                <div className="mt-5 flex justify-center">
                                    <div className="flex aspect-square w-full max-w-[240px] items-center justify-center rounded-lg border border-re-border bg-re-surface-card p-4">
                                        {qrSvgDataUrl ? (
                                            <img
                                                src={qrSvgDataUrl}
                                                alt="Field capture QR code"
                                                className="h-full w-full"
                                            />
                                        ) : (
                                            <Skeleton className="h-full w-full" />
                                        )}
                                    </div>
                                </div>

                                {/* Copy link */}
                                <div className="mt-5 flex items-center gap-2 rounded-md border border-re-border-subtle bg-re-surface-inset p-2 pl-3">
                                    <code className="min-w-0 flex-1 truncate font-mono text-[0.8125rem] text-re-text-secondary">{captureURL}</code>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={handleCopy}
                                        className="shrink-0"
                                    >
                                        {copied
                                            ? <Check className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                            : <Copy className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}
                                        {copied ? 'Copied' : 'Copy'}
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>

                        {/* How it works card */}
                        <Card>
                            <CardHeader>
                                <div className="flex min-w-0 items-center gap-2.5">
                                    <Smartphone className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <h2 className="text-subheading text-re-text-primary">How it works</h2>
                                </div>
                            </CardHeader>
                            <CardContent className="p-0">
                                <ol className="divide-y divide-re-border-subtle">
                                    {HOW_IT_WORKS.map((item) => (
                                        <li key={item.step} className="flex gap-3 px-5 py-4">
                                            <span className="shrink-0 font-mono text-label text-re-text-muted">
                                                {item.step}
                                            </span>
                                            <div className="min-w-0">
                                                <div className="text-ui font-medium text-re-text-primary">{item.title}</div>
                                                <p className="mt-0.5 text-small text-re-text-tertiary">{item.detail}</p>
                                            </div>
                                        </li>
                                    ))}
                                </ol>

                                {/* Try it yourself */}
                                <div className="border-t border-re-border-subtle px-5 py-4">
                                    <Link
                                        href={capturePath}
                                        target="_blank"
                                        className="inline-flex items-center gap-1.5 text-ui text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                                    >
                                        Open scanner in new tab <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                                    </Link>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                )}

                {/* Supported formats */}
                <Card>
                    <CardContent>
                        <h3 className="text-subheading text-re-text-primary">Supported barcode formats</h3>
                        <div className="mt-3 flex flex-wrap gap-2">
                            {BARCODE_FORMATS.map((fmt) => (
                                <Badge key={fmt} mono>
                                    {fmt}
                                </Badge>
                            ))}
                        </div>
                        <p className="mt-3 text-small text-re-text-tertiary">
                            Barcodes are parsed automatically — product number, lot code, serial, expiry, and pack date are extracted and mapped to the required data fields.
                        </p>
                    </CardContent>
                </Card>
            </div>
        </PageContainer>
    );
}
