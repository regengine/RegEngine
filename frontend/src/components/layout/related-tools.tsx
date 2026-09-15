import Link from 'next/link';
import { ChevronRight, type LucideIcon } from 'lucide-react';

interface RelatedTool {
    id: string;
    title: string;
    description: string;
    /** Accepted for call-site compatibility; the ledger rows carry no icon. */
    icon?: LucideIcon;
}

interface RelatedToolsProps {
    tools: RelatedTool[];
}

/**
 * Related tools — SPEC §6 "ledger-row lists".
 *
 * Hairline rows (title link + one-line description + a right chevron), not an
 * icon-card grid. `@/components/tools/RelatedTools` renders the identical row
 * recipe from a different prop shape; both module paths stay exported because
 * eighteen and eight call sites respectively import them, and page tests mock
 * them by path.
 */
export function RelatedTools({ tools }: RelatedToolsProps) {
    return (
        <div className="mt-12 border-t border-re-border-subtle pt-8">
            <h3 className="mb-4 text-heading text-re-text-primary">Related Tools</h3>
            <ul className="list-none p-0">
                {tools.map((tool) => (
                    <li key={tool.id} className="border-b border-re-border-subtle last:border-b-0">
                        <Link
                            href={`/tools/${tool.id}`}
                            className="group flex items-center gap-4 py-3 no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring"
                        >
                            <span className="min-w-0 flex-1">
                                <span className="block text-ui font-medium text-re-text-primary transition-colors duration-120 group-hover:text-re-brand motion-reduce:transition-none">
                                    {tool.title}
                                </span>
                                <span className="mt-0.5 block truncate text-small text-re-text-tertiary">
                                    {tool.description}
                                </span>
                            </span>
                            <ChevronRight
                                aria-hidden="true"
                                size={16}
                                strokeWidth={1.75}
                                className="shrink-0 text-re-text-muted transition-colors duration-120 group-hover:text-re-text-secondary motion-reduce:transition-none"
                            />
                        </Link>
                    </li>
                ))}
            </ul>
        </div>
    );
}
