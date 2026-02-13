#!/usr/bin/env node
/**
 * M-1 Phase 5: final sweep of remaining convertible patterns
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SRC = path.join(__dirname, '..', 'src');

const REPLACEMENTS = [
    // var(--re-*) single-prop leftovers
    ["style={{ color: \"var(--re-text-disabled)\" }}", 'className="text-re-text-disabled"'],
    ["style={{ background: 'var(--re-surface-elevated)', color: 'var(--re-text-primary)' }}", 'className="bg-re-surface-elevated text-re-text-primary"'],

    // T-object remaining patterns
    ["style={{ color: T.textMuted, fontSize: '13px', textDecoration: 'none' }}", 'className="text-re-text-muted text-[13px] no-underline"'],
    ["style={{ color: T.text, fontSize: '14px', margin: 0 }}", 'className="text-re-text-secondary text-sm m-0"'],
    ["style={{ width: 32, height: 32, color: T.accent, margin: '0 auto 16px' }}", 'className="w-8 h-8 text-re-brand mx-auto mb-4"'],
    ["style={{ width: 20, height: 20, color: T.accent }}", 'className="w-5 h-5 text-re-brand"'],
    ["style={{ width: 16, height: 16, color: T.textMuted }}", 'className="w-4 h-4 text-re-text-muted"'],

    // Layout patterns
    ["style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}", 'className="flex items-center gap-2.5 mb-2"'],
    ["style={{ marginTop: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}", 'className="mt-6 flex items-center justify-between"'],
    ["style={{ paddingTop: 0 }}", 'className="pt-0"'],
    ["style={{ marginLeft: 8, width: 16, height: 16 }}", 'className="ml-2 w-4 h-4"'],
    ["style={{ maxWidth: '900px', margin: '0 auto', padding: '48px 24px' }}", 'className="max-w-[900px] mx-auto py-12 px-6"'],
    ["style={{ maxWidth: '1000px', margin: '0 auto' }}", 'className="max-w-[1000px] mx-auto"'],
    ["style={{ marginBottom: '16px', opacity: 0.9 }}", 'className="mb-4 opacity-90"'],

    // Section wrappers
    ["style={{ position: \"relative\", zIndex: 2, maxWidth: \"720px\", margin: \"0 auto\", padding: \"80px 24px 60px\" }}", 'className="relative z-[2] max-w-[720px] mx-auto pt-20 px-6 pb-[60px]"'],
    ["style={{ position: \"relative\", zIndex: 2, maxWidth: \"720px\", margin: \"0 auto\", padding: \"80px 24px 48px\" }}", 'className="relative z-[2] max-w-[720px] mx-auto pt-20 px-6 pb-12"'],
    ["style={{ position: \"relative\", zIndex: 2, maxWidth: \"720px\", margin: \"0 auto\", padding: \"60px 24px 80px\" }}", 'className="relative z-[2] max-w-[720px] mx-auto py-[60px] px-6 pb-20"'],
    ["style={{ position: \"relative\", zIndex: 2, maxWidth: \"720px\", margin: \"0 auto\", padding: \"0 24px 80px\" }}", 'className="relative z-[2] max-w-[720px] mx-auto px-6 pb-20"'],
    ["style={{ position: \"relative\", zIndex: 2, maxWidth: \"1120px\", margin: \"0 auto\", padding: \"100px 24px\" }}", 'className="relative z-[2] max-w-[1120px] mx-auto py-[100px] px-6"'],

    // caption labels
    ["style={{ padding: \"4px 16px 8px\", fontSize: \"10px\", fontWeight: 600, letterSpacing: \"0.08em\", color: \"var(--re-text-muted)\", textTransform: \"uppercase\" as const }}", 'className="px-4 pt-1 pb-2 text-[10px] font-semibold tracking-wider text-re-text-muted uppercase"'],

    // nv-* legacy custom props
    ["style={{ color: 'var(--nv-text-dim)' }}", 'className="text-re-text-disabled"'],
    ["style={{ color: 'var(--nv-accent)', fontSize: '0.82rem' }}", 'className="text-re-brand text-[0.82rem]"'],
    ["style={{ color: 'var(--accent-emerald)', fontSize: '0.85rem', fontWeight: 500 }}", 'className="text-re-brand text-[0.85rem] font-medium"'],
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

console.log(`\nTotal Phase 5: ${totalReplacements} replacements`);

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
