#!/usr/bin/env node
// RegEngine copy rule check. Node only, no dependencies.
// Usage: node check-copy.mjs [repoRoot] [--rules copy-rules.json] [--allow allowlist.json] [--baseline baseline.json] [--base-baseline main-baseline.json] [--json] [--github] [--strict] [--gate] [--update-baseline]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
function walk(dir, out, cfg) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (cfg.skip.some(s => p.includes(s))) continue;
    if (e.isDirectory()) walk(p, out, cfg);
    else if (cfg.extensions.includes(path.extname(e.name))) out.push(p);
  }
  return out;
}

// Lexer: returns copy segments {text, line, col, kind} with comments removed.
// kind: 'str' (quote or template literal text), 'jsx' (JSX text), 'md' (markdown line)
export function segmentsTs(src, isTsx) {
  const segs = []; let i = 0, line = 1, col = 1; const n = src.length;
  const adv = () => { if (src[i] === '\n') { line++; col = 1; } else col++; i++; };
  const tplStack = []; // brace depth inside ${ }
  let braceDepth = 0;
  let code = ''; let codeLine = 1, codeCol = 1; // JSX text candidate buffer
  const flushJsx = () => {
    if (isTsx && code) {
      // JSX text: content after '>' up to '<' or '{', only when it reads like prose
      const m = code.match(/>([^<>{}]*)$/s);
      if (m && /[A-Za-z\u2013\u2014]/.test(m[1]) && !/[;=]|&&|\|\||=>|\)\s*$|^[\s)]*[:?]/.test(m[1])) {
        const before = code.slice(0, code.length - m[1].length);
        let l = codeLine, c = codeCol; for (const ch of before) { if (ch === '\n') { l++; c = 1; } else c++; }
        const lead = m[1].match(/^\s*/)[0]; for (const ch of lead) { if (ch === '\n') { l++; c = 1; } else c++; }
        if (m[1].trim()) segs.push({ text: m[1].trim(), line: l, col: c, kind: 'jsx' });
      }
    }
    code = ''; codeLine = line; codeCol = col;
  };
  while (i < n) {
    const ch = src[i], nx = src[i + 1];
    if (ch === '/' && nx === '/') { flushJsx(); while (i < n && src[i] !== '\n') adv(); continue; }
    if (ch === '/' && nx === '*') { flushJsx(); adv(); adv(); while (i < n && !(src[i] === '*' && src[i + 1] === '/')) adv(); adv(); adv(); continue; }
    if (isTsx && ch === '{' && nx === '/' && src[i + 2] === '*') { flushJsx(); while (i < n && !(src[i] === '*' && src[i + 1] === '/')) adv(); adv(); adv(); while (i < n && /\s/.test(src[i])) adv(); if (src[i] === '}') adv(); continue; }
    if (ch === '"' || ch === "'" || ch === '`' || (ch === '}' && tplStack.length && tplStack[tplStack.length - 1] === braceDepth)) {
      // in JSX text an apostrophe is prose, not a string start
      if (isTsx && ch === "'" && /[A-Za-z]$/.test(code) && />[^<>{}]*$/s.test(code)) { code += ch; adv(); continue; }
      flushJsx();
      let q = ch; if (ch === '}') { tplStack.pop(); q = '`'; }
      adv(); const sl = line, sc = col; let buf = '';
      while (i < n) {
        if (src[i] === '\\') { buf += src[i + 1] || ''; adv(); adv(); continue; }
        if (q === '`' && src[i] === '$' && src[i + 1] === '{') { adv(); adv(); tplStack.push(braceDepth); break; }
        if (src[i] === q) { adv(); break; }
        if (q !== '`' && src[i] === '\n') break;
        buf += src[i]; adv();
      }
      if (buf) segs.push({ text: buf, line: sl, col: sc, kind: 'str' });
      codeLine = line; codeCol = col; continue;
    }
    if (ch === '{') { flushJsx(); braceDepth++; adv(); codeLine = line; codeCol = col; continue; }
    if (ch === '}') { flushJsx(); braceDepth--; adv(); codeLine = line; codeCol = col; continue; }
    if (ch === '<') { flushJsx(); }
    if (!code) { codeLine = line; codeCol = col; }
    code += ch; adv();
  }
  flushJsx();
  return segs;
}

