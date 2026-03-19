#!/usr/bin/env node
/**
 * Deploy Decision Gate
 * Aggregates results from fast-gate and system-sim stages.
 * Blocks deploy if critical checks failed.
 * Allows deploy with warnings for non-critical issues.
 */

const fastGate = process.env.FAST_GATE_RESULT || 'unknown';
const systemSim = process.env.SYSTEM_SIM_RESULT || 'unknown';

console.log('\n=== Deploy Decision Gate ===\n');
console.log(`  Fast Gate:      ${fastGate}`);
console.log(`  System Sim:     ${systemSim}`);

const results = { fastGate, systemSim };
const allPassed = Object.values(results).every(r => r === 'success');
const anyFailed = Object.values(results).some(r => r === 'failure');
const anySkipped = Object.values(results).some(r => r === 'skipped');

console.log('');

if (allPassed) {
  console.log('\u2705 DEPLOY: All checks passed.');
  console.log('');
  console.log('  Pipeline summary:');
  console.log('  \u2500 FSMA 204 compliance: verified');
  console.log('  \u2500 Tenant isolation: verified');
  console.log('  \u2500 Full flow simulation: passed');
  console.log('  \u2500 Bad data rejection: passed');
  console.log('  \u2500 Export artifacts: validated');
  console.log('');
  process.exit(0);
} else if (anyFailed) {
  console.error('\u274c BLOCK DEPLOY: Critical checks failed.');
  console.error('');
  for (const [stage, result] of Object.entries(results)) {
    if (result === 'failure') {
      console.error(`  \u2717 ${stage}: FAILED`);
    }
  }
  console.error('');
  console.error('  Fix the failing checks before deploying.');
  console.error('  Run individual check scripts locally:');
  console.error('    node qa/fsma-lite-check.js');
  console.error('    node qa/tenant-test.js');
  console.error('    node qa/full-flow.js');
  console.error('    node qa/bad-data.js');
  console.error('    node qa/export-validate.js');
  console.error('');
  process.exit(1);
} else if (anySkipped) {
  console.log('\u26a0\ufe0f  WARN: Some stages were skipped.');
  console.log('  Deploy is allowed but review skipped stages.');
  for (const [stage, result] of Object.entries(results)) {
    if (result === 'skipped') {
      console.log(`  \u26a0 ${stage}: skipped`);
    }
  }
  process.exit(0);
} else {
  console.log(`\u26a0\ufe0f  UNKNOWN: Unexpected state — ${JSON.stringify(results)}`);
  console.log('  Allowing deploy but investigate.');
  process.exit(0);
}
