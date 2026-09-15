#!/usr/bin/env node
/**
 * design-lint — the gate that keeps the design system honest.
 *
 * The previous stylesheet kept 163 pages visually consistent by brute force:
 * blanket `!important` rules that rewrote raw Tailwind palette classes,
 * flattened every radius and suppressed every shadow. Those rules are being
 * removed (see SPEC.md §7.1), so consistency now has to come from what pages
 * are allowed to write. This script is that rule.
 *
 * Usage:
 *   node scripts/design-lint.mjs            # lint the whole app
 *   node scripts/design-lint.mjs src/app/dashboard   # lint a subtree
 *   node scripts/design-lint.mjs --report   # group by rule, list every hit
 *
 * Exit code 1 on any violation.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

const ROOT = process.cwd();
const REPORT = process.argv.includes('--report');
const targets = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const SCAN = targets.length ? targets : ['src'];

/** The Inflow Lab embed is a separate product skin with its own palette. */
const EXEMPT_PATH = /inflow/i;

/**
 * Social-card renderers are exempt from the inline-style rule.
 *
 * `next/og` rasterises JSX through Satori, which supports inline styles only —
 * it never sees a stylesheet, so a Tailwind class on an OG card renders as
 * nothing. Flagging these files would push an author to "fix" them into blank
 * images.
 */
const isSatori = (src) => /from ['"]next\/og['"]/.test(src);

/** Primitives own the raw recipes; pages may not write them. */
const isPrimitive = (p) =>
  p.includes(`components${sep}ui${sep}`) || p.includes(`components${sep}layout${sep}`);

const PALETTE = 'slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose';

const RULES = [
  {
    id: 'raw-palette',
    // e.g. text-slate-500, bg-emerald-50, border-gray-200/40, hover:bg-red-100
    re: new RegExp(`(?:^|["'\\s:])(?:hover:|focus:|active:|dark:|group-hover:|sm:|md:|lg:|xl:)*(?:text|bg|border|ring|from|via|to|fill|stroke|decoration|divide|outline|shadow|accent|caret|placeholder)-(?:${PALETTE})-\\d{2,3}(?:/\\d{1,3})?(?=["'\\s]|$)`, 'g'),
    msg: 'raw Tailwind palette class — use a token utility (text-re-text-muted, bg-re-success-bg, border-re-border)',
  },
  {
    id: 'gradient',
    re: /\bbg-gradient-to-[trblxy]{1,2}\b/g,
    msg: 'gradients are not part of the system (SPEC §1.6)',
  },
  {
    id: 'raw-hex',
    re: /(?:className|class)="[^"]*\[#[0-9a-fA-F]{3,8}\]/g,
    msg: 'hard-coded hex in a class — use a token',
  },
  {
    id: 'inline-style-visual',
    re: /style=\{\{[^}]*\b(?:color|background|backgroundColor|boxShadow|borderRadius|fontFamily|fontSize|fontWeight)\s*:/g,
    msg: 'inline style for a visual property — use a token utility',
    skipPrimitives: true,
  },
  {
    id: 'shadow-outside-ui',
    re: /(?:^|["'\s])(?:hover:|dark:|sm:|md:|lg:)*shadow-(?:sm|md|lg|xl|2xl|inner)(?=["'\s]|$)/g,
    msg: 'shadow on page markup — elevation is surface-step + border (SPEC §5.1)',
    skipPrimitives: true,
  },
  {
    id: 'ad-hoc-container',
    re: /\bmax-w-(?:5xl|6xl|7xl)\b/g,
    msg: 'ad-hoc container width — use <Container width="…">',
    skipPrimitives: true,
  },
  {
    id: 'sub-11px-type',
    re: /\btext-\[(?:9|10)px\]/g,
    msg: 'type below 11px — the smallest step is text-label (0.6875rem)',
  },
  {
    id: 'press-scale',
    re: /\bactive:scale-\[?0?\.9\d+\]?/g,
    msg: 'press-scale transform removed (SPEC §5.2) — press feedback is the active: background step',
  },
];

function walk(dir, out = []) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    if (entry === 'node_modules' || entry === '.next' || entry === 'dist') continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, out);
    else if (/\.(tsx|ts|css)$/.test(entry) && !/\.(test|spec)\.tsx?$/.test(entry)) out.push(full);
  }
  return out;
}

const files = SCAN.flatMap((t) => {
  const full = join(ROOT, t);
  try {
    return statSync(full).isDirectory() ? walk(full) : [full];
  } catch {
    return [];
  }
});

const violations = [];
for (const file of files) {
  const rel = relative(ROOT, file);
  if (EXEMPT_PATH.test(rel)) continue;
  // globals.css keeps documented verbatim blocks; it is checked separately.
  if (rel.endsWith('globals.css')) continue;

  const src = readFileSync(file, 'utf8');
  const satori = isSatori(src);
  const lines = src.split('\n');
  for (const rule of RULES) {
    if (rule.skipPrimitives && isPrimitive(rel)) continue;
    if (satori && rule.id === 'inline-style-visual') continue;
    lines.forEach((line, i) => {
      if (line.includes('design-lint-disable')) return;
      const matches = line.match(rule.re);
      if (matches) {
        for (const m of matches) {
          violations.push({ rule: rule.id, msg: rule.msg, file: rel, line: i + 1, text: m.trim() });
        }
      }
    });
  }
}

if (violations.length === 0) {
  console.log(`design-lint: clean (${files.length} files)`);
  process.exit(0);
}

if (REPORT) {
  const byRule = new Map();
  for (const v of violations) {
    if (!byRule.has(v.rule)) byRule.set(v.rule, []);
    byRule.get(v.rule).push(v);
  }
  for (const [rule, hits] of [...byRule].sort((a, b) => b[1].length - a[1].length)) {
    console.log(`\n${rule} — ${hits.length} hit(s): ${hits[0].msg}`);
    const byFile = new Map();
    for (const h of hits) byFile.set(h.file, (byFile.get(h.file) ?? 0) + 1);
    for (const [f, n] of [...byFile].sort((a, b) => b[1] - a[1])) {
      console.log(`  ${String(n).padStart(4)}  ${f}`);
    }
  }
  const byFileAll = new Map();
  for (const v of violations) byFileAll.set(v.file, (byFileAll.get(v.file) ?? 0) + 1);
  console.log(`\nTotal: ${violations.length} violation(s) in ${byFileAll.size} file(s).`);
} else {
  for (const v of violations.slice(0, 200)) {
    console.log(`${v.file}:${v.line}  [${v.rule}]  ${v.text}\n    ${v.msg}`);
  }
  if (violations.length > 200) console.log(`… and ${violations.length - 200} more. Run with --report for a summary.`);
  console.log(`\ndesign-lint: ${violations.length} violation(s).`);
}
process.exit(1);