export function segmentsMd(src) {
  const segs = []; let fence = false, htmlc = false;
  src.split('\n').forEach((t, k) => {
    if (/^\s*(```|~~~)/.test(t)) { fence = !fence; return; }
    if (fence) return;
    if (t.includes('<!--')) htmlc = true;
    if (htmlc) { if (t.includes('-->')) htmlc = false; return; }
    if (/^\s*(import|export)\s/.test(t)) return;
    let s = t.replace(/`[^`]*`/g, ''); // inline code
    if (/^\s*---\s*$/.test(s) || /^\s*\|?[\s:|-]+\|?\s*$/.test(s)) return; // rules, table separators
    s = s.replace(/^\s*[-*]\s/, '  '); // list bullets
    if (s.trim()) segs.push({ text: s, line: k + 1, col: 1, kind: 'md' });
  });
  return segs;
}

const looksLikeCode = s => /calc\(|var\(--|^[\w\-:/\[\].%#@]+(\s+[\w\-:/\[\].%#@!]+)*$/.test(s) && !/\s[a-z]+\s[a-z]+\s/i.test(s) && !/[\u2013\u2014]/.test(s);
const escapeRegex = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const word = s => new RegExp(`(?<![A-Za-z0-9_/-])${escapeRegex(s)}(?![A-Za-z0-9_/-])`, 'i');

export function parseCapabilities(src) {
  const groups = {};
  const seen = new Set();
  for (const name of ['live', 'preview', 'planned', 'off']) {
    const match = src.match(new RegExp(`\\b${name}\\s*:\\s*\\[([^\\]]*)\\]`));
    // Empty or omitted `off` means nothing is disabled — do not throw.
    if (!match) {
      if (name === 'off') {
        groups[name] = [];
        continue;
      }
      throw new Error(`Missing ${name} capability registry`);
    }
    if (match[1].replace(/'[^']+'/g, '').replace(/,/g, '').trim()) {
      throw new Error(`Unparseable ${name} capability registry`);
    }
    groups[name] = [...match[1].matchAll(/'([^']+)'/g)].map(m => m[1]);
    // `planned` and `off` may be empty; live/preview must list at least one feature.
    if (name !== 'planned' && name !== 'off' && !groups[name].length) {
      throw new Error(`Empty ${name} capability registry`);
    }
    for (const feature of groups[name]) {
      if (seen.has(feature)) throw new Error(`Duplicate capability status for ${feature}`);
      seen.add(feature);
    }
  }
  return groups;
}

function copyText(seg, srcLine) {
  if (/^\s*import\b/.test(srcLine)) return '';
  if (seg.kind === 'str') {
    const prefix = srcLine.slice(0, Math.max(0, seg.col - 2));
    if (/\b(?:className|href|src|path|route|id|key|testId|data-[\w-]+)\s*[:=]\s*$/.test(prefix)) return '';
    if (/\bfrom\s*$/.test(prefix)) return '';
    if (/\b(?:lastRun|nextRun|manifestHash)\s*:\s*$/.test(prefix)) return '';
    if (/\b[A-Z][A-Z0-9_]*\s*=\s*$/.test(prefix) && /^[a-z_]+$/.test(seg.text)) return '';
    if (/^[a-z]+(?:[-_][a-z]+)+$/.test(seg.text)) return '';
  }
  return seg.text.replace(/https?:\/\/\S+|(?<![A-Za-z0-9])\/[A-Za-z0-9_./-]+/g, ' ');
}

export function check(seg, srcLine, cfg, capabilities, copyLine = '') {
  const t = seg.text, hits = [];
  const add = (rule, m) => hits.push({ rule, match: m });
  if (/^\s*(?:[\u2014\u2013]|--)\s*$/.test(t) || (t.length < 4 && /^[\s'"`]*[\u2014\u2013][\s'"`]*$/.test(t)) || (t.trim() === '-' && /(?:\?\?|\|\|)\s*['"]-['"]/.test(srcLine))) add('dash-placeholder', t.trim());
  else {
    if (t.includes('\u2014')) add('em-dash', t);
    if (t.includes('\u2013')) add('en-dash', t);
  }
  if (/[A-Za-z0-9.,)"'%] - [A-Za-z0-9("'$]/.test(t) && !/calc\(/.test(t) && !(seg.kind === 'str' && looksLikeCode(t))) add('hyphen-dash', t);
  if (capabilities.off.some(name => new RegExp(`(^|[^A-Za-z0-9_])${escapeRegex(name)}(?![A-Za-z0-9_])`).test(t)) && !(seg.kind === 'str' && /^[A-Z_]+$/.test(t.trim()) && t.trim().length > 4)) add('edi-sftp', t);
  const previewNames = [...new Set(capabilities.preview.map(name => name.split(/\s+/)[0]))];
  if (previewNames.some(name => new RegExp(`\\b${escapeRegex(name)}\\b`).test(t)) && !/Preview/i.test(t) && !/Preview/i.test(srcLine)) add('epcis-unlabeled', t);
  if ((seg.kind !== 'str' && /\b(NaN|undefined)\b/.test(t)) || (seg.kind === 'str' && /\b(NaN|undefined)\b/.test(t) && /\s/.test(t.trim()) && !/typeof|===|!==/.test(t))) add('nan-undefined', t);
  const low = t.toLowerCase();
  cfg.denylist.forEach(d => { if (low.includes(d.toLowerCase())) add('invented-entity', d); });
  const copy = copyText(seg, srcLine);
  if (copy) {
    const nonLive = [...capabilities.preview, ...capabilities.planned, ...capabilities.off];
    const capability = nonLive.find(name => word(name).test(copy) || (name.startsWith('EPCIS ') && word('EPCIS').test(copy)));
    if (capability && (/\b(?:Live|Implemented|GA|Available)\b/.test(copyLine || copy) || (/\bstatus\s*:\s*['"]available['"]/.test(srcLine) && /\bavailable\b/.test(copyLine || copy)))) add('live-claim', capability);
    if (copy.trim() === 'Pilot' && /\b(?:badge|status)\b/i.test(srcLine)) add('pilot-status', copy);
    if (/(?:^|[^A-Za-z0-9_/-])(?:sample|demo|simulated|synthetic)(?![A-Za-z0-9_/-])/i.test(copy)) add('sample-demo', copy);
    if (word('sandbox').test(copy)) add('sandbox', copy);
  }
  return hits;
}

function emptyRenderSegments(src) {
  const clean = src.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, m => m.replace(/[^\n]/g, ' '));
  const segs = [];
  const re = /\{[^{}]*?(?:\?\?|\|\|)\s*(?:''|""|``)[^{}]*?\}/g;
  for (const m of clean.matchAll(re)) {
    const prefix = clean.slice(Math.max(0, m.index - 200), m.index);
    if (!/(?:<[^>]*|>[^<]*)$/.test(prefix)) continue;
    if (/=>|;/.test(m[0])) continue;
    const before = clean.slice(0, m.index);
    const line = before.split('\n').length;
    const col = m.index - before.lastIndexOf('\n');
    segs.push({ text: m[0].replace(/\s+/g, ' ').slice(0, 120), line, col, kind: 'jsx-empty' });
  }
  return segs;
}

export function scanSource(src, rel, cfg, capabilities, allow = []) {
  if (cfg.skip.some(part => rel.includes(part))) return [];
  const lines = src.split('\n');
  const ext = path.extname(rel);
  const segs = ext === '.md' || ext === '.mdx' ? segmentsMd(src) : segmentsTs(src, ext === '.tsx');
  const copyLines = new Map();
  for (const s of segs) {
    const copy = copyText(s, lines[s.line - 1] || '');
    if (copy) copyLines.set(s.line, `${copyLines.get(s.line) || ''} ${copy}`);
  }
  if (ext === '.tsx') segs.push(...emptyRenderSegments(src));
  const findings = []; const seen = new Set();
  for (const s of segs) {
    const hits = s.kind === 'jsx-empty' ? [{ rule: 'empty-render' }] : check(s, lines[s.line - 1] || '', cfg, capabilities, copyLines.get(s.line));
    for (const h of hits) {
      const allowed = allow.find(a => rel.endsWith(a.file) && a.rule === h.rule && (!a.line || a.line === s.line) && (!a.match || s.text.includes(a.match)));
      if (allowed) continue;
      const key = `${rel}:${s.line}:${s.col}:${h.rule}`; if (seen.has(key)) continue; seen.add(key);
      findings.push({ file: rel, line: s.line, col: s.col, rule: h.rule, text: s.text.replace(/\s+/g, ' ').slice(0, 120) });
    }
  }
  return findings;
}

export function summarize(findings, filesScanned, cfg) {
  const byRule = Object.fromEntries(Object.keys(cfg.rules).map(rule => [rule, 0]));
  findings.forEach(x => { byRule[x.rule]++; });
  return { total: findings.length, filesWithFindings: new Set(findings.map(x => x.file)).size, filesScanned, byRule };
}

export function countsByFileRule(findings) {
  const counts = {};
  for (const { file, rule } of findings) {
    counts[file] ??= {};
    counts[file][rule] = (counts[file][rule] || 0) + 1;
  }
  return Object.fromEntries(Object.keys(counts).sort().map(file => [
    file, Object.fromEntries(Object.keys(counts[file]).sort().map(rule => [rule, counts[file][rule]])),
  ]));
}

export function compareBaseline(current, baseline) {
  const regressions = [];
  const reductions = [];
  for (const file of [...new Set([...Object.keys(current), ...Object.keys(baseline)])].sort()) {
    const actualRules = current[file] || {};
    const baselineRules = baseline[file] || {};
    for (const rule of [...new Set([...Object.keys(actualRules), ...Object.keys(baselineRules)])].sort()) {
      const actual = actualRules[rule] || 0;
      const previous = baselineRules[rule] || 0;
      if (actual > previous) regressions.push({ file, rule, baseline: previous, current: actual });
      if (actual < previous) reductions.push({ file, rule, baseline: previous, current: actual });
    }
  }
  return { regressions, reductions };
}

function flatCounts(counts) {
  return Object.fromEntries(Object.entries(counts).flatMap(([file, rules]) =>
    Object.entries(rules).map(([rule, count]) => [`${file}|${rule}`, count])));
}

export function gateCompare(base, pr, actual) {
  const errors = [];
  for (const key of [...new Set([...Object.keys(base), ...Object.keys(pr), ...Object.keys(actual)])].sort()) {
    const [file, rule] = key.split('|');
    const mainCount = base[key] ?? 0;
    const prCount = pr[key] ?? 0;
    const actualCount = actual[key] ?? 0;
    const counts = `main=${mainCount}, PR baseline=${prCount}, actual=${actualCount}`;
    if (actualCount > mainCount) errors.push(`file=${file}, rule=${rule}: count went up vs main (${counts})`);
    if (prCount > mainCount) errors.push(`file=${file}, rule=${rule}: PR baseline loosened vs main (${counts})`);
    if (prCount !== actualCount) errors.push(`file=${file}, rule=${rule}: baseline.json is stale, run --update-baseline (${counts})`);
  }
  return { ok: errors.length === 0, errors };
}

const annotationEscape = s => String(s).replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A');
const propertyEscape = s => annotationEscape(s).replace(/:/g, '%3A').replace(/,/g, '%2C');

function main(args) {
  const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
  const pos = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && ['--rules', '--allow', '--baseline', '--base-baseline'].includes(args[i - 1])));
  const repo = path.resolve(pos[0] || '.');
  const cfg = JSON.parse(fs.readFileSync(opt('--rules', path.join(here, 'copy-rules.json')), 'utf8'));
  const allowPath = opt('--allow', path.join(here, 'allowlist.json'));
  const allow = fs.existsSync(allowPath) ? JSON.parse(fs.readFileSync(allowPath, 'utf8')).entries || [] : [];
  const targetRegistry = path.join(repo, 'frontend/src/lib/capabilities.ts');
  const registry = fs.existsSync(targetRegistry) ? targetRegistry : path.resolve(here, '../../frontend/src/lib/capabilities.ts');
  const capabilities = parseCapabilities(fs.readFileSync(registry, 'utf8'));
  const files = cfg.roots.flatMap(r => walk(path.join(repo, r), [], cfg));
  const findings = files.flatMap(f => scanSource(fs.readFileSync(f, 'utf8'), path.relative(repo, f), cfg, capabilities, allow));
  const summary = summarize(findings, files.length, cfg);
  const baselinePath = path.resolve(repo, opt('--baseline', 'scripts/copy-lint/baseline.json'));
  const current = countsByFileRule(findings);
  if (args.includes('--update-baseline')) {
    fs.writeFileSync(baselinePath, `${JSON.stringify(current, null, 2)}\n`);
    console.log(`Updated copy baseline: ${baselinePath}`);
  }
  if (args.includes('--json')) console.log(JSON.stringify({ summary, findings }, null, 1));
  else {
    for (const x of findings) {
      console.log(`${x.file}:${x.line}:${x.col}  ${x.rule}  ${x.text}`);
      if (args.includes('--github') || process.env.GITHUB_ACTIONS === 'true') {
        console.log(`::warning file=${propertyEscape(x.file)},line=${x.line},col=${x.col},title=copy-lint/${x.rule}::${annotationEscape(cfg.rules[x.rule].message)}`);
      }
    }
    console.log(`\n${summary.total} copy rule violations in ${summary.filesWithFindings} files (${summary.filesScanned} scanned)`);
    for (const [rule, count] of Object.entries(summary.byRule)) console.log(`  ${rule}: ${count}  ${cfg.rules[rule].message}`);
  }
  if (args.includes('--gate')) {
    const pr = JSON.parse(fs.readFileSync(baselinePath, 'utf8'));
    const basePath = opt('--base-baseline');
    const resolvedBasePath = basePath && path.resolve(repo, basePath);
    const baseText = resolvedBasePath && fs.existsSync(resolvedBasePath) ? fs.readFileSync(resolvedBasePath, 'utf8') : '';
    if (!baseText.trim()) console.log('Main has no baseline yet (bootstrap); using the PR baseline as main.');
    const base = baseText.trim() ? JSON.parse(baseText) : pr;
    const result = gateCompare(flatCounts(base), flatCounts(pr), flatCounts(current));
    for (const error of result.errors) console.log(`Copy gate: ${error}`);
    if (!result.ok) process.exitCode = 1;
  }
  if (summary.total && (args.includes('--strict') || process.env.COPY_LINT_STRICT === '1')) process.exitCode = 1;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main(process.argv.slice(2));
