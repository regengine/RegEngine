import { test, expect } from '@playwright/test';
import { isolateRegressionBrowser, writeRegressionEvidence } from './fe-regression-support';

test('FE-001 preserves complete GS1 lot identifiers in the real scanner form', async ({ context, page, baseURL }, testInfo) => {
  await isolateRegressionBrowser(context, baseURL!);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const response = await page.goto('/tools/scan');
  expect(response?.status()).toBe(200);
  await expect(page.getByRole('heading', { name: 'RegEngine • Scan & Ingest', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Save your GS1 scan result', exact: true })).toBeVisible();
  const input = page.getByLabel('Paste or type barcode string…');
  const lotField = page.getByLabel('Lot Code', { exact: true });
  const enterBarcode = async (barcode: string) => {
    // Firefox's native fill path strips ASCII GS; set the actual DOM input
    // with the native setter and notify React, exactly retaining scanner bytes.
    await input.evaluate((element, value) => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(element, value);
      element.dispatchEvent(new Event('input', { bubbles: true }));
    }, barcode);
    expect(await input.inputValue()).toBe(barcode);
  };

  // Both a simple AI lot and an encoded Digital Link must work first.
  for (const [barcode, lot] of [
    ['010950600013435210ALPHA\x1d17260930', 'ALPHA'],
    ['/01/09506000134352/10/LOT-10-ABC', 'LOT-10-ABC'],
  ]) {
    await enterBarcode(barcode);
    await page.getByRole('button', { name: 'Parse', exact: true }).click();
    await expect(lotField).toHaveValue(lot);
  }

  const observations = [];
  for (const lot of ['LOT-10-ABC', 'LOT-21-ABC', 'LOT-17260930']) {
    const barcode = `010950600013435210${lot}\x1d17260930`;
    await enterBarcode(barcode);
    await page.getByRole('button', { name: 'Parse', exact: true }).click();
    await expect(input).toHaveValue(''); // confirms React handler ran
    await expect(page.getByText('Raw Barcode String', { exact: true })).toBeVisible();
    observations.push({ barcode, expectedLot: lot, actualLot: await lotField.inputValue() });
  }
  expect(errors).toEqual([]);
  const screenshot = await writeRegressionEvidence(testInfo, 'fe-001', {
    url: page.url(), browser: testInfo.project.name, controlsPassed: 2,
    observations, pageErrors: errors, boundary: 'Real built scanner UI; native DOM setter/input event preserves ASCII GS fixture because Firefox fill strips it; no ingest or server persistence.',
  });
  await page.screenshot({ path: screenshot, fullPage: true });

  expect(observations.map(value => value.actualLot)).toEqual(observations.map(value => value.expectedLot));
});
