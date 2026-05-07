import { describe, expect, it } from 'vitest';

import { hasPermission, permissionImplies, sanitizePermissions } from '@/lib/permissions';

describe('permissions helpers', () => {
    it('sanitizes metadata permission arrays', () => {
        expect(sanitizePermissions([' inflow.write ', '', 42, 'admin:*'])).toEqual([
            'inflow.write',
            'admin:*',
        ]);
        expect(sanitizePermissions('inflow.write')).toBeUndefined();
    });

    it('understands wildcard and namespace permission grants', () => {
        expect(permissionImplies('*', 'inflow.write')).toBe(true);
        expect(permissionImplies('admin.*', 'admin.users.read')).toBe(true);
        expect(permissionImplies('inflow:*', 'inflow.write')).toBe(true);
        expect(permissionImplies('inflow.read', 'inflow.write')).toBe(false);
    });

    it('checks whether a permission set grants a required capability', () => {
        expect(hasPermission(['inflow.read', 'inflow:*'], 'inflow.write')).toBe(true);
        expect(hasPermission(['inflow.read'], 'inflow.write')).toBe(false);
        expect(hasPermission(undefined, 'inflow.write')).toBe(false);
    });
});
