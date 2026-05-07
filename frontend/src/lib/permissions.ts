function normalizePermission(permission: string): string {
  return permission.trim().toLowerCase().replaceAll(':', '.');
}

export function sanitizePermissions(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;

  return value
    .filter((permission): permission is string => typeof permission === 'string')
    .map((permission) => permission.trim())
    .filter((permission) => permission.length > 0);
}

export function permissionImplies(grantedPermission: string, requiredPermission: string): boolean {
  const granted = normalizePermission(grantedPermission);
  const required = normalizePermission(requiredPermission);

  if (!granted || !required) {
    return false;
  }

  if (granted === '*' || granted === 'admin.*' || granted === 'super_admin') {
    return true;
  }

  if (granted === required) {
    return true;
  }

  if (granted.endsWith('.*')) {
    const namespace = granted.slice(0, -2);
    return required.startsWith(`${namespace}.`);
  }

  return false;
}

export function hasPermission(
  grantedPermissions: readonly string[] | null | undefined,
  requiredPermission: string,
): boolean {
  if (!grantedPermissions?.length) {
    return false;
  }

  return grantedPermissions.some((grantedPermission) =>
    permissionImplies(grantedPermission, requiredPermission),
  );
}
