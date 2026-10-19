import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';

// Static on purpose: /api-keys, the settings API tab and the ingest page all
// link here. Live keys are issued by RegEngine, so this page only says so and
// points at the request form. It has no key list, no create form and no
// network call.
export default function ApiKeysPage() {
    return (
        <PageContainer className="space-y-6">
            <PageHeader
                title="API keys"
                description="How live API keys are issued for your workspace."
                className="mb-0"
            />

            <Card>
                <CardHeader>
                    <CardTitle>Live keys are issued by RegEngine</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <p className="max-w-[70ch] text-ui text-re-text-secondary">
                        RegEngine creates each live API key for your workspace and delivers it to you directly. Keys are
                        not created in this portal, and this page does not list or show them.
                    </p>
                    <p className="max-w-[70ch] text-small text-re-text-tertiary">
                        Treat a key like a password for your workspace. If one is exposed, contact us right away.
                    </p>
                    <Button asChild>
                        <Link href="/contact" className="no-underline">Request a live key</Link>
                    </Button>
                </CardContent>
            </Card>
        </PageContainer>
    );
}
