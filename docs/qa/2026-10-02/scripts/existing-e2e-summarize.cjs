// Produce per-engine counts without treating skipped or blocked tests as passes.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../../..');
const artifacts = path.join(root, 'docs/qa/2026-10-02/artifacts/browser');
const input = process.argv[2] || 'existing-e2e-proxy-local-browser.json';
const report = JSON.parse(fs.readFileSync(path.join(artifacts, input), 'utf8'));
const rows = [];
function visit(suite) {
  for (const spec of suite.specs || []) for (const test of spec.tests) {
    const result = test.results.at(-1);
    const messages = (result.errors || []).map(error => error.message || '').join('\n');
    let classification = result.status;
    if (test.status === 'unexpected') {
      if (messages.includes('QA environment restriction')) classification = 'environment: prohibited database/OTP setup';
      else if (messages.includes('ECONNREFUSED')) classification = 'environment: unavailable local service or wrong local port';
      else if (messages.includes('Cannot fulfill with redirect status')) classification = 'harness: WebKit redirect interception (corrected in final run)';
      else if (spec.title === 'sample FTL CSV evaluates and renders a diagnosis') classification = 'environment: local evaluator backend unavailable';
      else if (spec.title === 'Error pages do not expose sensitive information') classification = 'harness: config matches configured inside Next script text';
      else if (spec.title === 'Unauthenticated users are redirected to login') classification = 'harness: stale Password button expectation on OTP login';
      else if (spec.title === 'challenge network failure keeps the form filled and shows a clear error') classification = 'harness: browser-specific network error wording';
      else if (spec.title === 'login form has proper accessibility and autofill-friendly controls' && test.projectName === 'webkit') classification = 'environment: macOS WebKit keyboard focus preference (plain HTML control confirms)';
      else if (spec.file === 'inflow-lab-tour.spec.ts') classification = 'product UX-008: WebKit guided-tour tooltip extends below viewport (settling probe confirmed)';
      else classification = 'untriaged failure';
    }
    rows.push({ project: test.projectName, file: spec.file, line: spec.line, title: spec.title,
      status: result.status, expectedStatus: test.expectedStatus, classification,
      annotations: test.annotations, durationMs: result.duration,
      error: messages.replace(/\u001b\[[0-9;]*m/g, '').split('\n').slice(0, 8).join('\n') });
  }
  for (const child of suite.suites || []) visit(child);
}
visit(report);
const projects = [...new Set(rows.map(row => row.project))].map(project => {
  const tests = rows.filter(row => row.project === project);
  const counts = { discovered: tests.length, passed: 0, failed: 0, skipped: 0, timedOut: 0, interrupted: 0 };
  const failureClasses = {};
  const skipReasons = {};
  for (const test of tests) {
    if (test.status === 'passed' || test.status === 'skipped') counts[test.status] += 1;
    else {
      counts.failed += 1;
      if (test.status === 'timedOut' || test.status === 'interrupted') counts[test.status] += 1;
      failureClasses[test.classification] = (failureClasses[test.classification] || 0) + 1;
    }
    if (test.status === 'skipped') {
      const reason = (test.annotations || []).filter(annotation => annotation.type === 'skip').map(annotation => annotation.description).join(' | ') || 'unannotated skip';
      skipReasons[reason] = (skipReasons[reason] || 0) + 1;
    }
  }
  return { project, ...counts, failureClasses, skipReasons };
});
const summary = { input, capturedAt: new Date().toISOString(), localFrontend: input.includes('-proxy-') ? 'http://127.0.0.1:3115' : 'http://127.0.0.1:3114',
  noAuthenticatedBackend: true, projects, tests: rows };
const output = input.replace(/\.json$/, '-summary.json');
fs.writeFileSync(path.join(artifacts, output), JSON.stringify(summary, null, 2) + '\n');
console.log(JSON.stringify({ output, projects }, null, 2));
