#!/usr/bin/env node
/**
 * Fix duplicate className attributes created by Phase 1 script.
 * Merges two adjacent className attributes into one.
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const SRC = path.join(__dirname, '..', 'src');

const files = execSync(
    `grep -rl 'className="bg-re-brand text-re-surface-base"' --include="*.tsx" ${SRC}`,
    { encoding: 'utf8' }
).trim().split('\n').filter(Boolean);

let totalFixes = 0;

for (const file of files) {
    const lines = fs.readFileSync(file, 'utf8').split('\n');
    let fixes = 0;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (line === 'className="bg-re-brand text-re-surface-base"') {
            // Search backwards for the opening element's className
            for (let j = i - 1; j >= Math.max(0, i - 5); j--) {
                const prevLine = lines[j];
                const match = prevLine.match(/className="([^"]*)"/);
                if (match) {
                    // Merge the classes
                    lines[j] = prevLine.replace(
                        `className="${match[1]}"`,
                        `className="${match[1]} bg-re-brand text-re-surface-base"`
                    );
                    lines.splice(i, 1); // Remove the duplicate line
                    fixes++;
                    break;
                }
            }
        }
    }

    if (fixes > 0) {
        fs.writeFileSync(file, lines.join('\n'));
        console.log(`${path.relative(SRC, file)}: ${fixes} merged`);
        totalFixes += fixes;
    }
}

console.log(`\nTotal fixes: ${totalFixes}`);
