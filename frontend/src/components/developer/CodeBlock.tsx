'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

export interface CodeSnippet {
    language: string;
    label: string;
    code: string;
}

interface CodeBlockProps {
    snippets: CodeSnippet[];
    title?: string;
}

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
        <div className="rounded-lg overflow-hidden" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
            {/* Header: title + language tabs + copy */}
            <div className="flex items-center justify-between px-4 py-2" style={{
                background: 'rgba(0,0,0,0.4)',
                borderBottom: '1px solid rgba(255,255,255,0.06)',
            }}>
                <div className="flex items-center gap-1">
                    {title && (
                        <span className="text-[11px] font-medium mr-3" style={{ color: 'var(--re-text-disabled)' }}>
                            {title}
                        </span>
                    )}
                    {snippets.map((s, i) => (
                        <button
                            key={s.language}
                            onClick={() => { setActiveIdx(i); setCopied(false); }}
                            className="px-2.5 py-1 rounded text-[11px] font-medium transition-colors"
                            style={{
                                background: i === activeIdx ? 'rgba(16,185,129,0.15)' : 'transparent',
                                color: i === activeIdx ? 'var(--re-brand)' : 'var(--re-text-disabled)',
                            }}
                        >
                            {s.label}
                        </button>
                    ))}
                </div>
                <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] transition-colors hover:bg-white/5"
                    style={{ color: copied ? 'var(--re-brand)' : 'var(--re-text-disabled)' }}
                >
                    {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    {copied ? 'Copied' : 'Copy'}
                </button>
            </div>
            {/* Code body */}
            <pre className="p-4 overflow-x-auto text-[13px] leading-relaxed" style={{
                background: 'rgba(0,0,0,0.3)',
                margin: 0,
            }}>
                <code style={{ color: 'var(--re-text-muted)', fontFamily: 'var(--re-font-mono, ui-monospace, monospace)' }}>
                    {active.code}
                </code>
            </pre>
        </div>
    );
}
