#!/usr/bin/env node
/**
 * M-1 Phase 3: T-object refs + frequent compound patterns
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SRC = path.join(__dirname, '..', 'src');

// Exact string replacements: [target, replacement]
const REPLACEMENTS = [
    // === T-object single-property ===
    ["style={{ color: T.accent }}", 'className="text-re-brand"'],
    ["style={{ color: T.text }}", 'className="text-re-text-secondary"'],
    ["style={{ color: T.textMuted }}", 'className="text-re-text-muted"'],
    ["style={{ color: T.textDim }}", 'className="text-re-text-disabled"'],
    ["style={{ color: T.heading }}", 'className="text-re-text-primary"'],
    ["style={{ color: T.warning }}", 'className="text-re-warning"'],
    ["style={{ color: T.danger }}", 'className="text-re-danger"'],

    // === Common multi-prop patterns ===
    // Section label (12px uppercase accent)
    ["style={{ fontSize: 12, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8, fontWeight: 600 }}", 'className="re-section-label"'],

    // Page shell
    ["style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.fontSans }}", 'className="re-page"'],
    ["style={{ minHeight: \"100vh\", background: T.bg, fontFamily: T.sans, color: T.textBody }}", 'className="re-page"'],

    // Page content wrappers
    ["style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px 60px' }}", 'className="re-page-content"'],
    ["style={{ maxWidth: '700px', margin: '0 auto', padding: '48px 24px' }}", 'className="re-page-narrow"'],
    ["style={{ maxWidth: '700px', margin: '0 auto' }}", 'className="max-w-[700px] mx-auto"'],
    ["style={{ maxWidth: '900px', margin: '0 auto' }}", 'className="max-w-[900px] mx-auto"'],

    // Doc headings
    ["style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--re-text-primary)', marginBottom: '8px' }}", 'className="re-heading-xl"'],
    ["style={{ fontSize: '1.5rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}", 'className="re-heading-lg"'],
    ["style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}", 'className="re-heading-md"'],
    ["style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '8px' }}", 'className="re-heading-sm"'],
    ["style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '12px' }}", 'className="re-heading-sm"'],

    // Code blocks
    ["style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: 'var(--re-text-tertiary)' }}", 'className="re-code-block"'],

    // Body text patterns
    ["style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}", 'className="re-body"'],
    ["style={{ color: T.textMuted, fontSize: '16px' }}", 'className="text-re-text-muted text-base"'],
    ["style={{ fontSize: '14px', color: T.textMuted }}", 'className="text-sm text-re-text-muted"'],
    ["style={{ fontSize: '13px', color: T.textMuted }}", 'className="text-[13px] text-re-text-muted"'],
    ["style={{ fontSize: '12px', color: T.textMuted }}", 'className="text-xs text-re-text-muted"'],
    ["style={{ fontSize: '12px', color: T.accent }}", 'className="text-xs text-re-brand"'],

    // Layout patterns
    ["style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}", 'className="flex items-center gap-3 mb-3"'],
    ["style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}", 'className="flex items-start gap-4"'],
    ["style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}", 'className="flex items-start gap-3"'],
    ["style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}", 'className="flex items-center justify-between"'],
    ["style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}", 'className="flex gap-3 justify-center flex-wrap"'],

    // Spacing
    ["style={{ marginBottom: '40px' }}", 'className="mb-10"'],
    ["style={{ textAlign: 'center', marginBottom: 40 }}", 'className="text-center mb-10"'],
    ["style={{ marginTop: '48px', textAlign: 'center' }}", 'className="mt-12 text-center"'],

    // Tables
    ["style={{ width: '100%', borderCollapse: 'collapse' }}", 'className="re-table"'],

    // Misc
    ["style={{ fontSize: '0.75rem', color: '#64748b' }}", 'className="text-xs text-re-text-muted"'],
    ["style={{ fontSize: \"14px\" }}", 'className="text-sm"'],
    ["style={{ fontSize: \"11px\", color: \"var(--re-text-muted)\" }}", 'className="text-[11px] text-re-text-muted"'],
    ["style={{ fontSize: '12px', color: 'var(--re-text-muted)', lineHeight: 1.4 }}", 'className="text-xs text-re-text-muted leading-tight"'],
    ["style={{ fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '4px' }}", 'className="font-semibold text-re-text-primary mb-1"'],
    ["style={{ fontSize: '20px', fontWeight: 700, color: 'var(--re-text-primary)', margin: '0 0 4px' }}", 'className="text-xl font-bold text-re-text-primary mb-1"'],
    ["style={{ padding: '12px 16px' }}", 'className="px-4 py-3"'],

    // Icon patterns
    ["style={{ width: '6px', height: '6px', borderRadius: '50%', background: T.accent }}", 'className="re-dot bg-re-brand"'],

    // T.accent link patterns
    ["style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: T.accent, textDecoration: 'none' }}", 'className="flex items-center gap-2 text-[13px] text-re-brand no-underline"'],

    // Brand badge
    ["style={{ background: 'var(--re-brand)', color: 'var(--re-surface-base)' }}", 'className="bg-re-brand text-re-surface-base"'],

    // Table cells
    ["style={{ textAlign: 'left', padding: '12px 16px', color: T.textMuted, fontSize: '12px', fontWeight: 600 }}", 'className="text-left px-4 py-3 text-re-text-muted text-xs font-semibold"'],
    ["style={{ padding: '12px 16px', color: T.text, fontSize: '14px' }}", 'className="px-4 py-3 text-re-text-secondary text-sm"'],

    // CTA backgrounds
    ["style={{ borderColor: 'var(--re-border-default)', background: 'var(--re-surface-elevated)' }}", 'className="border-re-border bg-re-surface-elevated"'],

    // Info color
    ["style={{ color: \"var(--re-info)\" }}", 'className="text-re-info"'],

    // Font size 13px primary
    ["style={{ fontSize: \"13px\", fontWeight: 500, color: \"var(--re-text-primary)\" }}", 'className="text-[13px] font-medium text-re-text-primary"'],
];

const files = execSync(
    `grep -rl "style={{" --include="*.tsx" --include="*.ts" ${SRC}`,
    { encoding: 'utf8' }
).trim().split('\n');

let totalReplacements = 0;

for (const file of files) {
    let content = fs.readFileSync(file, 'utf8');
    let fileReplacements = 0;

    for (const [target, replacement] of REPLACEMENTS) {
        const twClasses = replacement.replace(/className="([^"]*)"/, '$1');

        // Case 1: Has className before the style
        const withClassBefore = new RegExp(
            `(className=["'])([^"']*)(["'])\\s*` + escapeRegex(target),
            'g'
        );
        let matches = content.match(withClassBefore);
        if (matches) {
            content = content.replace(withClassBefore, `$1$2 ${twClasses}$3`);
            fileReplacements += matches.length;
            continue;
        }

        // Case 2: Standalone
        const standalone = new RegExp(escapeRegex(target), 'g');
        matches = content.match(standalone);
        if (matches) {
            content = content.replace(standalone, replacement);
            fileReplacements += matches.length;
        }
    }

    if (fileReplacements > 0) {
        fs.writeFileSync(file, content);
        console.log(`${path.relative(SRC, file)}: ${fileReplacements} replacements`);
        totalReplacements += fileReplacements;
    }
}

console.log(`\nTotal Phase 3: ${totalReplacements} replacements`);

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
