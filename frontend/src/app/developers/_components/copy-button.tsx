'use client';

import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';
import { T } from '../_data';

export function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);
    const copy = useCallback(() => {
        navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        });
    }, [text]);
    return (
        <button onClick={copy} aria-label={copied ? 'Copied' : 'Copy to clipboard'}
            style={{
                position: 'absolute', top: 12, right: 12,
                background: 'rgba(255,255,255,0.06)',
                border: `1px solid ${T.border}`, borderRadius: 6,
                padding: '4px 10px', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 5,
                fontSize: 11, color: copied ? T.accent : T.textMuted,
                transition: 'all 0.2s', zIndex: 5,
            }}>
            {copied ? <Check style={{ width: 12, height: 12 }} /> : <Copy style={{ width: 12, height: 12 }} />}
            {copied ? 'Copied!' : 'Copy'}
        </button>
    );
}
