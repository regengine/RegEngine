import Link from 'next/link';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { ArrowRight, LucideIcon } from 'lucide-react';

interface RelatedTool {
    id: string;
    title: string;
    description: string;
    icon: LucideIcon;
}

interface RelatedToolsProps {
    tools: RelatedTool[];
}

export function RelatedTools({ tools }: RelatedToolsProps) {
    return (
        <div className="mt-16 pt-16 border-t border-[var(--re-border-default)]">
            <h3 className="text-2xl font-bold mb-8">Related Tools</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {tools.map((tool) => (
                    <Link key={tool.id} href={`/tools/${tool.id}`}>
                        <Card className="h-full border-[var(--re-border-default)] bg-[var(--re-surface-card)] hover:border-[var(--re-border-subtle)] transition-all group cursor-pointer">
                            <CardHeader className="space-y-3">
                                <div className="p-2 w-10 h-10 rounded-lg bg-[var(--re-surface-elevated)] flex items-center justify-center">
                                    <tool.icon className="h-5 w-5 text-[var(--re-brand)]" />
                                </div>
                                <div>
                                    <CardTitle className="text-lg group-hover:text-[var(--re-brand)] transition-colors">
                                        {tool.title}
                                    </CardTitle>
                                    <CardDescription className="text-sm line-clamp-2 mt-1">
                                        {tool.description}
                                    </CardDescription>
                                </div>
                                <div className="flex items-center text-xs font-bold text-[var(--re-brand)] opacity-0 group-hover:opacity-100 transition-opacity pt-2">
                                    Launch Tool <ArrowRight className="ml-1 h-3 w-3" />
                                </div>
                            </CardHeader>
                        </Card>
                    </Link>
                ))}
            </div>
        </div>
    );
}
