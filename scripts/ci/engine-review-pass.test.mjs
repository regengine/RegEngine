// Run: node --test scripts/ci/engine-review-pass.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

// Execute the workflow's actual script so the gate stays inline and tests cannot
// drift onto a separate implementation. No GitHub calls leave this harness.
const workflow = readFileSync(new URL('../../.github/workflows/pr-guards.yml', import.meta.url), 'utf8');
const job = workflow.split(/^  engine-review-pass:\s*$/m)[1]?.split(/^  [\w-]+:/m)[0];
const script = job?.match(/^          script: \|\n((?: {12}[^\n]*\n|\n)+)/m)?.[1]
  .replace(/^ {12}/gm, '');
assert.ok(script, 'Engine Review Pass inline script must be present');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const runGate = new AsyncFunction('github', 'context', 'core', script);

const HEAD = 'abcdef01'.repeat(5);
const LATER = '2026-11-18T13:00:00Z';
const NO_PASS = 'Engine Review Pass failed: No passing review from a non-author engine for current head SHA. A marker counts only in a pull request review, not in a comment.';
const INVALID_AUTHOR = 'Invalid author engine. Please use an engine branch prefix such as gemini/ or claude/.';

function review(engine = 'deepseek', overrides = {}) {
  return {
    id: 1,
    state: 'APPROVED',
    submitted_at: '2026-11-18T12:00:00Z',
    author_association: 'OWNER',
    user: { login: 'trusted-reviewer' },
    body: `REVIEW: PASS ${engine} ${HEAD}`,
    ...overrides,
  };
}

async function evaluate({ branch = 'cursor/fix', reviews = [], comments = [] } = {}) {
  const statuses = [];
  const failures = [];
  const calls = [];
  const warnings = [];
  const errors = [];
  const pr = { number: 1, head: { ref: branch, sha: HEAD } };
  const context = {
    repo: { owner: 'example', repo: 'example' },
    payload: { pull_request: pr },
    runId: 1,
    workflow: 'PR Guards',
  };
  const github = {
    rest: {
      repos: { createCommitStatus: async (status) => statuses.push(status) },
      pulls: {
        get: async () => ({ data: pr }),
        listReviews: 'reviews',
        listReviewComments: 'reviewComments',
      },
      issues: { listComments: 'issueComments' },
      actions: { listWorkflowRunsForRepo: 'runs' },
    },
    paginate: async (endpoint) => {
      calls.push(endpoint);
      if (endpoint === 'reviews') return reviews;
      if (endpoint === 'issueComments' || endpoint === 'reviewComments') return comments;
      assert.equal(endpoint, 'runs', 'Unexpected GitHub endpoint');
      return [];
    },
  };
  const core = {
    info: () => {},
    warning: (message) => warnings.push(message),
    error: (message) => errors.push(message),
    setFailed: (message) => failures.push(message),
  };
  await runGate(github, context, core);
  assert.deepEqual(errors, [], 'The script must reach a gate verdict, not throw');
  assert.deepEqual(warnings, [], 'All expected GitHub calls must be mocked');
  assert.equal(statuses.length, 1);
  assert.equal(statuses[0].sha, HEAD);
  assert.equal(statuses[0].context, 'Engine Review Pass');
  return { status: statuses[0], failures, calls };
}

function expectVerdict(result, failure = null) {
  assert.equal(result.status.state, failure ? 'failure' : 'success');
  assert.deepEqual(result.failures, failure ? [failure] : []);
}

const engines = [
  'claude', 'codex', 'cursor', 'gemini', 'grok', 'muse', 'kimi', 'pi',
  'deepseek', 'hermes', 'antigravity', 'visual-designer', 'product-designer',
];

test('ALLOWED_ENGINES is exactly the 13 supported engines (no additions or removals)', () => {
  const declaration = script.match(/\bconst ALLOWED_ENGINES = (new Set\(\[[\s\S]*?\]\));/);
  assert.ok(declaration, 'The inline script must declare ALLOWED_ENGINES');
  const actualEngines = new Function(`return ${declaration[1]};`)();
  assert.deepEqual(actualEngines, new Set(engines));
});

