import { spawn } from 'node:child_process';

const baseUrl = process.env.PUBLIC_SSR_BASE_URL ?? 'http://127.0.0.1:3011';
const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
let managedServer = null;

function isLocalBaseUrl(url) {
  return ['127.0.0.1', 'localhost'].includes(url.hostname);
}

async function canReach(url) {
  try {
    const response = await fetch(new URL('/login', url));
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForServer(url, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await canReach(url)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for SSR server at ${url}`);
}

async function ensureServer(url) {
  if (await canReach(url)) {
    return;
  }
  if (!isLocalBaseUrl(url)) {
    throw new Error(`SSR server is not reachable at ${url}`);
  }

  const port = url.port || '3011';
  managedServer = spawn(
    npmCommand,
    ['run', 'start', '--', '--hostname', '127.0.0.1', '--port', port],
    {
      stdio: 'inherit',
      env: { ...process.env, PORT: port, HOSTNAME: '127.0.0.1' },
    },
  );

  const cleanup = () => {
    if (managedServer && !managedServer.killed) {
      managedServer.kill('SIGTERM');
    }
  };
  process.on('exit', cleanup);
  process.on('SIGINT', () => {
    cleanup();
    process.exit(130);
  });
  process.on('SIGTERM', () => {
    cleanup();
    process.exit(143);
  });

  await waitForServer(url);
}

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

try {
  const resolvedBaseUrl = new URL(baseUrl);
  await ensureServer(resolvedBaseUrl);

  for (const check of checks) {
    const url = new URL(check.path, resolvedBaseUrl);
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
    process.exitCode = 1;
  } else {
    process.stdout.write(`SSR verification passed for ${checks.length} public routes at ${resolvedBaseUrl}.\n`);
  }
} finally {
  if (managedServer && !managedServer.killed) {
    managedServer.kill('SIGTERM');
  }
}
