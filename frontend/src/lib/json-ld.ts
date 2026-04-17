/**
 * Serialize a value for embedding inside an inline `<script>` tag.
 *
 * `JSON.stringify` alone is unsafe: if the data ever contains the string
 * "</script>", "<script>", or "<!--", the browser parses it as HTML and the
 * <script> block terminates early. Unicode-escaping every `<` neutralizes
 * all three while remaining valid JSON.
 *
 * Use for every `dangerouslySetInnerHTML` that serializes JSON (JSON-LD,
 * hydration payloads, etc.).
 */
export function stringifyForScript(value: unknown): string {
    return JSON.stringify(value).replace(/</g, '\\u003c');
}
