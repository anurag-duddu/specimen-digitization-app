'use strict';
// Test-only interception: the unchanged upstream bundle cannot reach the network
// except this synthetic loopback server. Production never loads this module.
const http = require('node:http');
const https = require('node:https');
const realRequest = http.request.bind(http);
function route(options, callback) {
  if (typeof options === 'string' || options instanceof URL) options = new URL(options);
  const hostname = options.hostname || options.host;
  if (!['synthetic.actions.githubusercontent.com', 'sts.googleapis.com', 'iamcredentials.googleapis.com'].includes(hostname)) {
    throw new Error('Offline auth fixture rejected an unexpected host');
  }
  return realRequest({ hostname: '127.0.0.1', port: Number(process.env.SYNTHETIC_AUTH_PORT),
    path: options.path || options.pathname + options.search, method: options.method,
    headers: { ...options.headers, 'x-synthetic-target': hostname }, agent: false }, callback);
}
https.request = route;
https.get = (options, callback) => { const request = route(options, callback); request.end(); return request; };
http.request = () => { throw new Error('Offline auth fixture rejected direct HTTP'); };
http.get = http.request;