for (const engine of engines) {
  test(`${engine}/ accepts a current-head PASS from another allowed engine`, async () => {
    const reviewer = engine === 'deepseek' ? 'codex' : 'deepseek';
    expectVerdict(await evaluate({ branch: `${engine}/fix`, reviews: [review(reviewer)] }));
  });

  test(`${engine}/ rejects its own engine's PASS`, async () => {
    expectVerdict(await evaluate({ branch: `${engine}/fix`, reviews: [review(engine)] }), NO_PASS);
  });
}

for (const association of ['OWNER', 'MEMBER', 'COLLABORATOR']) {
  test(`cursor/ accepts a non-author PASS from ${association}`, async () => {
    expectVerdict(await evaluate({ reviews: [review('kimi', { author_association: association })] }));
  });
}

test('branch and reviewer engines are case-insensitive', async () => {
  expectVerdict(await evaluate({ branch: 'CuRsOr/fix', reviews: [review('CoDeX')] }));
  expectVerdict(await evaluate({ branch: 'CuRsOr/fix', reviews: [review('CURSOR')] }), NO_PASS);
});

test('SHA hex remains case-insensitive for a current-head PASS', async () => {
  expectVerdict(await evaluate({
    reviews: [review('deepseek', { body: `REVIEW: PASS deepseek ${HEAD.toUpperCase()}` })],
  }));
});

test('cursor is also an allowed non-author reviewer', async () => {
  expectVerdict(await evaluate({ branch: 'codex/fix', reviews: [review('cursor')] }));
});

for (const branch of ['unknown/fix', 'cursor', '/cursor', '']) {
  test(`invalid author branch ${JSON.stringify(branch)} fails before reading reviews`, async () => {
    const result = await evaluate({ branch, reviews: [review()] });
    expectVerdict(result, INVALID_AUTHOR);
    assert.deepEqual(result.calls, []);
  });
}

for (const sha of ['0'.repeat(40), HEAD.slice(0, 39), `${HEAD}0`, `g${HEAD.slice(1)}`]) {
  test(`cursor/ rejects stale or malformed SHA ${sha}`, async () => {
    expectVerdict(await evaluate({ reviews: [review('deepseek', { body: `REVIEW: PASS deepseek ${sha}` })] }), NO_PASS);
  });
}

test('cursor/ rejects a 7-character current-head SHA prefix (no prefix matching)', async () => {
  expectVerdict(await evaluate({
    reviews: [review('deepseek', { body: `REVIEW: PASS deepseek ${HEAD.slice(0, 7)}` })],
  }), NO_PASS);
});

for (const action of ['FAIL', 'BLOCKED']) {
  const blocked = 'Engine Review Pass blocked: Blocked by deepseek';

  test(`a current-head ${action} from a non-author engine blocks without a PASS`, async () => {
    expectVerdict(await evaluate({
      reviews: [review('deepseek', { body: `REVIEW: ${action} deepseek ${HEAD}` })],
    }), blocked);
  });

  test(`a current-head ${action} still blocks with another non-author engine's PASS`, async () => {
    expectVerdict(await evaluate({
      reviews: [
        review('deepseek', { body: `REVIEW: ${action} deepseek ${HEAD}` }),
        review('kimi', { id: 2, submitted_at: LATER }),
      ],
    }), blocked);
  });

  test(`a later PASS from the same engine replaces its earlier ${action}`, async () => {
    expectVerdict(await evaluate({
      reviews: [
        review('deepseek', { id: 2, submitted_at: LATER }),
        review('deepseek', { body: `REVIEW: ${action} deepseek ${HEAD}` }),
      ],
    }));
  });
}

for (const association of ['OWNER', 'MEMBER', 'COLLABORATOR']) {
  test(`latest CHANGES_REQUESTED from ${association} blocks even with a PASS in its body`, async () => {
    expectVerdict(await evaluate({
      reviews: [review('deepseek', { state: 'CHANGES_REQUESTED', author_association: association })],
    }), 'Engine Review Pass blocked: Changes requested by trusted-reviewer');
  });
}

test('empty-body CHANGES_REQUESTED blocks a separate PASS (decisions use raw reviews)', async () => {
  expectVerdict(await evaluate({
    reviews: [
      review('deepseek', { state: 'CHANGES_REQUESTED', body: '' }),
      review('kimi', { id: 2, user: { login: 'another-reviewer' }, submitted_at: LATER }),
    ],
  }), 'Engine Review Pass blocked: Changes requested by trusted-reviewer');
});

