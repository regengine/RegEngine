import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent } from '@/components/ui/card';
import { parseLabelLink, traceHrefForLot } from '@/lib/label-link';

/**
 * Public landing page for a scanned RegEngine label.
 *
 * Every label printed by services/graph/app/routers/labels.py carries a QR
 * code pointing at <TRACEABILITY_DOMAIN>/01/{gtin}/10/{lot}/21/{serial}.
 * This page is what a scan reaches. It shows only what the code itself
 * encodes, which is already printed on the label, and sends signed-in users
 * on to /trace with the lot prefilled. It never queries tenant data.
 */

type Params = Promise<{ gtin: string; lot: string; serial: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
    const label = parseLabelLink(await params);
    return {
        title: label ? `Lot ${label.lot} | RegEngine label` : 'Label not found | RegEngine',
        // One page per printed serial. Nothing here should rank.
        robots: { index: false, follow: false },
    };
}

export default async function LabelLinkPage({ params }: { params: Params }) {
    const label = parseLabelLink(await params);
    if (!label) notFound();

    const rows: Array<[string, string]> = [
        ['GTIN (AI 01)', label.gtin],
        ['Traceability Lot Code (AI 10)', label.lot],
        ['Serial (AI 21)', label.serial],
        ['GTIN check digit', label.gtinCheckDigitValid ? 'Valid' : 'Does not match'],
    ];

    return (
        <Container width="tool" className="py-10">
            <PageHeader
                eyebrow="Traceability label"
                title={`Lot ${label.lot}`}
                description="This QR code uses the GS1 Digital Link format that RegEngine prints on labels. The values below are read from the code itself."
            />

            <Card>
                <CardContent>
                    <dl className="grid gap-4 sm:grid-cols-2">
                        {rows.map(([term, value]) => (
                            <div key={term}>
                                <dt className="text-label text-re-text-muted">{term}</dt>
                                <dd className="mt-1 break-all font-mono text-ui text-re-text-primary">{value}</dd>
                            </div>
                        ))}
                    </dl>
                </CardContent>
            </Card>

            <Callout tone="neutral" title="Custody records are not shown here" className="mt-6">
                Tracing a lot through its Critical Tracking Events needs a RegEngine workspace sign-in.
                Nothing on this page confirms where the product has been.
            </Callout>

            <div className="mt-6">
                <Button asChild>
                    <Link href={traceHrefForLot(label.lot)}>Trace this lot</Link>
                </Button>
            </div>
        </Container>
    );
}
