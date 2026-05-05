const baseUrl = process.env.PUBLIC_SSR_BASE_URL ?? 'http://localhost:3011';

const checks = [
  {
    path: '/retailer-readiness',
    mustInclude: ['Retailer Supplier FSMA 204 Compliance', 'Retailer-Ready in 48 Hours'],
    mustNotInclude: ['Checking tool access'],
  },
  {
    path: '/tools/ftl-checker',
    mustInclude: ['FTL Checker', 'Food Traceability List'],
    mustNotInclude: ['Checking tool access'],
  },
  {
    path: '/tools/kde-checker',
    mustInclude: ['KDE Checker', 'Key Data Element'],
    mustNotInclude: ['Checking tool access'],
  },
  {
    path: '/docs/api',
    mustInclude: [
      '<title>API Reference | RegEngine</title>',
      'RegEngine API reference for FSMA 204 traceability records',
    ],
  },
  {
    path: '/docs/changelog',
    mustInclude: [
      '<title>Changelog | RegEngine</title>',
      'Latest RegEngine product updates',
    ],
  },
  {
    path: '/login',
    mustInclude: ['Return to RegEngine.co'],
    mustNotInclude: ['Return to RegEngine.com'],
  },
  {
    path: '/pricing',
    mustInclude: [
      'href="/signup?plan=base&amp;billing=annual"',
      'href="/signup?plan=standard&amp;billing=annual"',
      'href="/signup?plan=premium&amp;billing=annual"',
      'under 12 minutes',
    ],
    mustNotInclude: ['Under 10 minutes', 'Most customers', 'direct ERP connectors', 'href="/onboarding"'],
  },
];

let failures = 0;

for (const check of checks) {
  const url = new URL(check.path, baseUrl);
  const res = await fetch(url);
  const html = await res.text();

  if (!res.ok) {
    console.error(`${check.path}: expected HTTP 2xx, got ${res.status}`);
    failures += 1;
    continue;
  }

  for (const needle of check.mustInclude ?? []) {
    if (!html.includes(needle)) {
      console.error(`${check.path}: missing expected text: ${needle}`);
      failures += 1;
    }
  }

  for (const needle of check.mustNotInclude ?? []) {
    if (html.includes(needle)) {
      console.error(`${check.path}: found forbidden text: ${needle}`);
      failures += 1;
    }
  }
}

if (failures > 0) {
  console.error(`SSR verification failed with ${failures} issue${failures === 1 ? '' : 's'}.`);
  process.exit(1);
}

process.stdout.write(`SSR verification passed for ${checks.length} public routes at ${baseUrl}.\n`);
