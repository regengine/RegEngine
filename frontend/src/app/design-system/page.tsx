'use client';

import { useState } from 'react';
import { notFound } from 'next/navigation';
import {
    AlertTriangle,
    Boxes,
    Download,
    FileText,
    Inbox,
    Plus,
    Trash2,
} from 'lucide-react';

import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

/**
 * /design-system — the rendered contract for the design system.
 *
 * Every primitive, in every state, in whichever theme is active. This is what a
 * page author checks their work against, and the fastest way for a human to
 * review the system as a whole. Development-only: it 404s in production.
 */

const STATES: ComplianceState[] = [
    'compliant',
    'committed',
    'exported',
    'at-risk',
    'needs-correction',
    'non-compliant',
    'blocked',
    'pending',
    'in-progress',
    'corrected',
    'unknown',
];

type Row = { lot: string; supplier: string; state: ComplianceState; gaps: number; seen: string };

const ROWS: Row[] = [
    { lot: 'RVF-ROM-041426-F3-001', supplier: 'Rio Verde Farms', state: 'committed', gaps: 0, seen: '2026-09-14T14:02Z' },
    { lot: 'VFP-SPIN5-041426-001', supplier: 'Valley Fresh Packhouse', state: 'needs-correction', gaps: 3, seen: '2026-09-14T11:40Z' },
    { lot: 'FL-SHIP-041426-088', supplier: 'FreshLine Distribution', state: 'blocked', gaps: 7, seen: '2026-09-13T22:15Z' },
];

const COLUMNS: DataTableColumn<Row>[] = [
    { key: 'lot', header: 'Lot code', mono: true, width: '18rem', sortable: true },
    { key: 'supplier', header: 'Supplier', sortable: true },
    { key: 'state', header: 'State', cell: (r) => <StatusBadge state={r.state} size="sm" /> },
    { key: 'gaps', header: 'Gaps', align: 'right', sortable: true },
    { key: 'seen', header: 'Last event', mono: true, align: 'right' },
];

function Swatch({ name, className }: { name: string; className: string }) {
    return (
        <div className="flex items-center gap-3">
            <span className={`h-9 w-9 shrink-0 rounded-md border border-re-border ${className}`} aria-hidden="true" />
            <code className="font-mono text-[0.8125rem] text-re-text-secondary">{name}</code>
        </div>
    );
}

function Row2({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="flex flex-col gap-2 border-b border-re-border-subtle py-4 last:border-0 sm:flex-row sm:items-center sm:gap-6">
            <p className="w-40 shrink-0 text-label text-re-text-muted">{label}</p>
            <div className="flex flex-wrap items-center gap-3">{children}</div>
        </div>
    );
}

