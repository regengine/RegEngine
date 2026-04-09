import Link from 'next/link';

interface RelatedTool {
    href: string;
    title: string;
    description: string;
}

export function RelatedTools({ tools }: { tools: RelatedTool[] }) {
    return (
        <section className="max-w-4xl mx-auto px-4 sm:px-6 pb-16 pt-4">
            <h2 className="text-sm font-semibold text-[var(--re-text-muted)] uppercase tracking-wider mb-4">
                Related Free Tools
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {tools.map((tool) => (
                    <Link
                        key={tool.href}
                        href={tool.href}
                        className="rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 hover:border-[var(--re-brand)]/40 transition-colors group"
                    >
                        <span className="text-sm font-semibold text-[var(--re-brand)] group-hover:underline">
                            {tool.title}
                        </span>
                        <p className="text-xs text-[var(--re-text-muted)] mt-1 leading-relaxed">
                            {tool.description}
                        </p>
                    </Link>
                ))}
            </div>
        </section>
    );
}
