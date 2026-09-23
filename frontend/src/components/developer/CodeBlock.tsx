'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface CodeSnippet {
    language: string;
    label: string;
    code: string;
}

interface CodeBlockProps {
    snippets: CodeSnippet[];
    title?: string;
}

// Only rendered inside the developer portal (codegen page), so these tokens
// resolve against the .re-devportal scope — which also means the block
// automatically defers to forced high-contrast mode along with the rest of
// the portal. The /docs pages use @/components/ui/code-block, not this.
export function CodeBlock({ snippets, title }: CodeBlockProps) {
    const [activeIdx, setActiveIdx] = useState(0);
    const [copied, setCopied] = useState(false);

    const active = snippets[activeIdx];

    function handleCopy() {
        navigator.clipboard.writeText(active.code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    }

    return (
        <div className="overflow-hidden rounded-lg border border-re-border">
            {/* Header: title + language tabs + copy */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-re-border-subtle bg-re-surface-card px-4 py-2">
                <div className="flex flex-wrap items-center gap-1">
                    {title && (
                        <span className="mr-3 font-mono text-label text-re-text-muted">
                            {title}
                        </span>
                    )}
                    {snippets.map((s, i) => (
                        <button
                            key={s.language}
                            type="button"
                            onClick={() => { setActiveIdx(i); setCopied(false); }}
                            aria-pressed={i === activeIdx}
                            className={cn(
                                'rounded-sm px-2.5 py-1 text-[0.8125rem] transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none',
                                i === activeIdx
                                    ? 'bg-re-surface-inset font-medium text-re-text-primary'
                                    : 'text-re-text-tertiary hover:text-re-text-primary',
                            )}
                        >
                            {s.label}
                        </button>
                    ))}
                </div>
                <button
                    type="button"
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 rounded-sm px-2 py-1 text-[0.8125rem] text-re-text-tertiary transition-colors duration-120 hover:bg-re-surface-inset hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                >
                    {copied
                        ? <Check className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                        : <Copy className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />}
                    {copied ? 'Copied' : 'Copy'}
                </button>
            </div>
            {/* Code body */}
            <pre className="m-0 overflow-x-auto bg-re-surface-inset p-4 text-[0.8125rem] leading-relaxed">
                <code className="font-mono text-re-text-secondary">
                    {active.code}
                </code>
            </pre>
        </div>
    );
}
