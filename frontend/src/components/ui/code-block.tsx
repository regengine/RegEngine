'use client';

import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  code: string;
  language?: string;
  showLineNumbers?: boolean;
  copyable?: boolean;
}

export function CodeBlock({
  code,
  language,
  showLineNumbers = false,
  copyable = true,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [code]);

  const lines = code.split('\n');

  return (
    <div
      className="relative rounded-lg overflow-hidden group"
      style={{
        background: 'var(--re-surface-card, rgba(0,0,0,0.3))',
        border: '1px solid var(--re-surface-border, rgba(255,255,255,0.08))',
      }}
    >
      {/* Language badge */}
      {language && (
        <span
          className="absolute top-2 right-10 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded"
          style={{
            background: 'rgba(255,255,255,0.06)',
            color: 'var(--re-text-muted, #999)',
          }}
        >
          {language}
        </span>
      )}

      {/* Copy button */}
      {copyable && (
        <button
          onClick={handleCopy}
          className="absolute top-2 right-2 p-1.5 rounded transition-opacity opacity-0 group-hover:opacity-100 focus:opacity-100"
          style={{
            background: 'rgba(255,255,255,0.08)',
            color: copied ? 'var(--re-brand, #10b981)' : 'var(--re-text-muted, #999)',
          }}
          aria-label={copied ? 'Copied' : 'Copy code'}
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      )}

      {/* Code body */}
      <pre
        className="p-4 overflow-x-auto text-[13px] leading-relaxed m-0"
        style={{ fontFamily: 'var(--re-font-mono, "JetBrains Mono", ui-monospace, monospace)' }}
      >
        <code style={{ color: 'var(--re-text-primary, #e0e0e0)' }}>
          {showLineNumbers
            ? lines.map((line, i) => (
                <span key={i} className="table-row">
                  <span
                    className="table-cell select-none text-right pr-4"
                    style={{
                      color: 'var(--re-text-disabled, #555)',
                      minWidth: '2.5rem',
                      userSelect: 'none',
                    }}
                  >
                    {i + 1}
                  </span>
                  <span className="table-cell whitespace-pre">{line}</span>
                </span>
              ))
            : code}
        </code>
      </pre>
    </div>
  );
}
