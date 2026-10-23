import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import { fileURLToPath } from "node:url";

const sourcePath = fileURLToPath(
  new URL("../../supabase/functions/notify-new-lead/index.ts", import.meta.url),
);
const source = readFileSync(sourcePath, "utf8");
const runtimeImport = 'import "jsr:@supabase/functions-js/edge-runtime.d.ts";\n';
const typedHandler = "Deno.serve(async (req: Request) => {";
assert.ok(source.startsWith(runtimeImport));
assert.ok(source.includes(typedHandler));
const runnableSource = source.slice(runtimeImport.length).replace(
  typedHandler,
  "Deno.serve(async (req) => {",
).replace(
  "async function secretsMatch(expected: string, incoming: string)",
  "async function secretsMatch(expected, incoming)",
);

function loadHandler(variables, rpc = { status: 200, secret: "rpc-secret" }) { // pragma: allowlist secret
  let handler;
  const sends = [];
  const rpcCalls = [];
  runInNewContext(runnableSource, {
    Deno: {
      env: { get: (name) => variables[name] },
      serve: (fn) => { handler = fn; },
    },
    Response,
    TextEncoder,
    crypto: webcrypto,
    fetch: async (...args) => {
      if (args[0].endsWith("/rest/v1/rpc/get_notify_new_lead_secret")) {
        rpcCalls.push(args);
        if (rpc.error) throw rpc.error;
        return { ok: rpc.status === 200, json: async () => rpc.secret };
      }
      sends.push(args);
      if (rpc.resendError) throw rpc.resendError;
      return { status: 202 };
    },
    console: { log() {}, error() {} },
  }, { filename: sourcePath });
  assert.equal(typeof handler, "function");
  return { handler, sends, rpcCalls };
}

function request(method = "POST", secret, payload = { record: { name: "Test Lead", email: "lead@example.test", company: "Test Co" } }) {
  let reads = 0;
  return {
    value: {
      method,
      headers: new Headers(secret === undefined ? {} : { "x-webhook-secret": secret }),
      json: async () => {
        reads += 1;
        return payload;
      },
    },
    reads: () => reads,
  };
}

test("missing, empty, or whitespace secret configuration fails closed", async () => {
  for (const configured of [undefined, "", "   "]) {
    const { handler, sends } = loadHandler({ WEBHOOK_SECRET: configured, RESEND_API_KEY: "mock-key" }, { status: 500 });
    const incoming = request("POST", "any-value");
    const response = await handler(incoming.value);
    assert.equal(response.status, 500);
    assert.deepEqual(await response.json(), { error: "Server misconfigured" });
    assert.equal(incoming.reads(), 0);
    assert.equal(sends.length, 0);
  }
});

test("RPC fallback authenticates and caches the secret", async () => {
  const { handler, sends, rpcCalls } = loadHandler({
    SUPABASE_URL: "https://supabase.example.test",
    SUPABASE_SERVICE_ROLE_KEY: "service-role-test-key",
    RESEND_API_KEY: "mock-key", // pragma: allowlist secret
  });
  for (const secret of [undefined, "wrong"]) {
    const incoming = request("POST", secret);
    const response = await handler(incoming.value);
    assert.equal(response.status, 401);
    assert.deepEqual(await response.json(), { error: "Unauthorized" });
    assert.equal(incoming.reads(), 0);
  }
  assert.equal(sends.length, 0);
  for (let i = 0; i < 2; i++) {
    const response = await handler(request("POST", "rpc-secret").value);
    assert.equal(response.status, 200);
  }
  assert.equal(rpcCalls.length, 1);
  assert.equal(rpcCalls[0][0], "https://supabase.example.test/rest/v1/rpc/get_notify_new_lead_secret");
  assert.equal(rpcCalls[0][1].method, "POST");
  assert.equal(rpcCalls[0][1].headers.apikey, "service-role-test-key");
  assert.equal(rpcCalls[0][1].headers.Authorization, "Bearer service-role-test-key");
  assert.equal(rpcCalls[0][1].body, "{}");
  assert.equal(sends.length, 2);
});

test("RPC returning no usable secret fails closed", async () => {
  for (const rpc of [{ status: 500 }, { status: 200, secret: null }, { status: 200, secret: "" }, { error: new Error("network failure") }]) {
    const { handler, sends } = loadHandler({ SUPABASE_URL: "https://supabase.example.test", SUPABASE_SERVICE_ROLE_KEY: "service-role-test-key" }, rpc);
    const response = await handler(request("POST", "anything").value);
    assert.equal(response.status, 500);
    assert.deepEqual(await response.json(), { error: "Server misconfigured" });
    assert.equal(sends.length, 0);
  }
});

test("missing and incorrect headers are rejected before parsing or sending", async () => {
  for (const header of [undefined, "wrong"]) {
    const { handler, sends } = loadHandler({ WEBHOOK_SECRET: "expected", RESEND_API_KEY: "mock-key" });
    const incoming = request("POST", header);
    const response = await handler(incoming.value);
    assert.equal(response.status, 401);
    assert.equal(incoming.reads(), 0);
    assert.equal(sends.length, 0);
  }
});

test("authenticated POST preserves notification behavior with mocked Resend", async () => {
  const { handler, sends } = loadHandler({ WEBHOOK_SECRET: "expected", RESEND_API_KEY: "mock-key" });
  const incoming = request("POST", "expected");
  const response = await handler(incoming.value);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ok: true });
  assert.equal(incoming.reads(), 1);
  assert.equal(sends.length, 1);
  assert.equal(sends[0][0], "https://api.resend.com/emails");
  assert.equal(sends[0][1].headers.Authorization, "Bearer mock-key");
  assert.match(JSON.parse(sends[0][1].body).subject, /^New Lead:/);
  assert.match(JSON.parse(sends[0][1].body).text, /Email: lead@example\.test/);
});

test("test leads get a subject prefix", async () => {
  for (const payload of [
    { record: { name: "Lead", source: "test" } },
    { test: true, record: { name: "Lead", source: "quiz" } },
  ]) {
    const { handler, sends } = loadHandler({ WEBHOOK_SECRET: "expected", RESEND_API_KEY: "mock-key" });
    const response = await handler(request("POST", "expected", payload).value);
    assert.equal(response.status, 200);
    assert.match(JSON.parse(sends[0][1].body).subject, /^\[TEST\] New Lead:/);
  }
});

test("internal errors have a generic response", async () => {
  const { handler } = loadHandler(
    { WEBHOOK_SECRET: "expected", RESEND_API_KEY: "mock-key" }, // pragma: allowlist secret
    { resendError: new Error("private provider detail") },
  );
  const response = await handler(request("POST", "expected").value);
  assert.equal(response.status, 500);
  assert.deepEqual(await response.json(), { ok: false, error: "Internal error" });
});

test("non-POST requests return 405 without parsing or sending", async () => {
  const { handler, sends } = loadHandler({ WEBHOOK_SECRET: "expected", RESEND_API_KEY: "mock-key" });
  const incoming = request("GET", "expected");
  const response = await handler(incoming.value);
  assert.equal(response.status, 405);
  assert.equal(incoming.reads(), 0);
  assert.equal(sends.length, 0);
});
