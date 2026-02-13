#!/usr/bin/env node
/**
 * M-1 Phase 4: remaining compound patterns + marketing footer + T refs
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SRC = path.join(__dirname, '..', 'src');

const REPLACEMENTS = [
    // T-object section titles
    ["style={{ fontSize: 'clamp(24px, 4vw, 36px)', fontWeight: 700, color: T.heading, marginBottom: 12 }}", 'className="re-section-title"'],
    ["style={{ fontSize: 'clamp(24px, 4vw, 36px)', fontWeight: 700, color: T.heading }}", 'className="re-section-title"'],

    // T-object body/muted text
    ["style={{ fontSize: 14, color: T.textMuted }}", 'className="text-sm text-re-text-muted"'],
    ["style={{ fontSize: 13, color: T.textMuted }}", 'className="text-[13px] text-re-text-muted"'],
    ["style={{ fontSize: 12, color: T.textDim, fontWeight: 500 }}", 'className="text-xs text-re-text-disabled font-medium"'],
    ["style={{ fontSize: 11, color: T.textDim }}", 'className="text-[11px] text-re-text-disabled"'],
    ["style={{ fontSize: '14px', color: T.text }}", 'className="text-sm text-re-text-secondary"'],
    ["style={{ fontSize: '14px', color: T.textMuted, margin: 0 }}", 'className="text-sm text-re-text-muted m-0"'],
    ["style={{ fontSize: '13px', color: T.textDim }}", 'className="text-[13px] text-re-text-disabled"'],

    // T-object icon sizes with color
    ["style={{ width: 28, height: 28, color: T.accent }}", 'className="w-7 h-7 text-re-brand"'],
    ["style={{ width: 16, height: 16, color: T.accent }}", 'className="w-4 h-4 text-re-brand"'],
    ["style={{ width: 20, height: 20, display: 'inline', verticalAlign: 'middle', marginRight: '8px' }}", 'className="w-5 h-5 inline align-middle mr-2"'],
    ["style={{ width: 14, height: 14, marginRight: 6 }}", 'className="w-3.5 h-3.5 mr-1.5"'],
    ["style={{ width: 8, height: 8, borderRadius: '50%', background: T.accent }}", 'className="w-2 h-2 rounded-full bg-re-brand"'],

    // Layout
    ["style={{ display: 'flex', flexDirection: 'column', gap: 16 }}", 'className="flex flex-col gap-4"'],
    ["style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}", 'className="flex gap-3 justify-center flex-wrap"'],
    ["style={{ display: 'flex', alignItems: 'center', gap: '6px' }}", 'className="flex items-center gap-1.5"'],
    ["style={{ textAlign: 'center', marginBottom: 48 }}", 'className="text-center mb-12"'],

    // Quoted var colors 
    ["style={{ color: \"var(--re-warning)\" }}", 'className="text-re-warning"'],
    ["style={{ color: \"var(--re-brand)\" }}", 'className="text-re-brand"'],

    // Common doc patterns
    ["style={{ textDecoration: 'none', color: 'inherit' }}", 'className="no-underline text-inherit"'],
    ["style={{ color: 'var(--text-muted)', textDecoration: 'none', display: 'block', padding: '0.2rem 0' }}", 'className="text-re-text-muted no-underline block py-[0.2rem]"'],
    ["style={{ marginBottom: '0.75rem' }}", 'className="mb-3"'],
    ["style={{ fontSize: '20px', marginBottom: '8px' }}", 'className="text-xl mb-2"'],
    ["style={{ fontSize: '1.15rem', marginBottom: '0.5rem' }}", 'className="text-lg mb-2"'],
    ["style={{ fontSize: '0.88rem', color: 'var(--text-muted)', lineHeight: '1.55', marginBottom: '1rem' }}", 'className="text-sm text-re-text-muted leading-relaxed mb-4"'],

    // Marketing footer patterns
    ["style={{ fontSize: \"12px\", fontWeight: 600, color: \"var(--re-text-muted)\", letterSpacing: \"0.08em\", textTransform: \"uppercase\", marginBottom: \"16px\" }}", 'className="text-xs font-semibold text-re-text-muted tracking-wider uppercase mb-4"'],
    ["style={{ fontSize: \"13px\", color: \"var(--re-text-tertiary)\", textDecoration: \"none\", marginBottom: \"10px\", display: \"block\" }}", 'className="text-[13px] text-re-text-tertiary no-underline mb-2.5 block"'],
    ["style={{ fontSize: \"12px\", color: \"var(--re-text-disabled)\" }}", 'className="text-xs text-re-text-disabled"'],

    // Label patterns
    ["style={{ fontSize: '12px', fontWeight: 600, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: '6px' }}", 'className="text-xs font-semibold text-re-text-muted uppercase tracking-wide block mb-1.5"'],
    ["style={{ fontSize: '14px', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '4px' }}", 'className="text-sm font-semibold text-re-text-primary mb-1"'],
    ["style={{ fontSize: '13px', color: 'var(--re-text-muted)', margin: '0 0 16px' }}", 'className="text-[13px] text-re-text-muted mb-4"'],

    // Page widths
    ["style={{ maxWidth: \"720px\", margin: \"0 auto\", padding: \"60px 24px\" }}", 'className="max-w-[720px] mx-auto py-[60px] px-6"'],

    // T dim labels
    ["style={{ fontSize: \"11px\", fontFamily: T.mono, fontWeight: 500, color: T.textDim, letterSpacing: \"0.1em\", textTransform: \"uppercase\" }}", 'className="text-[11px] font-mono font-medium text-re-text-disabled tracking-widest uppercase"'],

    // Nav link patterns
    ["style={{ display: \"flex\", alignItems: \"center\", gap: \"10px\", padding: \"8px 16px\", textDecoration: \"none\", transition: \"background 0.15s\" }}", 'className="flex items-center gap-2.5 py-2 px-4 no-underline transition-[background] duration-150"'],

    // Table cells
    ["style={{ padding: '12px 16px', color: T.textMuted, fontSize: '14px' }}", 'className="px-4 py-3 text-re-text-muted text-sm"'],
    ["style={{ padding: '12px 16px', color: 'var(--re-text-primary)', fontWeight: 500 }}", 'className="px-4 py-3 text-re-text-primary font-medium"'],

    // Footer text snippets
    ["style={{ fontSize: \"14px\", color: T.textMuted, lineHeight: 1.6, margin: 0 }}", 'className="text-sm text-re-text-muted leading-relaxed m-0"'],
    ["style={{ textAlign: 'center', padding: '16px', fontSize: '13px', color: T.textDim }}", 'className="text-center p-4 text-[13px] text-re-text-disabled"'],
    ["style={{ textAlign: 'center', padding: '14px 16px', fontSize: '13px', color: T.textDim }}", 'className="text-center px-4 py-3.5 text-[13px] text-re-text-disabled"'],

    // Page subtitle
    ["style={{ color: T.text, fontSize: '14px', marginBottom: '20px', maxWidth: '400px', margin: '0 auto 20px' }}", 'className="text-re-text-secondary text-sm mb-5 max-w-[400px] mx-auto"'],
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

        // Case 1: Has className before
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

console.log(`\nTotal Phase 4: ${totalReplacements} replacements`);

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
