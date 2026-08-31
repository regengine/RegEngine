// Experimental QA preload: fail on unmocked network calls in trusted tests.
const deny = () => { throw new Error('QA isolation denied network access'); };
require('node:net').Socket.prototype.connect = deny;
require('node:net').Server.prototype.listen = deny;
require('node:tls').connect = deny;
require('node:dgram').Socket.prototype.bind = deny;
require('node:dgram').Socket.prototype.send = deny;
require('node:dns').lookup = deny;
require('node:dns').resolve = deny;
globalThis.fetch = deny;
