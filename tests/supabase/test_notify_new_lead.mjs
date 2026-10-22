import assert from "node:assert/strict";
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
);

function loadHandler(variables) {
  let handler;
  const sends = [];
  runInNewContext(runnableSource, {
    Deno: {
      env: { get: (name) => variables[name] },
      serve: (fn) => { handler = fn; },
    },
    Response,
    fetch: async (...args) => {
      sends.push(args);
      return { status: 202 };
    },
    console: { log() {}, error() {} },
  }, { filename: sourcePath });
  assert.equal(typeof handler, "function");
  return { handler, sends };
}

function request(method = "POST", secret) {
  let reads = 0;
  return {
    value: {
      method,
      headers: new Headers(secret === undefined ? {} : { "x-webhook-secret": secret }),
      json: async () => {
        reads += 1;
        return { record: { name: "Test Lead", email: "lead@example.test", company: "Test Co" } };
      },
    },
    reads: () => reads,
  };
}

test("missing, empty, or whitespace WEBHOOK_SECRET fails closed", async () => {
  for (const configured of [undefined, "", "   "]) {
    const { handler, sends } = loadHandler({ WEBHOOK_SECRET: configured, RESEND_API_KEY: "mock-key" });
    const incoming = request("POST", "any-value");
    const response = await handler(incoming.value);
    assert.equal(response.status, 503);
    assert.deepEqual(await response.json(), { error: "Webhook authentication unavailable" });
    assert.equal(incoming.reads(), 0);
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
  assert.deepEqual(await response.json(), { ok: true, lead: "lead@example.test" });
  assert.equal(incoming.reads(), 1);
  assert.equal(sends.length, 1);
  assert.equal(sends[0][0], "https://api.resend.com/emails");
  assert.equal(sends[0][1].headers.Authorization, "Bearer mock-key");
  assert.match(JSON.parse(sends[0][1].body).text, /Email: lead@example\.test/);
});

test("non-POST requests return 405 without parsing or sending", async () => {
  const { handler, sends } = loadHandler({ WEBHOOK_SECRET: "expected", RESEND_API_KEY: "mock-key" });
  const incoming = request("GET", "expected");
  const response = await handler(incoming.value);
  assert.equal(response.status, 405);
  assert.equal(incoming.reads(), 0);
  assert.equal(sends.length, 0);
});
