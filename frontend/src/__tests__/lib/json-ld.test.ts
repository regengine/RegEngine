/**
 * XSS regression tests for `stringifyForScript`.
 *
 * `stringifyForScript` is the serializer used by every `dangerouslySetInnerHTML`
 * that embeds JSON in an inline `<script>` tag (JSON-LD schema blocks in
 * layout.tsx, hydration payloads, OG image data).
 *
 * Raw `JSON.stringify` is unsafe: if attacker-controlled data ever contains
 * "</script>", "<script>", or "<!--", the browser parses it as HTML and the
 * <script> block terminates early, allowing arbitrary JS. This test pins the
 * unicode-escape behavior so a regression can't silently reintroduce the
 * vulnerability.
 *
 * Related: #1200 (escape `</script>` in JSON-LD, drop unused dompurify)
 */

import { describe, it, expect } from 'vitest';
import { stringifyForScript } from '@/lib/json-ld';

describe('stringifyForScript — XSS guard for inline JSON-LD scripts', () => {
    it('escapes a raw </script> tag in a string field', () => {
        const payload = {
            '@type': 'Organization',
            name: 'Evil</script><script>alert(1)</script>',
        };
        const out = stringifyForScript(payload);
        expect(out).not.toContain('</script>');
        expect(out).not.toContain('<script>');
        // `<` is unicode-escaped; `>` stays literal but is harmless alone.
        expect(out).toContain('\\u003c/script>');
    });

    it('escapes a <!-- HTML comment that could terminate the script', () => {
        const out = stringifyForScript({ description: 'hello <!-- inline' });
        expect(out).not.toContain('<!--');
        // `<` is escaped, so the comment-start sequence is broken.
        expect(out).toContain('\\u003c!--');
    });

    it('escapes ALL angle brackets, not just the first', () => {
        const out = stringifyForScript({ a: '<one>', b: '<two>' });
        const lessThanCount = (out.match(/</g) || []).length;
        expect(lessThanCount).toBe(0);
    });

    it('survives a malicious key as well as a malicious value', () => {
        const key = '</script><img src=x onerror=alert(1)>';
        const out = stringifyForScript({ [key]: 'value' });
        expect(out).not.toContain('</script>');
        expect(out).not.toContain('<img');
    });

    it('remains valid JSON after escaping (roundtrip)', () => {
        const payload = {
            '@context': 'https://schema.org',
            '@type': 'Product',
            description: 'Product with </script>inline',
        };
        const out = stringifyForScript(payload);
        // JSON.parse unescapes \u003c back to <
        const parsed = JSON.parse(out);
        expect(parsed.description).toBe('Product with </script>inline');
        expect(parsed['@type']).toBe('Product');
    });

    it('handles nested attacker-controlled data in arrays', () => {
        const out = stringifyForScript({
            itemListElement: [
                { '@type': 'ListItem', name: '<evil>' },
                { '@type': 'ListItem', name: '</script>' },
            ],
        });
        expect(out).not.toContain('</script>');
        expect(out).not.toContain('<evil>');
    });

    it('does not alter non-hostile content', () => {
        const out = stringifyForScript({ name: 'RegEngine', version: 1, ok: true });
        expect(out).toBe('{"name":"RegEngine","version":1,"ok":true}');
    });
});
