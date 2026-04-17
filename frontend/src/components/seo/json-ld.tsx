import { stringifyForScript } from '@/lib/json-ld';

export function JSONLD({ data }: { data: Record<string, unknown> }) {
    return (
        <script
            type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: stringifyForScript(data) }}
        />
    );
}
