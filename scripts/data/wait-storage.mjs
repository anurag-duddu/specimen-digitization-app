import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function hubEmulators(port, timeoutMs) {
  // Keep the GET on loopback without redirects or pooled connections.
  const request = http.get({hostname:'127.0.0.1', port, path:'/emulators', agent:false});
  let timer;
  try {
    return await new Promise((resolve, reject) => {
      request.once('error', reject);
      timer = setTimeout(() => request.destroy(new Error('Storage hub probe timed out')), timeoutMs);
      request.once('response', response => {
        response.once('error', reject);
        if (response.statusCode !== 200) { reject(new Error(`Storage hub returned ${response.statusCode}`)); return; }
        response.setEncoding('utf8');
        let body = '';
        response.on('data', chunk => {
          body += chunk;
          if (body.length > 65536) request.destroy(new Error('Storage hub response too large'));
        });
        response.once('end', () => {
          try { resolve(JSON.parse(body)); } catch (error) { reject(error); }
        });
      });
    });
  } finally { clearTimeout(timer); request.destroy(); }
}

async function storagePortOpen(port, timeoutMs) {
  const socket = net.createConnection({host:'127.0.0.1', port});
  try {
    await new Promise((resolve, reject) => {
      socket.once('connect', resolve);
      socket.once('error', reject);
      // A deadline can expire between checks; zero disables socket timeouts.
      socket.setTimeout(Math.max(1, timeoutMs), () => reject(new Error('Storage TCP probe timed out')));
    });
  } finally { socket.destroy(); }
}

// The standalone CLI and JVM need their own startup budget; the SQL root-404
// probe is not a Storage protocol. Cap the entire wait at 30s (including hung
// HTTP bodies/TCP probes), within the engine job's existing ten-minute budget.
// Pinned firebase-tools v15.8.0 src/emulator/hub.ts:74-97 returns a map keyed
// by emulator name, with host/port in each EmulatorInfo, at GET /emulators:
// https://github.com/firebase/firebase-tools/blob/v15.8.0/src/emulator/hub.ts#L74-L97
export async function waitForStorage({hubPort, storagePort, checkRunning, timeoutMs = 30000}) {
  for (const port of [hubPort, storagePort]) assert.ok(Number.isInteger(port) && port > 0 && port < 65536, 'invalid Storage readiness port');
  assert.ok(Number.isInteger(timeoutMs) && timeoutMs > 0 && timeoutMs <= 30000, 'invalid Storage readiness budget');
  assert.equal(typeof checkRunning, 'function', 'Storage readiness requires a process/download guard');
  const deadline = performance.now() + timeoutMs;
  const remaining = () => Math.max(0, Math.ceil(deadline - performance.now()));
  while (remaining() > 0) {
    checkRunning();
    let ready = false;
    try {
      const emulators = await hubEmulators(hubPort, Math.min(500, remaining()));
      ready = emulators?.storage?.host === '127.0.0.1' && emulators.storage.port === storagePort;
    } catch { /* A starting hub may refuse connections or return incomplete JSON. */ }
    checkRunning();
    if (ready && remaining() > 0) {
      // A closed loopback port can silently drop SYNs. Keep each TCP attempt
      // short enough to observe startup and process exits on the next poll.
      try { await storagePortOpen(storagePort, Math.min(100, remaining())); }
      catch { ready = false; }
      checkRunning();
      if (ready && remaining() > 0) return;
    }
    if (remaining() > 0) await delay(Math.min(100, remaining()));
  }
  checkRunning();
  throw new Error(`Storage emulator did not become ready within ${timeoutMs} ms: hub must list storage at 127.0.0.1:${storagePort} and its TCP port must accept connections`);
}
