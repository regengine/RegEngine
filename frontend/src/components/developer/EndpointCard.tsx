'use client';

import { Badge } from '@/components/ui/badge';
import { CodeBlock } from './CodeBlock';
import type { CodeSnippet } from './CodeBlock';

interface EndpointCardProps {
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
    path?: string;
    endpoint?: string;
    title?: string;
    description: string;
    snippets: CodeSnippet[];
    parameters?: { name: string; type: string; required: boolean; desc?: string; description?: string }[];
    responseExample?: string | Record<string, unknown>;
}

const METHOD_COLORS: Record<string, { text: string; bg: string; border: string }> = {
    GET: { text: '#60a5fa', bg: 'rgba(96,165,250,0.08)', border: 'rgba(96,165,250,0.2)' },
    POST: { text: '#10b981', bg: 'rgba(16,185,129,0.08)', border: 'rgba(16,185,129,0.2)' },
    PUT: { text: '#f59e0b', bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.2)' },
    DELETE: { text: '#f87171', bg: 'rgba(248,113,113,0.08)', border: 'rgba(248,113,113,0.2)' },
    PATCH: { text: '#a78bfa', bg: 'rgba(167,139,250,0.08)', border: 'rgba(167,139,250,0.2)' },
};

export function EndpointCard({ method, path, endpoint, title, description, snippets, parameters, responseExample }: EndpointCardProps) {
    const colors = METHOD_COLORS[method] || METHOD_COLORS.GET;
    const displayPath = path || endpoint || '';
    const responseStr = typeof responseExample === 'string' ? responseExample : responseExample ? JSON.stringify(responseExample, null, 2) : undefined;

    return (
        <div className="rounded-lg p-5 space-y-4 mb-6" style={{
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.06)',
        }}>
            {/* Method + Path */}
            <div className="flex items-center gap-3">
                <Badge className="font-mono text-xs px-2 py-0.5" style={{
                    color: colors.text, background: colors.bg, border: `1px solid ${colors.border}`,
                }}>
                    {method}
                </Badge>
                <code className="text-sm font-mono" style={{ color: 'var(--re-text-primary)' }}>{displayPath}</code>
            </div>

            {/* Title */}
            {title && <h3 className="text-base font-semibold" style={{ color: 'var(--re-text-primary)', margin: 0 }}>{title}</h3>}

            {/* Description */}
            <p className="text-sm" style={{ color: 'var(--re-text-muted)' }}>{description}</p>

            {/* Parameters table */}
            {parameters && parameters.length > 0 && (
                <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--re-text-disabled)' }}>
                        Parameters
                    </h4>
                    <div className="rounded-md overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.06)' }}>
                        {parameters.map((p, i) => (
                            <div key={p.name} className="flex items-center gap-4 px-3 py-2 text-xs" style={{
                                background: i % 2 === 0 ? 'rgba(0,0,0,0.1)' : 'rgba(0,0,0,0.05)',
                                borderBottom: i < parameters.length - 1 ? '1px solid rgba(255,255,255,0.04)' : 'none',
                            }}>
                                <code className="font-mono font-medium w-36" style={{ color: 'var(--re-text-primary)' }}>{p.name}</code>
                                <span className="w-16" style={{ color: 'var(--re-text-disabled)' }}>{p.type}</span>
                                {p.required && <Badge variant="outline" className="text-[10px] px-1.5" style={{ color: '#f59e0b', borderColor: 'rgba(245,158,11,0.3)' }}>required</Badge>}
                                <span className="flex-1" style={{ color: 'var(--re-text-muted)' }}>{p.desc || p.description}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Code snippets */}
            <CodeBlock snippets={snippets} title="Request" />

            {/* Response example */}
            {responseStr && (
                <CodeBlock
                    snippets={[{ language: 'json', label: 'Response', code: responseStr }]}
                    title="Response · 200"
                />
            )}
        </div>
    );
}
