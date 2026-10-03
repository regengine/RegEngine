// QA-only process guard: do not read dotenv/credential files or connect off-host.
// Load with NODE_OPTIONS=--require=/absolute/path/to/this/file.
const fs = require('node:fs');
const net = require('node:net');
const dns = require('node:dns');
const { syncBuiltinESMExports } = require('node:module');

function sensitive(file) {
  if (typeof file !== 'string' && !(file instanceof URL)) return false;
  const name = String(file);
  return /(^|[/\\])\.env(?:[./\\]|$)/.test(name)
    || /(^|[/\\])(?:\.npmrc|\.netrc|credentials|id_rsa|id_ed25519)(?:[/\\]|$)/.test(name);
}
function absent(file) {
  const error = new Error('QA isolation: protected configuration file unavailable');
  error.code = 'ENOENT';
  return error;
}
for (const name of ['readFileSync', 'openSync', 'statSync', 'lstatSync', 'accessSync']) {
  const original = fs[name];
  fs[name] = function (file, ...args) {
    if (sensitive(file)) throw absent(file);
    return original.call(this, file, ...args);
  };
}
const existsSync = fs.existsSync;
fs.existsSync = function (file) { return !sensitive(file) && existsSync.call(this, file); };
for (const name of ['readFile', 'open', 'stat', 'lstat', 'access']) {
  const original = fs[name];
  fs[name] = function (file, ...args) {
    if (sensitive(file)) {
      const callback = args.at(-1);
      if (typeof callback === 'function') return queueMicrotask(() => callback(absent(file)));
      throw absent(file);
    }
    return original.call(this, file, ...args);
  };
  const promiseOriginal = fs.promises[name];
  fs.promises[name] = async function (file, ...args) {
    if (sensitive(file)) throw absent(file);
    return promiseOriginal.call(this, file, ...args);
  };
}
function local(host) {
  return !host || ['localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0'].includes(host);
}
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  // net.connect()/http.request() may supply Node's normalized [options, cb]
  // argument array rather than the public positional/options call shape.
  const normalized = Array.isArray(args[0]) ? args[0] : args;
  const options = normalized[0];
  const host = options && typeof options === 'object'
    ? options.host || options.hostname
    : typeof normalized[1] === 'string' ? normalized[1] : undefined;
  if (!local(host)) throw new Error('QA isolation: off-host socket blocked');
  return connect.apply(this, args);
};
for (const name of ['lookup', 'resolve', 'resolve4', 'resolve6', 'resolveAny']) {
  const original = dns[name];
  dns[name] = function (hostname, ...args) {
    if (!local(hostname)) throw new Error('QA isolation: off-host DNS blocked');
    return original.call(this, hostname, ...args);
  };
}
const fetch = globalThis.fetch;
if (fetch) globalThis.fetch = async function (input, ...args) {
  const raw = typeof input === 'string' || input instanceof URL ? input : input.url;
  const target = new URL(raw, 'http://localhost');
  if (!local(target.hostname)) throw new Error('QA isolation: off-host fetch blocked');
  return fetch.call(this, input, ...args);
};
syncBuiltinESMExports();
