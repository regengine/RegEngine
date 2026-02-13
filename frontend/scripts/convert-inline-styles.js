#!/usr/bin/env node
/**
 * M-1 Inline Style → Tailwind Converter
 * Handles single-property style={{}} patterns that map directly to Tailwind classes.
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SRC = path.join(__dirname, '..', 'src');

// Map: style={{ property: 'value' }} → className additions
const SINGLE_PROP_MAP = {
    // Colors
    "style={{ color: 'var(--re-text-primary)' }}": 'text-re-text-primary',
    "style={{ color: 'var(--re-text-secondary)' }}": 'text-re-text-secondary',
    "style={{ color: 'var(--re-text-tertiary)' }}": 'text-re-text-tertiary',
    "style={{ color: 'var(--re-text-muted)' }}": 'text-re-text-muted',
    "style={{ color: 'var(--re-text-disabled)' }}": 'text-re-text-disabled',
    "style={{ color: 'var(--re-brand)' }}": 'text-re-brand',
    "style={{ color: 'var(--re-success)' }}": 'text-re-success',
    "style={{ color: 'var(--re-warning)' }}": 'text-re-warning',
    "style={{ color: 'var(--re-danger)' }}": 'text-re-danger',
    "style={{ color: 'var(--re-info)' }}": 'text-re-info',
    "style={{ color: 'var(--re-surface-base)' }}": 'text-re-surface-base',
    // Backgrounds
    "style={{ background: 'var(--re-surface-card)' }}": 'bg-re-surface-card',
    "style={{ background: 'var(--re-surface-base)' }}": 'bg-re-surface-base',
    "style={{ background: 'var(--re-surface-elevated)' }}": 'bg-re-surface-elevated',
    "style={{ background: 'var(--re-brand)' }}": 'bg-re-brand',
    "style={{ background: 'var(--re-success)' }}": 'bg-re-success',
    "style={{ background: 'var(--re-danger)' }}": 'bg-re-danger',
    "style={{ background: 'var(--re-warning)' }}": 'bg-re-warning',
    "style={{ backgroundColor: 'var(--re-surface-card)' }}": 'bg-re-surface-card',
    "style={{ backgroundColor: 'var(--re-text-disabled)' }}": 'bg-re-text-disabled',
    // Layout
    "style={{ flex: 1 }}": 'flex-1',
    "style={{ textAlign: 'center' }}": 'text-center',
    "style={{ textAlign: 'left' }}": 'text-left',
};

// Find all tsx files with style={{
const files = execSync(
    `grep -rl "style={{" --include="*.tsx" --include="*.ts" ${SRC}`,
    { encoding: 'utf8' }
).trim().split('\n');

let totalReplacements = 0;

for (const file of files) {
    let content = fs.readFileSync(file, 'utf8');
    let fileReplacements = 0;

    for (const [styleAttr, twClass] of Object.entries(SINGLE_PROP_MAP)) {
        // Pattern: already has className="..." before style={{
        // e.g., className="foo bar" style={{ color: 'var(--re-text-primary)' }}
        const withClassBefore = new RegExp(
            `(className=["'])([^"']*)(["'])\\s*` + escapeRegex(styleAttr),
            'g'
        );
        const matchesBefore = content.match(withClassBefore);
        if (matchesBefore) {
            content = content.replace(withClassBefore, `$1$2 ${twClass}$3`);
            fileReplacements += matchesBefore.length;
        }

        // Pattern: style={{ ... }} with className after
        const withClassAfter = new RegExp(
            escapeRegex(styleAttr) + `\\s*(className=["'])([^"']*)(["'])`,
            'g'
        );
        const matchesAfter = content.match(withClassAfter);
        if (matchesAfter) {
            content = content.replace(withClassAfter, `$1$2 ${twClass}$3`);
            fileReplacements += matchesAfter.length;
        }

        // Pattern: standalone style={{ ... }} with no className
        // Need to be careful — only match if there's no className nearby
        // Replace style={{...}} with className="twClass"
        const standalone = new RegExp(escapeRegex(styleAttr), 'g');
        const matchesStandalone = content.match(standalone);
        if (matchesStandalone) {
            content = content.replace(standalone, `className="${twClass}"`);
            fileReplacements += matchesStandalone.length;
        }
    }

    if (fileReplacements > 0) {
        fs.writeFileSync(file, content);
        console.log(`${path.relative(SRC, file)}: ${fileReplacements} replacements`);
        totalReplacements += fileReplacements;
    }
}

console.log(`\nTotal: ${totalReplacements} inline styles → Tailwind classes`);

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
