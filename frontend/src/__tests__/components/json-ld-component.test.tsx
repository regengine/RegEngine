import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { JSONLD } from '@/components/seo/json-ld';

describe('JSONLD', () => {
    it('renders raw JSON-LD markup while escaping tag-breaking payloads', async () => {
        const markup = renderToStaticMarkup(
            await JSONLD({
                nonce: 'test-nonce',
                data: {
                    '@context': 'https://schema.org',
                    '@type': 'SoftwareApplication',
                    name: 'RegEngine</script><script>alert(1)</script>',
                },
            }),
        );

        expect(markup).toContain('nonce="test-nonce"');
        expect(markup).toContain('type="application/ld+json"');
        expect(markup).toContain('{"@context":"https://schema.org"');
        expect(markup).not.toContain('&quot;');
        expect(markup).not.toContain('</script><script>alert(1)</script>');
        expect(markup).toContain('RegEngine\\u003c/script>\\u003cscript>alert(1)\\u003c/script>');
    });
});
