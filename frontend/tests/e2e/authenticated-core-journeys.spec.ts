import fs from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { expect, test, type APIResponse, type BrowserContext, type Page } from '@playwright/test';
import { hasPasswordlessE2E, passwordlessE2ESkipReason } from './auth-prereqs';
import { csrfHeader, loginViaApi, logoutViaApi } from './support/api-auth';

const TEST_USER_EMAIL = process.env.TEST_USER_EMAIL || 'test@example.com';
const DEFAULT_ADMIN_DB = 'sqlite:////tmp/regengine-playwright-admin.db';
const DEFAULT_EMAIL_OUTBOX = '/tmp/regengine-playwright-email-outbox.jsonl';

type CoreSession = Awaited<ReturnType<typeof loginViaApi>>;
type AdminRole = {
    id: string;
    name: string;
};
type AdminUser = {
    id: string;
    email: string;
    status: string;
};
type InvitePayload = {
    id: string;
    email: string;
    role_id: string;
    status: string;
    invite_link: string;
};
type InviteEmailOutboxRecord = {
    type?: string;
    to?: string;
    invite_link?: string;
};
type ProductPayload = {
    id: string;
    name: string;
    category: string;
    sku: string;
    gtin?: string;
    description?: string;
    suppliers?: string[];
    facilities?: string[];
};

