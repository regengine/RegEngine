import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { seedClientSessionUser } from '@/lib/client-session-profile';

export const OTP_CHALLENGE_STORAGE_KEY = 'regengine_passwordless_otp_challenge';

export type ChallengeStartResponse = {
  detail?: string;
  message?: string;
  challenge_id?: string;
  sso_redirect?: boolean;
  organization_id?: string;
  sso_url?: string;
};

export type StoredOtpChallenge = {
  email: string;
  challengeId: string | null;
  createdAt: number;
};

export function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export function saveOtpChallengeState(state: StoredOtpChallenge): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.setItem(OTP_CHALLENGE_STORAGE_KEY, JSON.stringify(state));
}

export function loadOtpChallengeState(): StoredOtpChallenge | null {
  if (typeof window === 'undefined') return null;
  const raw = window.sessionStorage.getItem(OTP_CHALLENGE_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredOtpChallenge>;
    if (typeof parsed.email !== 'string') return null;
    return {
      email: parsed.email,
      challengeId: typeof parsed.challengeId === 'string' ? parsed.challengeId : null,
      createdAt: typeof parsed.createdAt === 'number' ? parsed.createdAt : Date.now(),
    };
  } catch {
    return null;
  }
}

export function clearOtpChallengeState(): void {
  if (typeof window === 'undefined') return;
  window.sessionStorage.removeItem(OTP_CHALLENGE_STORAGE_KEY);
}

export async function startEmailChallenge(email: string): Promise<ChallengeStartResponse> {
  const response = await fetchWithCsrf('/api/admin/auth/challenges', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email }),
  });

  const data = await readJson<ChallengeStartResponse>(response);
  if (!response.ok) {
    throw buildApiError(response, data);
  }
  return data || {};
}

export async function verifyEmailChallenge(challengeId: string, code: string): Promise<void> {
  const response = await fetchWithCsrf(
    `/api/admin/auth/challenges/${encodeURIComponent(challengeId)}/verify`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ code }),
    },
  );

  const data = await readJson(response);
  if (!response.ok) {
    throw buildApiError(response, data);
  }
}

export async function performPasskeyLogin(email: string): Promise<void> {
  if (typeof window === 'undefined' || !window.PublicKeyCredential || !navigator.credentials?.get) {
    throw new Error('Passkeys are not available in this browser.');
  }

  const optionsResponse = await fetchWithCsrf('/api/admin/auth/webauthn/login/generate-options', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ email }),
  });
  const optionsJson = await readJson<Record<string, unknown>>(optionsResponse);
  if (!optionsResponse.ok || !optionsJson) {
    throw buildApiError(optionsResponse, optionsJson);
  }

  const credential = await navigator.credentials.get({
    publicKey: toPublicKeyRequestOptions(optionsJson),
  });
  if (!credential || credential.type !== 'public-key') {
    throw new Error('No passkey assertion was returned.');
  }

  const verifyResponse = await fetchWithCsrf('/api/admin/auth/webauthn/login/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ credential: serializeAssertion(credential as PublicKeyCredential) }),
  });
  const verifyJson = await readJson(verifyResponse);
  if (!verifyResponse.ok) {
    throw buildApiError(verifyResponse, verifyJson);
  }
}

export async function registerPasskey(): Promise<void> {
  if (typeof window === 'undefined' || !window.PublicKeyCredential || !navigator.credentials?.create) {
    throw new Error('Passkeys are not available in this browser.');
  }

  const optionsResponse = await fetchWithCsrf('/api/admin/auth/webauthn/register/generate-options', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
  });
  const optionsJson = await readJson<Record<string, unknown>>(optionsResponse);
  if (!optionsResponse.ok || !optionsJson) {
    throw buildApiError(optionsResponse, optionsJson);
  }

  const credential = await navigator.credentials.create({
    publicKey: toPublicKeyCreationOptions(optionsJson),
  });
  if (!credential || credential.type !== 'public-key') {
    throw new Error('No passkey credential was returned.');
  }

  const verifyResponse = await fetchWithCsrf('/api/admin/auth/webauthn/register/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ credential: serializeAttestation(credential as PublicKeyCredential) }),
  });
  const verifyJson = await readJson(verifyResponse);
  if (!verifyResponse.ok) {
    throw buildApiError(verifyResponse, verifyJson);
  }
}

export function seedPasswordlessClientUser(email: string): void {
  seedClientSessionUser(email);
}

