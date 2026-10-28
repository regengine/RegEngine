import { Container } from '@/components/layout/container';

/**
 * SEL-585 F5: skeleton mirrors the real tools landing layout
 * (marketing hero plus category chips plus card grid).
 * Decorative blocks only. No tool names while loading.
 */
export default function ToolsLoading() {
    return (
        <div className="bg-re-surface-base" aria-busy="true" aria-label="Loading tools">
            {/* Hero skeleton */}
            <Container
                as="section"
                width="marketing"
                className="grid items-start gap-10 pb-10 pt-12 md:grid-cols-[0.75fr_1fr] md:pb-12 md:pt-16"
            >
                <div className="animate-pulse space-y-6 motion-reduce:animate-none" aria-hidden="true">
                    <div className="h-4 w-16 rounded bg-re-surface-inset" />
                    <div className="space-y-3">
                        <div className="h-8 w-3/4 rounded bg-re-surface-inset" />
                        <div className="h-8 w-1/2 rounded bg-re-surface-inset" />
                    </div>
                    <div className="h-4 w-full rounded bg-re-surface-inset" />
                </div>
                <div
                    className="animate-pulse divide-y divide-re-border-subtle overflow-hidden rounded-lg border border-re-border bg-re-surface-card motion-reduce:animate-none"
                    aria-hidden="true"
                >
                    {[0, 1, 2, 3].map((i) => (
                        <div key={i} className="flex items-baseline gap-4 px-4 py-2.5">
                            <div className="h-4 w-1/3 rounded bg-re-surface-inset" />
                            <div className="h-4 min-w-0 flex-1 rounded bg-re-surface-inset" />
                        </div>
                    ))}
                </div>
            </Container>

            <Container as="section" width="marketing" className="pb-16 pt-6 sm:pb-20">
                {/* Category chips skeleton */}
                <div className="mb-6 flex animate-pulse flex-wrap gap-2 motion-reduce:animate-none" aria-hidden="true">
                    {[0, 1, 2, 3, 4].map((i) => (
                        <div key={i} className="h-9 w-20 rounded-md border border-re-border bg-re-surface-card" />
                    ))}
                </div>

                {/* Card grid skeleton */}
                <div className="grid animate-pulse gap-4 motion-reduce:animate-none md:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
                    {[0, 1, 2, 3, 4, 5].map((i) => (
                        <div key={i} className="min-h-[210px] rounded-lg border border-re-border bg-re-surface-card p-5">
                            <div className="mb-8 flex items-center justify-between border-b border-re-border-subtle pb-3">
                                <div className="h-5 w-5 rounded bg-re-surface-inset" />
                                <div className="h-4 w-16 rounded bg-re-surface-inset" />
                            </div>
                            <div className="h-6 w-2/3 rounded bg-re-surface-inset" />
                            <div className="mt-3 h-4 w-full rounded bg-re-surface-inset" />
                        </div>
                    ))}
                </div>
            </Container>
        </div>
    );
}