function escapeRegex(value: string): string {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function expectResponseOk(response: APIResponse, label: string): Promise<void> {
    expect(response.ok(), `${label}: ${await response.text()}`).toBeTruthy();
}

async function login(context: BrowserContext): Promise<CoreSession> {
    return loginViaApi(context, TEST_USER_EMAIL);
}

function ingestionPath(tenantId: string, path: string): string {
    return `/api/ingestion/api/v1/${path.replace(/^\/+/, '')}/${tenantId}`;
}

function adminSqlitePath(): string {
    return (process.env.ADMIN_FALLBACK_SQLITE || DEFAULT_ADMIN_DB).replace(/^sqlite:\/*/, '/');
}

function emailOutboxPath(): string {
    return process.env.REGENGINE_E2E_EMAIL_OUTBOX || DEFAULT_EMAIL_OUTBOX;
}

function isLocalE2E(): boolean {
    return !process.env.PLAYWRIGHT_BASE_URL;
}

function parseInviteEmailOutboxLine(line: string): InviteEmailOutboxRecord | null {
    try {
        return JSON.parse(line) as InviteEmailOutboxRecord;
    } catch {
        return null;
    }
}

function readInviteEmailOutbox(email: string): InviteEmailOutboxRecord[] {
    const outbox = emailOutboxPath();
    if (!fs.existsSync(outbox)) return [];
    return fs.readFileSync(outbox, 'utf-8')
        .split('\n')
        .filter(Boolean)
        .map(parseInviteEmailOutboxLine)
        .filter((record): record is InviteEmailOutboxRecord => record?.type === 'invite_email' && record.to === email);
}

function removeInviteEmailOutboxRecords(email: string): void {
    const outbox = emailOutboxPath();
    if (!fs.existsSync(outbox)) return;
    const remaining = fs.readFileSync(outbox, 'utf-8')
        .split('\n')
        .filter(Boolean)
        .filter((line) => parseInviteEmailOutboxLine(line)?.to !== email);
    fs.writeFileSync(outbox, remaining.length > 0 ? `${remaining.join('\n')}\n` : '', 'utf-8');
}

function expectAdminAuditLog(tenantId: string, eventType: string, resourceId: string): void {
    const database = new DatabaseSync(adminSqlitePath());
    try {
        const row = database
            .prepare('SELECT event_type, resource_type, resource_id FROM audit_logs WHERE tenant_id = ? AND event_type = ? AND resource_id = ? LIMIT 1')
            .get(tenantId, eventType, resourceId) as { event_type: string } | undefined;
        expect(row, `${eventType} audit log exists for ${resourceId}`).toBeTruthy();
    } finally {
        database.close();
    }
}

function cleanupInviteFixture(tenantId: string | null, email: string, userId?: string, inviteId?: string): void {
    removeInviteEmailOutboxRecords(email);
    if (!tenantId || !isLocalE2E()) return;

    const database = new DatabaseSync(adminSqlitePath());
    try {
        if (userId) {
            database.prepare('DELETE FROM memberships WHERE tenant_id = ? AND user_id = ?').run(tenantId, userId);
        }
        if (inviteId) {
            database.prepare('DELETE FROM invites WHERE id = ?').run(inviteId);
        }
        database.prepare('DELETE FROM invites WHERE tenant_id = ? AND email = ?').run(tenantId, email);
        database.prepare('DELETE FROM audit_logs WHERE tenant_id = ? AND (resource_id IN (?, ?) OR "metadata" LIKE ?)')
            .run(tenantId, inviteId || '', userId || '', `%${email}%`);
        database.prepare('DELETE FROM users WHERE email = ?').run(email);
    } finally {
        database.close();
    }
}

async function getInviteRole(context: BrowserContext): Promise<AdminRole> {
    const response = await context.request.get('/api/admin/v1/admin/roles');
    await expectResponseOk(response, 'list roles for invite');
    const payload = await response.json() as { items?: AdminRole[] };
    const roles = payload.items || [];
    const role = roles.find(item => /viewer/i.test(item.name)) || roles.find(item => /member/i.test(item.name)) || roles[0];
    expect(role?.id, 'invite role is available').toBeTruthy();
    return role;
}

async function createInvite(context: BrowserContext, email: string, roleId: string): Promise<InvitePayload> {
    const response = await context.request.post('/api/admin/v1/admin/invites', {
        headers: await csrfHeader(context),
        data: {
            email,
            role_id: roleId,
        },
    });
    await expectResponseOk(response, `create invite for ${email}`);
    const payload = await response.json() as InvitePayload;
    expect(payload.email).toBe(email);
    expect(payload.status).toBe('pending');
    expect(payload.invite_link).toContain('token=');
    return payload;
}

async function expectMemberInBackend(context: BrowserContext, email: string): Promise<AdminUser> {
    const response = await context.request.get('/api/admin/v1/admin/users');
    await expectResponseOk(response, `list users for ${email}`);
    const payload = await response.json() as { items?: AdminUser[] };
    const member = (payload.items || []).find(user => user.email === email);
    expect(member?.status).toBe('active');
    return member!;
}

async function createProduct(
    context: BrowserContext,
    tenantId: string,
    product: { name: string; category: string; sku: string },
): Promise<ProductPayload> {
    const response = await context.request.post(ingestionPath(tenantId, 'products'), {
        headers: await csrfHeader(context),
        data: product,
    });
    await expectResponseOk(response, `create product ${product.name}`);
    const payload = await response.json() as { created?: boolean; product?: ProductPayload };
    expect(payload.created).toBe(true);
    expect(payload.product?.name).toBe(product.name);
    expect(payload.product?.id).toBeTruthy();
    return payload.product!;
}

async function deleteProduct(
    context: BrowserContext,
    tenantId: string,
    productId: string,
): Promise<void> {
    const response = await context.request.delete(`${ingestionPath(tenantId, 'products')}/${productId}`, {
        headers: await csrfHeader(context),
    });
    if (response.status() === 404) return;
    await expectResponseOk(response, `delete product ${productId}`);
}

async function expectProductInBackend(
    context: BrowserContext,
    tenantId: string,
    productName: string,
    category: string,
): Promise<void> {
    const response = await context.request.get(
        `${ingestionPath(tenantId, 'products')}?category=${encodeURIComponent(category)}`,
    );
    await expectResponseOk(response, `list products for ${category}`);
    const payload = await response.json() as {
        total: number;
        products: Array<{ name: string; category: string }>;
    };
    expect(payload.products.some(product => product.name === productName)).toBe(true);
}

async function expectProductMissingInBackend(
    context: BrowserContext,
    tenantId: string,
    productName: string,
    category: string,
): Promise<void> {
    const response = await context.request.get(
        `${ingestionPath(tenantId, 'products')}?category=${encodeURIComponent(category)}`,
    );
    await expectResponseOk(response, `list products for ${category}`);
    const payload = await response.json() as {
        products: Array<{ name: string; category: string }>;
    };
    expect(payload.products.some(product => product.name === productName)).toBe(false);
}

async function gotoProducts(page: Page): Promise<void> {
    await page.goto('/dashboard/products');
    await expect(page.getByRole('heading', { name: 'Product Catalog' })).toBeVisible();
}

async function openCategoryFilter(page: Page, category: string): Promise<void> {
    const filter = page.locator('button').filter({
        hasText: new RegExp(`^${escapeRegex(category)} \\(`),
    });
    await expect(filter).toBeVisible();
    await filter.click();
}

test.describe.serial('Authenticated core journeys', () => {
    test.beforeEach(() => {
        test.skip(!hasPasswordlessE2E, passwordlessE2ESkipReason);
    });

    test('primary resource create -> list -> open -> edit -> delete with UI and backend assertions', async ({ page, context }) => {
        const session = await login(context);
        const tenantId = String(session.tenant_id);
        const runId = Date.now();
        const category = `E2E Primary ${runId}`;
        const productName = `E2E Tomato ${runId}`;
        const editedName = `${productName} Edited`;
        let createdProduct: ProductPayload | null = null;

        try {
            createdProduct = await createProduct(context, tenantId, {
                name: productName,
                category,
                sku: `E2E-${runId}`,
            });

            await gotoProducts(page);
            await expect(page.getByText(productName)).toBeVisible();
            await openCategoryFilter(page, category);
            const productCard = page.getByRole('region', { name: `Product ${productName}` });
            await expect(productCard.getByText(productName)).toBeVisible();
            await productCard.getByRole('button', { name: /^open$/i }).click();

            const detail = page.getByRole('region', { name: 'Product detail' });
            await expect(detail).toBeVisible();
            await expect(detail.getByRole('heading', { name: productName })).toBeVisible();
            await expectProductInBackend(context, tenantId, productName, category);

            await detail.getByRole('button', { name: /edit product/i }).click();
            await page.getByLabel('Product Name').fill(editedName);
            await page.getByLabel('SKU').fill(`E2E-${runId}-EDIT`);
            await detail.getByRole('button', { name: /^save$/i }).click();
            await expect(detail.getByRole('heading', { name: editedName })).toBeVisible();
            await expectProductInBackend(context, tenantId, editedName, category);

            page.once('dialog', dialog => dialog.accept());
            await detail.getByRole('button', { name: /delete product/i }).click();
            await expect(page.getByText(editedName)).toHaveCount(0);
            await expectProductMissingInBackend(context, tenantId, editedName, category);
            createdProduct = null;
        } finally {
            if (createdProduct) {
                await deleteProduct(context, tenantId, createdProduct.id);
            }
        }
    });

    test('settings change persists across logout and API login', async ({ page, context }) => {
        const session = await login(context);
        const tenantId = String(session.tenant_id);
        const runId = Date.now();
        const seededProfile = {
            company_name: `E2E Settings Co ${runId}`,
            company_type: 'manufacturer',
            primary_contact: `E2E Contact ${runId}`,
            contact_email: session.user.email,
            phone: '+1 555 0100',
            address: `100 E2E Way ${runId}`,
            website: '',
            fei_number: `FEI-${runId}`,
        };
        const updatedPhone = '+1 555 0199';
        const resetProfile = {
            company_name: '',
            company_type: 'distributor',
            primary_contact: '',
            contact_email: '',
            phone: '',
            address: '',
            website: '',
            fei_number: '',
        };

        try {
            const seed = await context.request.put(ingestionPath(tenantId, 'settings') + '/profile', {
                headers: await csrfHeader(context),
                data: seededProfile,
            });
            await expectResponseOk(seed, 'seed settings profile');

            await page.goto('/dashboard/settings');
            await expect(page.getByRole('heading', { name: 'Account Settings' })).toBeVisible();
            await expect(page.locator('input').nth(0)).toHaveValue(seededProfile.company_name);

            await page.locator('input').nth(3).fill(updatedPhone);
            await page.getByRole('button', { name: /save changes/i }).click();
            await expect(page.getByRole('button', { name: /saved/i })).toBeVisible();

            const backendAfterSave = await context.request.get(ingestionPath(tenantId, 'settings'));
            await expectResponseOk(backendAfterSave, 'read settings after save');
            const savedPayload = await backendAfterSave.json() as { profile: { phone: string } };
            expect(savedPayload.profile.phone).toBe(updatedPhone);

            await logoutViaApi(context);
            await context.clearCookies();
            await login(context);

            await page.goto('/dashboard/settings');
            await expect(page.locator('input').nth(0)).toHaveValue(seededProfile.company_name);
            await expect(page.locator('input').nth(3)).toHaveValue(updatedPhone);
        } finally {
            await context.request.put(ingestionPath(tenantId, 'settings') + '/profile', {
                headers: await csrfHeader(context),
                data: resetProfile,
            });
        }
    });

    test('search/filter on populated dataset returns expected results and backend pagination', async ({ page, context }, testInfo) => {
        const session = await login(context);
        const tenantId = String(session.tenant_id);
        const runId = Date.now();
        const category = `E2E Batch ${runId}`;
        const products = Array.from({ length: 55 }, (_, index) => ({
            name: `E2E Batch Product ${runId}-${String(index + 1).padStart(2, '0')}`,
            category,
            sku: `E2E-BATCH-${runId}-${index + 1}`,
        }));
        const createdProducts: ProductPayload[] = [];

        try {
            for (const product of products) {
                createdProducts.push(await createProduct(context, tenantId, product));
            }

            await gotoProducts(page);
            await openCategoryFilter(page, category);
            await expect(page.getByText(products[0].name)).toBeVisible();

            const pageThree = await context.request.get(
                `${ingestionPath(tenantId, 'products')}?category=${encodeURIComponent(category)}&skip=50&limit=10`,
            );
            await expectResponseOk(pageThree, 'read paginated product page');
            const pageThreePayload = await pageThree.json() as {
                total: number;
                products: Array<{ name: string }>;
            };
            expect(pageThreePayload.total).toBe(55);
            expect(pageThreePayload.products).toHaveLength(5);
            expect(pageThreePayload.products[0].name).toBe(products[50].name);

            testInfo.annotations.push({
                type: 'remaining-gap',
                description: 'Product catalog has category filtering but no dedicated search box or UI pagination controls yet.',
            });
        } finally {
            for (const product of createdProducts) {
                await deleteProduct(context, tenantId, product.id);
            }
        }
    });

    test('invite collaborator -> email sent -> accept invite -> appears in member list', async ({ page, context }) => {
        test.skip(!isLocalE2E(), 'Invite email outbox and SQLite membership assertions are local E2E fixtures.');

        const session = await login(context);
        const tenantId = String(session.tenant_id);
        const runId = Date.now();
        const inviteEmail = `e2e-core-invite-${runId}@example.com`;
        let inviteId: string | undefined;
        let invitedUserId: string | undefined;

        try {
            const role = await getInviteRole(context);
            const invite = await createInvite(context, inviteEmail, role.id);
            inviteId = invite.id;
            const inviteUrl = new URL(invite.invite_link, 'http://localhost');
            const token =
                inviteUrl.searchParams.get('token') ||
                new URLSearchParams(inviteUrl.hash.slice(1)).get('token');
            expect(token).toBeTruthy();

            const outboxRecords = readInviteEmailOutbox(inviteEmail);
            expect(
                outboxRecords.some(record => record.invite_link?.includes(`token=${token}`)),
                'invite email outbox includes the acceptance link',
            ).toBe(true);
            expectAdminAuditLog(tenantId, 'invite.create', invite.id);

            const accept = await context.request.post('/api/admin/v1/auth/accept-invite', {
                data: {
                    token,
                    name: 'E2E Core Invitee',
                },
            });
            await expectResponseOk(accept, `accept invite for ${inviteEmail}`);
            const acceptPayload = await accept.json() as { status: string; user_id: string };
            expect(acceptPayload.status).toBe('success');
            invitedUserId = acceptPayload.user_id;

            const member = await expectMemberInBackend(context, inviteEmail);
            expect(member.id).toBe(invitedUserId);
            expectAdminAuditLog(tenantId, 'invite.accept', invitedUserId);

            await page.goto('/settings/users');
            await expect(page.getByRole('heading', { name: 'Team Management' })).toBeVisible();
            await expect(page.getByText(inviteEmail)).toBeVisible();
        } finally {
            cleanupInviteFixture(tenantId, inviteEmail, invitedUserId, inviteId);
        }
    });

    test('billing/plan change -> account state and Stripe state', async () => {
        test.fixme(true, 'Stripe checkout exists, but E2E-safe plan mutation and Stripe state verification remain expected-broken.');
    });

    test('bulk action on 50+ items -> progress and backend completion', async () => {
        test.fixme(true, 'Bulk upload backend coverage exists in pytest, but the authenticated UI bulk-action journey is not exposed yet.');
    });
});