function toPublicKeyCreationOptions(options: Record<string, unknown>): PublicKeyCredentialCreationOptions {
  const challenge = options.challenge;
  const rp = asRecord(options.rp);
  const user = asRecord(options.user);
  const userId = user.id;
  if (typeof challenge !== 'string' || typeof userId !== 'string') {
    throw new Error('Passkey registration challenge is missing.');
  }

  return {
    rp: {
      id: typeof rp.id === 'string' ? rp.id : undefined,
      name: typeof rp.name === 'string' ? rp.name : 'RegEngine',
    },
    user: {
      id: base64UrlToArrayBuffer(userId),
      name: typeof user.name === 'string' ? user.name : 'RegEngine user',
      displayName: typeof user.displayName === 'string' ? user.displayName : 'RegEngine user',
    },
    challenge: base64UrlToArrayBuffer(challenge),
    pubKeyCredParams: Array.isArray(options.pubKeyCredParams)
      ? options.pubKeyCredParams
        .map((param): PublicKeyCredentialParameters | null => {
          const record = asRecord(param);
          return typeof record.alg === 'number'
            ? { type: 'public-key', alg: record.alg }
            : null;
        })
        .filter((param): param is PublicKeyCredentialParameters => param !== null)
      : [{ type: 'public-key', alg: -7 }],
    timeout: typeof options.timeout === 'number' ? options.timeout : undefined,
    excludeCredentials: Array.isArray(options.excludeCredentials)
      ? options.excludeCredentials
        .map(toCredentialDescriptor)
        .filter((credential): credential is PublicKeyCredentialDescriptor => credential !== null)
      : undefined,
    authenticatorSelection: toAuthenticatorSelection(options.authenticatorSelection),
    attestation: options.attestation === 'direct' || options.attestation === 'enterprise' || options.attestation === 'indirect'
      ? options.attestation
      : 'none',
  };
}

function toPublicKeyRequestOptions(options: Record<string, unknown>): PublicKeyCredentialRequestOptions {
  const challenge = options.challenge;
  if (typeof challenge !== 'string') {
    throw new Error('Passkey challenge is missing.');
  }

  const allowCredentials = Array.isArray(options.allowCredentials)
    ? options.allowCredentials
      .map(toCredentialDescriptor)
      .filter((credential): credential is PublicKeyCredentialDescriptor => credential !== null)
    : undefined;

  return {
    challenge: base64UrlToArrayBuffer(challenge),
    timeout: typeof options.timeout === 'number' ? options.timeout : undefined,
    rpId: typeof options.rpId === 'string' ? options.rpId : undefined,
    allowCredentials,
    userVerification: options.userVerification === 'discouraged' || options.userVerification === 'preferred'
      ? options.userVerification
      : 'required',
  };
}

function toAuthenticatorSelection(value: unknown): AuthenticatorSelectionCriteria | undefined {
  const selection = asRecord(value);
  if (Object.keys(selection).length === 0) return undefined;
  return {
    authenticatorAttachment: selection.authenticatorAttachment === 'cross-platform'
      ? 'cross-platform'
      : selection.authenticatorAttachment === 'platform'
        ? 'platform'
        : undefined,
    requireResidentKey: typeof selection.requireResidentKey === 'boolean'
      ? selection.requireResidentKey
      : undefined,
    residentKey: selection.residentKey === 'discouraged' || selection.residentKey === 'preferred' || selection.residentKey === 'required'
      ? selection.residentKey
      : undefined,
    userVerification: selection.userVerification === 'discouraged' || selection.userVerification === 'preferred'
      ? selection.userVerification
      : 'required',
  };
}

function toCredentialDescriptor(credential: unknown): PublicKeyCredentialDescriptor | null {
  const record = asRecord(credential);
  if (typeof record.id !== 'string') return null;
  return {
    id: base64UrlToArrayBuffer(record.id),
    type: 'public-key',
    transports: Array.isArray(record.transports)
      ? record.transports.filter((item): item is AuthenticatorTransport => typeof item === 'string')
      : undefined,
  };
}

function serializeAttestation(credential: PublicKeyCredential) {
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: arrayBufferToBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    response: {
      attestationObject: arrayBufferToBase64Url(response.attestationObject),
      clientDataJSON: arrayBufferToBase64Url(response.clientDataJSON),
      transports: typeof response.getTransports === 'function' ? response.getTransports() : undefined,
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

function serializeAssertion(credential: PublicKeyCredential) {
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: arrayBufferToBase64Url(credential.rawId),
    type: credential.type,
    response: {
      authenticatorData: arrayBufferToBase64Url(response.authenticatorData),
      clientDataJSON: arrayBufferToBase64Url(response.clientDataJSON),
      signature: arrayBufferToBase64Url(response.signature),
      userHandle: response.userHandle ? arrayBufferToBase64Url(response.userHandle) : null,
    },
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function base64UrlToArrayBuffer(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/').padEnd(
    value.length + ((4 - (value.length % 4)) % 4),
    '=',
  );
  const binary = window.atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

function arrayBufferToBase64Url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let index = 0; index < bytes.byteLength; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return window.btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function readJson<T = unknown>(response: Response): Promise<T | null> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

function buildApiError(response: Response, payload: unknown): Error & { response?: { status: number; data: unknown } } {
  const detail = payload && typeof payload === 'object'
    ? (payload as { detail?: unknown; error?: unknown; message?: unknown }).detail
      ?? (payload as { detail?: unknown; error?: unknown; message?: unknown }).error
      ?? (payload as { detail?: unknown; error?: unknown; message?: unknown }).message
    : null;
  const message = typeof detail === 'string' && detail.trim()
    ? detail
    : response.statusText || 'Authentication request failed';
  const error = new Error(message) as Error & { response?: { status: number; data: unknown } };
  error.response = { status: response.status, data: payload };
  return error;
}
