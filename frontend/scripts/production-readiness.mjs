#!/usr/bin/env node

import { spawn } from 'node:child_process';

const CHECKS = [
  {
    name: 'Production dependency audit',
    command: 'npm',
    args: ['audit', '--audit-level=high', '--omit=dev'],
  },
  {
    name: 'Auth/session regression tests',
    command: 'npm',
    args: [
      'run',
      'test:run',
      '--',
      'src/__tests__/api/proxy-sanitization.test.ts',
      'src/__tests__/api/session-origin.test.ts',
      'src/__tests__/auth/login.test.tsx',
      'src/__tests__/instrumentation.test.ts',
    ],
  },
  {
    name: 'Auth/session lint slice',
    command: 'npx',
    args: [
      'eslint',
      'src/lib/jwt-keys.ts',
      'src/app/login/LoginClient.tsx',
      'src/__tests__/api/proxy-sanitization.test.ts',
      'src/__tests__/auth/login.test.tsx',
    ],
  },
];

function runCheck(check) {
  return new Promise((resolve, reject) => {
    console.log(`\n==> ${check.name}`);
    console.log(`$ ${[check.command, ...check.args].join(' ')}`);

    const child = spawn(check.command, check.args, {
      cwd: process.cwd(),
      env: process.env,
      shell: process.platform === 'win32',
      stdio: 'inherit',
    });

    child.on('error', reject);
    child.on('exit', (code, signal) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${check.name} failed${signal ? ` with signal ${signal}` : ` with exit code ${code}`}`));
    });
  });
}

for (const check of CHECKS) {
  await runCheck(check);
}

console.log('\nProduction readiness gate passed.');
