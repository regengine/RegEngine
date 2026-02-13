#!/usr/bin/env node
/**
 * M-1 Phase 2: Multi-property inline style replacements
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SRC = path.join(__dirname, '..', 'src');

// Exact multi-property replacements
const MULTI_PROP_MAP = {
    // Icon sizes
    "style={{ width: 16, height: 16 }}": 'className="w-4 h-4"',
    "style={{ width: 20, height: 20 }}": 'className="w-5 h-5"',
    "style={{ width: 24, height: 24 }}": 'className="w-6 h-6"',
    "style={{ width: 28, height: 28 }}": 'className="w-7 h-7"',
    "style={{ width: 14, height: 14 }}": 'className="w-3.5 h-3.5"',
    "style={{ width: 12, height: 12 }}": 'className="w-3 h-3"',
    "style={{ width: 10, height: 10 }}": 'className="w-2.5 h-2.5"',

    // Common layout patterns
    "style={{ display: 'grid', gap: '12px' }}": 'className="grid gap-3"',
    "style={{ display: 'flex', alignItems: 'center', gap: '8px' }}": 'className="flex items-center gap-2"',
    "style={{ display: 'flex', alignItems: 'center', gap: '12px' }}": 'className="flex items-center gap-3"',
    "style={{ display: 'flex', alignItems: 'center', gap: '16px' }}": 'className="flex items-center gap-4"',
    "style={{ display: 'flex', gap: '12px' }}": 'className="flex gap-3"',
    "style={{ display: 'flex', gap: '16px' }}": 'className="flex gap-4"',
    "style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}": 'className="flex flex-col gap-4"',
    "style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}": 'className="flex flex-col gap-3"',
    "style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}": 'className="flex flex-col gap-2"',

    // Spacing
    "style={{ marginBottom: '48px' }}": 'className="mb-12"',
    "style={{ marginBottom: '56px' }}": 'className="mb-14"',
    "style={{ marginBottom: '32px' }}": 'className="mb-8"',
    "style={{ marginBottom: '24px' }}": 'className="mb-6"',
    "style={{ marginBottom: '16px' }}": 'className="mb-4"',
    "style={{ marginBottom: '12px' }}": 'className="mb-3"',
    "style={{ marginBottom: '8px' }}": 'className="mb-2"',

    // Background
    "style={{ background: 'var(--re-surface-card)' }}": 'className="bg-re-surface-card"',
};

const files = execSync(
    `grep -rl "style={{" --include="*.tsx" --include="*.ts" ${SRC}`,
    { encoding: 'utf8' }
).trim().split('\n');

let totalReplacements = 0;

for (const file of files) {
    let content = fs.readFileSync(file, 'utf8');
    let fileReplacements = 0;

    for (const [styleAttr, replacement] of Object.entries(MULTI_PROP_MAP)) {
        // Case 1: Element already has className — merge
        // className="existing" style={{ width: 16, height: 16 }}
        const twClasses = replacement.replace(/className="([^"]*)"/, '$1');

        const withClassBefore = new RegExp(
            `(className=["'])([^"']*)(["'])\\s*` + escapeRegex(styleAttr),
            'g'
        );
        let matches = content.match(withClassBefore);
        if (matches) {
            content = content.replace(withClassBefore, `$1$2 ${twClasses}$3`);
            fileReplacements += matches.length;
            continue; // already handled
        }

        // Case 2: standalone style={{...}} — replace with className
        const standalone = new RegExp(escapeRegex(styleAttr), 'g');
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

console.log(`\nTotal Phase 2: ${totalReplacements} replacements`);

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
