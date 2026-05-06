import { headers } from 'next/headers';
import { stringifyForScript } from '@/lib/json-ld';

type JSONLDProps = {
    data: Record<string, unknown>;
    nonce?: string;
};

export async function JSONLD({ data, nonce }: JSONLDProps) {
    const resolvedNonce = nonce ?? (await headers()).get('x-nonce') ?? undefined;

    return (
        <script
            nonce={resolvedNonce}
            suppressHydrationWarning
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: stringifyForScript(data) }}
        />
    );
}