for (const association of ['CONTRIBUTOR', 'NONE', '']) {
  test(`CHANGES_REQUESTED from untrusted association ${JSON.stringify(association)} does not block a PASS`, async () => {
    expectVerdict(await evaluate({
      reviews: [
        review('deepseek', { state: 'CHANGES_REQUESTED', body: '', author_association: association }),
        review('kimi', { id: 2, user: { login: 'another-reviewer' }, submitted_at: LATER }),
      ],
    }));
  });
}

test('a later APPROVED from the same user clears CHANGES_REQUESTED', async () => {
  expectVerdict(await evaluate({
    reviews: [
      review('deepseek', { id: 2, state: 'APPROVED', submitted_at: LATER }),
      review('deepseek', { state: 'CHANGES_REQUESTED', body: '' }),
    ],
  }));
});

test('a later COMMENTED PASS from the same user does not clear CHANGES_REQUESTED', async () => {
  expectVerdict(await evaluate({
    reviews: [
      review('deepseek', { id: 2, state: 'COMMENTED', submitted_at: LATER }),
      review('deepseek', { state: 'CHANGES_REQUESTED', body: '' }),
    ],
  }), 'Engine Review Pass blocked: Changes requested by trusted-reviewer');
});

for (const [placement, body] of [
  ['leading text', `Please see REVIEW: PASS deepseek ${HEAD}`],
  ['trailing text', `REVIEW: PASS deepseek ${HEAD} for details`],
  ['leading and trailing text', `Please see REVIEW: PASS deepseek ${HEAD} for details`],
]) {
  test(`a mid-line PASS with ${placement} does not count (marker must occupy its own line)`, async () => {
    expectVerdict(await evaluate({ reviews: [review('deepseek', { body })] }), NO_PASS);
  });
}

test('an own-line PASS surrounded by prose counts after CRLF normalization', async () => {
  expectVerdict(await evaluate({
    reviews: [review('deepseek', { body: `Review complete.\r\nREVIEW: PASS deepseek ${HEAD}\r\nDetails follow.` })],
  }));
});

// REVIEW: and PASS/BLOCKED/FAIL deliberately require uppercase; engine names
// and SHA hex remain case-insensitive. Do not add an i flag to the marker regex.
for (const keyword of ['review: pass', 'REVIEW: pass', 'Review: PASS']) {
  test(`case-sensitive marker keyword rejects ${JSON.stringify(keyword)}`, async () => {
    expectVerdict(await evaluate({
      reviews: [review('deepseek', { body: `${keyword} deepseek ${HEAD}` })],
    }), NO_PASS);
  });
}

test('a COMMENTED review accepts a valid non-author current-head PASS', async () => {
  expectVerdict(await evaluate({ reviews: [review('deepseek', { state: 'COMMENTED' })] }));
});

test('a COMMENTED review without a marker does not supply a PASS', async () => {
  expectVerdict(await evaluate({
    reviews: [review('deepseek', { state: 'COMMENTED', body: 'Reviewed the changes.' })],
  }), NO_PASS);
});

for (const association of ['CONTRIBUTOR', 'NONE', '']) {
  test(`cursor/ rejects a PASS from untrusted association ${JSON.stringify(association)}`, async () => {
    expectVerdict(await evaluate({ reviews: [review('deepseek', { author_association: association })] }), NO_PASS);
  });
}

test('unknown reviewer engine cannot supply a PASS', async () => {
  expectVerdict(await evaluate({ reviews: [review('unknown')] }), NO_PASS);
});

test('dismissed and unsubmitted reviews cannot supply a PASS', async () => {
  expectVerdict(await evaluate({ reviews: [review('deepseek', { state: 'DISMISSED' })] }), NO_PASS);
  expectVerdict(await evaluate({ reviews: [review('deepseek', { submitted_at: null })] }), NO_PASS);
});

test('PASS markers in comments are not read or counted', async () => {
  const result = await evaluate({ comments: [review()] });
  expectVerdict(result, NO_PASS);
  assert.deepEqual(result.calls, ['reviews']);
});
