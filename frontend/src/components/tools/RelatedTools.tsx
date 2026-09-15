import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { Container } from '@/components/layout/container';

interface RelatedTool {
    href: string;
    title: string;
    description: string;
}

/**
 * Related free tools — the same ledger-row recipe as
 * `@/components/layout/related-tools` (SPEC §6), rendered from this module's
 * own `{href, title, description}` prop shape. Both module paths stay exported:
 * the two are imported from twenty-six places between them and page tests mock
 * them by path.
 */
export function RelatedTools({ tools }: { tools: RelatedTool[] }) {
    return (
        <Container as="section" width="tool" className="pb-16 pt-4">
            <h2 className="mb-3 text-label uppercase text-re-text-muted">Related Free Tools</h2>
            <ul className="list-none p-0">
                {tools.map((tool) => (
                    <li key={tool.href} className="border-b border-re-border-subtle last:border-b-0">
                        <Link
                            href={tool.href}
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
        </Container>
    );
}
