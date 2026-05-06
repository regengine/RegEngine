import { headers } from 'next/headers';
import type { ScriptHTMLAttributes } from 'react';
import { stringifyForScript } from '@/lib/json-ld';

type JSONLDProps = {
    data: Record<string, unknown>;
    nonce?: string;
};

export async function JSONLD({ data, nonce }: JSONLDProps) {
    const resolvedNonce = nonce ?? (await headers()).get('x-nonce') ?? undefined;
    const scriptProps: ScriptHTMLAttributes<HTMLScriptElement> = {
        nonce: resolvedNonce,
        suppressHydrationWarning: true,
        type: 'application/ld+json',
        // JSON-LD must remain raw script text; stringifyForScript escapes tag-breaking "<" sequences.
        // nosemgrep: typescript.react.security.audit.react-dangerouslysetinnerhtml.react-dangerouslysetinnerhtml
        dangerouslySetInnerHTML: { __html: stringifyForScript(data) },
    };

    return <script {...scriptProps} />;
}