export default function DesignSystemPage() {
    const [search, setSearch] = useState('');
    const [sort, setSort] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'lot', direction: 'asc' });

    if (process.env.NODE_ENV === 'production') {
        notFound();
    }

    return (
        <Container width="app" className="py-8">
            <PageHeader
                eyebrow="Internal · development only"
                title="Design system"
                description="Every primitive in every state. Check your page against this before opening a PR. Toggle the theme in the header to verify both palettes."
                meta={<Badge tone="brand" mono>v2</Badge>}
                primaryAction={<Button leadingIcon={<Plus />}>Primary action</Button>}
                secondaryActions={<Button variant="secondary">Secondary</Button>}
            />

            <div className="space-y-10">
                <Section spacing="app" title="Colour" description="Brand green appears in six places only: the primary button, the focus ring, prose links, the wordmark, the active-nav rail, and the hero sparkline.">
                    <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
                        <Swatch name="--re-surface-base" className="bg-re-surface-base" />
                        <Swatch name="--re-surface-card" className="bg-re-surface-card" />
                        <Swatch name="--re-surface-inset" className="bg-re-surface-inset" />
                        <Swatch name="--re-brand" className="bg-re-brand" />
                        <Swatch name="--re-success" className="bg-re-success" />
                        <Swatch name="--re-warning" className="bg-re-warning" />
                        <Swatch name="--re-danger" className="bg-re-danger" />
                        <Swatch name="--re-info" className="bg-re-info" />
                        <Swatch name="--re-state-corrected" className="bg-re-state-corrected" />
                    </div>
                </Section>

                <Section spacing="app" title="Type scale" description="Eight steps, all in rem so the accessibility font-size settings keep scaling them.">
                    <div className="space-y-3">
                        <p className="font-display text-display text-re-text-primary">Display · marketing hero</p>
                        <p className="font-display text-heading-lg text-re-text-primary">Heading-lg · marketing section</p>
                        <p className="text-title text-re-text-primary">Title · page H1</p>
                        <p className="text-heading text-re-text-primary">Heading · H2</p>
                        <p className="text-subheading text-re-text-primary">Subheading · card title</p>
                        <p className="text-body text-re-text-secondary">Body · marketing and docs prose at 16/26.</p>
                        <p className="text-ui text-re-text-secondary">UI · app body, table cells, inputs, buttons.</p>
                        <p className="text-small text-re-text-tertiary">Small · captions and helper text.</p>
                        <p className="text-label text-re-text-muted">Label · eyebrows, table heads, stat labels</p>
                    </div>
                </Section>

                <Section spacing="app" title="Buttons">
                    <div className="w-full space-y-0">
                        <Row2 label="Variants">
                            <Button>Primary</Button>
                            <Button variant="secondary">Secondary</Button>
                            <Button variant="ghost">Ghost</Button>
                            <Button variant="danger" leadingIcon={<Trash2 />}>Danger</Button>
                            <Button variant="link">Link</Button>
                        </Row2>
                        <Row2 label="Sizes">
                            <Button size="sm">Small</Button>
                            <Button size="md">Medium</Button>
                            <Button size="lg">Large</Button>
                            <Button size="icon" aria-label="Download"><Download /></Button>
                        </Row2>
                        <Row2 label="States">
                            <Button loading>Saving</Button>
                            <Button disabled>Disabled</Button>
                            <Button variant="secondary" trailingIcon={<Download />}>With icon</Button>
                        </Row2>
                    </div>
                </Section>

                <Section spacing="app" title="Status" description="A state always ships as icon + label, never colour alone, so it survives greyscale and forced-colours mode.">
                    <div className="flex flex-wrap gap-2">
                        {STATES.map((s) => (
                            <StatusBadge key={s} state={s} />
                        ))}
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                        <Badge>Neutral</Badge>
                        <Badge tone="brand">Brand</Badge>
                        <Badge tone="info" mono>MONO</Badge>
                        <Badge size="sm">Small</Badge>
                    </div>
                </Section>

                <Section spacing="app" title="Stat tiles" description="Label / value / delta / trend. The value is never coloured; only the delta arrow carries sentiment. One hero per view.">
                    <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr_1fr]">
                        <StatTile
                            hero
                            label="FSMA readiness score"
                            value={72}
                            unit="/100"
                            delta={{ value: '+4.2 pts', direction: 'up', sentiment: 'good', period: 'vs last run' }}
                            trend={[58, 60, 59, 63, 65, 64, 68, 70, 69, 72]}
                            status={<StatusBadge state="at-risk" label="Not export eligible" size="sm" />}
                        />
                        <StatTile
                            label="CTE events (30d)"
                            value="1,284"
                            delta={{ value: '+118', direction: 'up', sentiment: 'good', period: 'vs prior 30d' }}
                            trend={[20, 24, 22, 28, 31, 30, 34, 38]}
                        />
                        <StatTile label="Open fixes" value={3} delta={{ value: 'flat', direction: 'flat' }} />
                    </div>
                    <div className="mt-4 grid gap-4 sm:grid-cols-3">
                        <StatTile label="Loading" value="" loading />
                        <StatTile label="Hash chain" value="" empty emptyCaption="No saved Inflow Workbench run yet" />
                        <StatTile label="Linked tile" value={12} href="/design-system" />
                    </div>
                </Section>

                <Section spacing="app" title="Data table">
                    <DataTable
                        caption="Example lots and their compliance state"
                        columns={COLUMNS}
                        data={ROWS}
                        sort={sort}
                        onSortChange={setSort}
                        stickyFirstColumn
                        toolbar={{
                            search: { placeholder: 'Search lots…', value: search, onChange: setSearch },
                            actions: <Button variant="ghost" size="sm" leadingIcon={<Download />}>Export</Button>,
                        }}
                        pagination={{ page: 1, pageSize: 10, total: 3, onPageChange: () => { } }}
                    />
                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                        <DataTable
                            caption="Empty table example"
                            columns={COLUMNS}
                            data={[]}
                            status="empty"
                            empty={{ icon: Inbox, title: 'No facilities yet', description: 'Add a facility to start tracking lot codes.', action: <Button size="sm">Add facility</Button> }}
                        />
                        <DataTable
                            caption="Errored table example"
                            columns={COLUMNS}
                            data={[]}
                            status="error"
                            error={{ message: 'Unable to load supplier data. Please try again.', onRetry: () => { } }}
                        />
                    </div>
                </Section>

                <Section spacing="app" title="Callouts" description="Callouts sit on the card surface. A danger callout with role=alert is the one case that earns a tinted ground.">
                    <div className="space-y-3">
                        <Callout tone="neutral" title="Educational tool">Free self-check tool. Not a compliance certification or regulatory determination.</Callout>
                        <Callout tone="info" title="Sandbox mode">Using sample data for demonstration.</Callout>
                        <Callout tone="success" title="Chain verified">Every record in this export is hash-chained.</Callout>
                        <Callout tone="warning" title="Supplier gaps open" icon={AlertTriangle}>Three lots are missing a ship-to location.</Callout>
                        <Callout tone="danger" role="alert" title="Backend services unreachable" action={<Button size="sm" variant="secondary">Retry</Button>}>
                            Data will appear once services are connected.
                        </Callout>
                    </div>
                </Section>

                <Section spacing="app" title="Cards, fields, tabs, empty states">
                    <div className="grid gap-4 lg:grid-cols-2">
                        <Card>
                            <CardHeader>
                                <div>
                                    <CardTitle>Card title</CardTitle>
                                    <CardDescription>A card carries no shadow; its border darkens on hover.</CardDescription>
                                </div>
                                <StatusBadge state="committed" size="sm" />
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <Field label="Email address" htmlFor="ds-email" hint="We never share this.">
                                    <Input placeholder="you@company.com" type="email" />
                                </Field>
                                <Field label="Lot code" htmlFor="ds-lot" error="That lot code does not exist.">
                                    <Input mono defaultValue="RVF-ROM-041426" />
                                </Field>
                                <Field label="Disabled" htmlFor="ds-disabled">
                                    <Input disabled placeholder="Not editable" />
                                </Field>
                            </CardContent>
                        </Card>

                        <div className="space-y-4">
                            <Card variant="inset" padding="spacious">
                                <p className="text-ui text-re-text-secondary">Card variant <code className="font-mono text-[0.8125rem]">inset</code> — wells, code blocks and summary strips.</p>
                            </Card>
                            <Tabs defaultValue="overview">
                                <TabsList>
                                    <TabsTrigger value="overview">Overview</TabsTrigger>
                                    <TabsTrigger value="lots">Lots</TabsTrigger>
                                    <TabsTrigger value="gaps">Gaps <Badge size="sm">3</Badge></TabsTrigger>
                                </TabsList>
                                <TabsContent value="overview">
                                    <EmptyState icon={Boxes} title="Nothing needs attention" description="Every lot in this workspace has passed the checks you configured." size="sm" />
                                </TabsContent>
                                <TabsContent value="lots">
                                    <EmptyState icon={FileText} title="No lots in range" size="sm" />
                                </TabsContent>
                                <TabsContent value="gaps">
                                    <div className="space-y-2 pt-2">
                                        <Skeleton className="h-10 w-full" />
                                        <Skeleton className="h-10 w-full" />
                                        <Skeleton className="h-10 w-2/3" />
                                    </div>
                                </TabsContent>
                            </Tabs>
                        </div>
                    </div>
                </Section>
            </div>
        </Container>
    );
}
