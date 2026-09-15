'use client';

import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

interface CodeBlockProps {
  code: string;
  language?: string;
  showLineNumbers?: boolean;
  copyable?: boolean;
}

/**
 * Code block — SPEC §4/§5.1.
 *
 * `Card variant="inset"`: code is a well, so it sits one surface step *below*
 * the card it is on, bounded by a subtle hairline rather than a shadow. The
 * copy control is a real `Button variant="ghost" size="icon"` so it picks up
 * the system's focus ring and hit area; its `aria-label` still flips between
 * "Copy code" and "Copied".
 */
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
    <Card variant="inset" className="group relative overflow-hidden">
      {/* Language label */}
      {language && (
        <span
          className={`pointer-events-none absolute top-3 font-mono text-label uppercase text-re-text-muted ${
            copyable ? 'right-12' : 'right-4'
          }`}
        >
          {language}
        </span>
      )}

      {/* Copy button */}
      {copyable && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={handleCopy}
          aria-label={copied ? 'Copied' : 'Copy code'}
          className="absolute right-1.5 top-1.5 opacity-0 transition-opacity duration-120 focus-visible:opacity-100 group-hover:opacity-100 motion-reduce:transition-none"
        >
          {copied ? (
            <Check aria-hidden="true" strokeWidth={1.75} className="text-re-success" />
          ) : (
            <Copy aria-hidden="true" strokeWidth={1.75} />
          )}
        </Button>
      )}

      {/* Code body */}
      <pre className="m-0 overflow-x-auto p-4 font-mono text-[0.8125rem] leading-6 text-re-text-primary">
        <code>
          {showLineNumbers
            ? lines.map((line, i) => (
              <span key={i} className="table-row">
                <span className="table-cell min-w-[2.5rem] select-none pr-4 text-right text-re-text-disabled">
                  {i + 1}
                </span>
                <span className="table-cell whitespace-pre">{line}</span>
              </span>
            ))
            : code}
        </code>
      </pre>
    </Card>
  );
}
