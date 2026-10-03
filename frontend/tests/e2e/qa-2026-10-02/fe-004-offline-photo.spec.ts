import { test, expect, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';
import { isolateRegressionBrowser, syntheticUser, writeRegressionEvidence } from './fe-regression-support';

async function photosInBrowser(page: Page) {
  return page.evaluate(async () => {
    const records = await new Promise<any[]>((resolve, reject) => {
      const open = indexedDB.open('RegEngineMobileDB');
      open.onerror = () => reject(open.error);
      open.onsuccess = () => {
        const db = open.result;
        if (!db.objectStoreNames.contains('photos')) { db.close(); return resolve([]); }
        const transaction = db.transaction('photos', 'readonly');
        const request = transaction.objectStore('photos').getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
        transaction.oncomplete = () => db.close();
      };
    });
    return Promise.all(records.map(async record => ({
      ...record,
      blob: { type: record.blob.type, size: record.blob.size,
        base64: btoa(String.fromCharCode(...new Uint8Array(await record.blob.arrayBuffer()))) },
    })));
  });
}

test('FE-004 keeps account A offline photos out of account B replay requests', async ({ context, page, baseURL, browserName }, testInfo) => {
  let account = 'a';
  // Local middleware only decodes claims; every API remains intercepted.
  // These fixture tokens have a deliberately non-authentic signature.
  const fixtureToken = (identity: string) => [
    Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url'),
    Buffer.from(JSON.stringify({ sub: `qa-user-${identity}`, tenant_id: `qa-tenant-${identity}`,
      aud: 'regengine-api', iss: 'regengine-admin', exp: Math.floor(Date.now() / 1000) + 3600 })).toString('base64url'),
    'qa-fixture-not-a-signature',
  ].join('.');
  const accountAToken = fixtureToken('a');
  const accountBToken = fixtureToken('b');
  const sessionReads: string[] = [];
  const uploadAttempts: Array<{ account: string; path: string; cookieIdentifiesAccountB: boolean; body: Buffer }> = [];
  const pageErrors: string[] = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  await isolateRegressionBrowser(context, baseURL!, async (route, url) => {
    if (url.pathname === '/api/session') {
      sessionReads.push(account);
      await route.fulfill({ status: 200, json: {
        authenticated: true, has_credentials: true, has_api_key: false,
        tenant_id: `qa-tenant-${account}`, user: syntheticUser(account), auth_method: 'email_otp',
      } });
      return true;
    }
    if (url.pathname.endsWith('/api/v1/ingest/csv')) {
      const headers = await route.request().allHeaders();
      uploadAttempts.push({ account, path: url.pathname,
        cookieIdentifiesAccountB: (headers.cookie || '').includes(`re_access_token=${accountBToken}`),
        body: route.request().postDataBuffer() || Buffer.alloc(0),
      });
      // Reject synthetic upload: prove dispatch without suggesting data persisted.
      await route.fulfill({ status: 422, json: { detail: 'QA synthetic boundary: photo persistence is not exercised.' } });
      return true;
    }
    return false;
  });
  await context.addCookies([{ name: 're_access_token', value: accountAToken,
    url: baseURL!, httpOnly: true, sameSite: 'Lax' }]);

  const response = await page.goto('/fsma/field-capture');
  expect(response?.status()).toBe(200);
  await expect(page.getByRole('tab', { name: 'Photo', exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('regengine_tenant_id'))).toBe('qa-tenant-a');
  await expect.poll(() => photosInBrowser(page).then(photos => photos.length)).toBe(0);
  await page.getByRole('tab', { name: 'Photo', exact: true }).click();
  await context.setOffline(true);
  await expect(page.getByText('Offline', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => navigator.onLine)).toBe(false);
  // Seed a synthetic legacy photo with the exact existing savePhoto record shape
  // into REAL IndexedDB. Camera acquisition and data-URL capture are not part of
  // this replay witness; all reads and upload/retry behavior use the built app.
  try {
    await page.evaluate(async () => {
    const canvas = document.createElement('canvas');
    canvas.width = 96; canvas.height = 64;
    const drawing = canvas.getContext('2d')!;
    drawing.fillStyle = '#14532d'; drawing.fillRect(0, 0, 96, 64);
    drawing.fillStyle = 'white'; drawing.font = '12px sans-serif'; drawing.fillText('QA ACCOUNT A', 4, 32);
    const jpegBytes = Uint8Array.from(atob(canvas.toDataURL('image/jpeg', 0.8).split(',')[1]), byte => byte.charCodeAt(0));
    const blob = new Blob([jpegBytes], { type: 'image/jpeg' });
    await new Promise<void>((resolve, reject) => {
      const open = indexedDB.open('RegEngineMobileDB');
      open.onerror = () => reject(open.error);
      open.onsuccess = () => {
        const db = open.result;
        const transaction = db.transaction('photos', 'readwrite');
        const add = transaction.objectStore('photos').add({ blob, timestamp: Date.now(), synced: 0, syncAttempts: 0 });
        add.onerror = () => reject(new Error(`Photo fixture request failed: ${add.error?.name}: ${add.error?.message}`));
        transaction.oncomplete = () => { db.close(); resolve(); };
        transaction.onerror = () => { db.close(); reject(new Error(`Photo fixture write failed: ${transaction.error?.name}: ${transaction.error?.message}`)); };
        transaction.onabort = () => { db.close(); reject(new Error(`Photo fixture transaction aborted: ${transaction.error?.name}: ${transaction.error?.message}`)); };
      };
    });
    });
  } catch (error) {
    const message = String(error);
    if (browserName !== 'webkit' || !message.includes('UnknownError: Error preparing Blob/File data to be stored in object store')) throw error;
    // Distinguish native browser storage failure from a product failure using a
    // separate database with no Dexie, React, auth or application code involved.
    const nativeControl = await page.evaluate(async () => {
      const db = await new Promise<IDBDatabase>((resolve, reject) => {
        const open = indexedDB.open('qa-fe004-native-capability', 1);
        open.onupgradeneeded = () => open.result.createObjectStore('controls');
        open.onerror = () => reject(open.error);
        open.onsuccess = () => resolve(open.result);
      });
      const outcomes = [];
      for (const [kind, value] of [['string', 'qa'], ['blob', new Blob(['qa'], { type: 'text/plain' })]] as const) {
        outcomes.push(await new Promise<{ kind: string; success: boolean; error?: string }>(resolve => {
          const transaction = db.transaction('controls', 'readwrite');
          const put = transaction.objectStore('controls').put(value, kind);
          put.onerror = () => resolve({ kind, success: false, error: `${put.error?.name}: ${put.error?.message}` });
          transaction.oncomplete = () => resolve({ kind, success: true });
        }));
      }
      db.close();
      return outcomes;
    });
    await writeRegressionEvidence(testInfo, 'fe-004-webkit-environment', { fixtureError: message, nativeControl });
    expect(nativeControl).toEqual([
      { kind: 'string', success: true },
      { kind: 'blob', success: false, error: 'UnknownError: Error preparing Blob/File data to be stored in object store' },
    ]);
    test.skip(true, 'WebKit server native IndexedDB Blob storage fails UnknownError; separate string control passes. FE-004 replay remains unverified here.');
  }
  await expect.poll(() => photosInBrowser(page).then(photos => photos.length)).toBe(1);
  const queuedA = (await photosInBrowser(page))[0];
  expect(queuedA.synced).toBe(0);
  expect(queuedA.blob.type).toBe('image/jpeg');
  expect(queuedA.blob.size).toBeGreaterThan(100);
  expect(uploadAttempts).toHaveLength(0);
  const queuedBytes = Buffer.from(queuedA.blob.base64, 'base64');
  const aScreenshot = await writeRegressionEvidence(testInfo, 'fe-004-account-a', {
    account: 'a', tenant: 'qa-tenant-a', offline: true, setup: 'Synthetic legacy photo seeded in actual IndexedDB', queuedRecord: queuedA,
    sha256: createHash('sha256').update(queuedBytes).digest('hex'), uploads: 0,
  });
  await page.screenshot({ path: aScreenshot, fullPage: true });

  // Unmount offline A before reconnecting; emulate the server changing accounts.
  // The real IndexedDB persists in the same browser context across both sessions.
  await page.goto('about:blank');
  account = 'b';
  await context.addCookies([{ name: 're_access_token', value: accountBToken,
    url: baseURL!, httpOnly: true, sameSite: 'Lax' }]);
  await context.setOffline(false);
  await page.goto('/fsma/field-capture');
  await expect(page.getByRole('tab', { name: 'Photo', exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('regengine_tenant_id'))).toBe('qa-tenant-b');
  expect(sessionReads).toEqual(['a', 'b']);
  await expect(page.getByText('Online', { exact: true })).toBeVisible();
  // Allow the asynchronous IndexedDB/auto-sync effect to settle; this delay also
  // permits a corrected implementation with no upload to reach the assertion.
  await page.waitForTimeout(1500);
  const retainedB = await photosInBrowser(page);
  expect(pageErrors).toEqual([]);
  const attempts = uploadAttempts.map(attempt => ({
    account: attempt.account, path: attempt.path,
    cookieIdentifiesAccountB: attempt.cookieIdentifiesAccountB,
    containsExactAccountAPhoto: attempt.body.includes(queuedBytes),
    includesOfflineSource: attempt.body.includes(Buffer.from('mobile_capture_pwa_offline')),
    multipartBytes: attempt.body.length,
  }));
  const screenshot = await writeRegressionEvidence(testInfo, 'fe-004-account-b', {
    sessionReads, queuedASha256: createHash('sha256').update(queuedBytes).digest('hex'),
    attempts, retainedB, pageErrors,
    boundary: 'Actual built FieldCapture, AuthProvider, useSync and IndexedDB; synthetic legacy photo seeded offline; synthetic session replacement; uploads intercepted and rejected 422. Camera, real login/logout and server persistence not exercised.',
  });
  await page.screenshot({ path: screenshot, fullPage: true });

  test.fail(true, 'FE-004: account B sends account A ownerless queued photo with its current cookie.');
  expect(attempts.filter(attempt => attempt.cookieIdentifiesAccountB && attempt.containsExactAccountAPhoto)).toEqual([]);
});
