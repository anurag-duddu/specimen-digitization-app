#!/usr/bin/env node
// Run with Node >=22, the pinned Dart SDK, and Chrome. Compiles the actual
// production adapter with dart2js -O4, then uses fresh headless Chrome and two
// loopback origins. No npm packages, existing profile, or provider is involved.
// DART_EXECUTABLE / CHROME_EXECUTABLE select installed tools. The optional
// INTAKE_AUTH_APP_ROOT supports a private source overlay for mutation checks.
const assert = require('node:assert/strict');
const {spawn, spawnSync} = require('node:child_process');
const fs = require('node:fs/promises');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');

assert.ok(Number(process.versions.node.split('.')[0]) >= 22, 'Node >=22 is required');
const appRoot = process.env.INTAKE_AUTH_APP_ROOT ||
  path.resolve(__dirname, '../../apps/specimen_digitization');
const chromePath = process.env.CHROME_EXECUTABLE ||
  (process.platform === 'darwin'
    ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : 'google-chrome');
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function until(action, label, milliseconds = 20000) {
  const deadline = Date.now() + milliseconds;
  while (Date.now() < deadline) {
    const value = await action();
    if (value) return value;
    await delay(20);
  }
  throw new Error(`Timed out: ${label}`);
}

class DevTools {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 0;
    this.pending = new Map();
    this.exceptions = [];
    socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const operation = this.pending.get(message.id);
        if (!operation) return;
        this.pending.delete(message.id);
        if (message.error) operation.reject(new Error(JSON.stringify(message.error)));
        else operation.resolve(message.result);
      } else if (message.method === 'Runtime.exceptionThrown') {
        const detail = message.params.exceptionDetails;
        this.exceptions.push(detail.exception?.description || detail.text);
      }
    });
  }
  send(method, params = {}, sessionId) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`DevTools timed out: ${method}`));
      }, 20000);
      this.pending.set(id, {
        resolve: value => { clearTimeout(timeout); resolve(value); },
        reject: error => { clearTimeout(timeout); reject(error); },
      });
      this.socket.send(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}));
    });
  }
  async attach(targetId) {
    const {sessionId} = await this.send('Target.attachToTarget', {targetId, flatten: true});
    await this.send('Runtime.enable', {}, sessionId);
    return sessionId;
  }
  async evaluate(sessionId, expression, userGesture = false) {
    const response = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true, userGesture,
    }, sessionId);
    assert.equal(response.exceptionDetails, undefined,
      JSON.stringify(response.exceptionDetails));
    return response.result.value;
  }
  async targets() {
    return (await this.send('Target.getTargets')).targetInfos;
  }
}

async function serve(script) {
  const server = http.createServer((request, response) => {
    response.setHeader('Cache-Control', 'no-store');
    if (request.url === '/fixture.js' && script) {
      response.setHeader('Content-Type', 'text/javascript');
      response.end(script);
    } else {
      response.setHeader('Content-Type', 'text/html');
      response.end(request.url === '/' && script
        ? '<!doctype html><title>Intake auth fixture</title><script src="/fixture.js"></script>'
        : '<!doctype html><title>Synthetic OAuth callback</title>Callback fixture');
    }
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return {server, origin: `http://127.0.0.1:${server.address().port}`};
}

(async () => {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'specimen-intake-auth-browser-'));
  let chrome, mainServer, callbackServer, client;
  try {
    const compiled = path.join(temporary, 'fixture.js');
    const build = spawnSync(process.env.DART_EXECUTABLE || 'dart', [
      '--suppress-analytics', 'compile', 'js', '-O4',
      `--packages=${path.join(appRoot, '.dart_tool/package_config.json')}`, '-o', compiled,
      'test/verification/intake_auth_browser_app.dart',
    ], {cwd: appRoot, encoding: 'utf8', timeout: 120000, maxBuffer: 2 * 1024 * 1024});
    assert.equal(build.status, 0, build.error?.message || build.stderr || build.stdout);
    const main = await serve(await fs.readFile(compiled));
    mainServer = main.server;
    const callback = await serve();
    callbackServer = callback.server;
    assert.notEqual(main.origin, callback.origin);
    const profile = path.join(temporary, 'chrome-profile');
    chrome = spawn(chromePath, [
      '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
      '--disable-background-networking', '--disable-sync', '--disable-extensions',
      '--disable-popup-blocking', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
      'about:blank',
    ], {stdio: 'ignore'});
    let chromeFailure;
    chrome.once('error', error => { chromeFailure = error; });
    const port = await until(async () => {
      if (chromeFailure) throw chromeFailure;
      if (chrome.exitCode !== null) throw new Error(`Chrome exited ${chrome.exitCode}`);
      try {
        return (await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0];
      } catch (error) {
        if (error.code !== 'ENOENT') throw error;
        return false;
      }
    }, 'fresh Chrome debugging endpoint');
    const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
    const socket = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve, {once: true});
      socket.addEventListener('error', reject, {once: true});
    });
    client = new DevTools(socket);
    const {targetId} = await client.send('Target.createTarget', {url: main.origin});
    const app = await client.attach(targetId);
    await until(() => client.evaluate(app,
      'typeof window.intakeAuthBrowserState === "function"'), 'compiled Dart entry point');
    const state = () => client.evaluate(app, 'JSON.parse(window.intakeAuthBrowserState())');
    // Observe only listeners installed after the fixture's barrier listener.
    // The real adapter must remove its message listener after every outcome.
    await client.evaluate(app, `(() => {
      const active = new Set();
      const add = window.addEventListener.bind(window);
      const remove = window.removeEventListener.bind(window);
      window.addEventListener = (type, listener, options) => {
        if (type === 'message') active.add(listener);
        return add(type, listener, options);
      };
      window.removeEventListener = (type, listener, options) => {
        if (type === 'message') active.delete(listener);
        return remove(type, listener, options);
      };
      window.intakeAuthBrowserListenerCount = () => active.size;
    })()`);
    const listenerCount = () => client.evaluate(app, 'window.intakeAuthBrowserListenerCount()');
    const url = new URL('/authorize', callback.origin);
    url.searchParams.set('state', 'synthetic-state');
    url.searchParams.set('redirect_uri', `${callback.origin}/callback`);
    const existing = new Set((await client.targets()).map(target => target.targetId));
    await client.evaluate(app,
      `window.intakeAuthBrowserStart(${JSON.stringify(url.href)}, true)`, true);
    const popup = await until(async () => (await client.targets()).find(target =>
      !existing.has(target.targetId) && target.url === url.href), 'production popup navigation');
    const popupSession = await client.attach(popup.targetId);
    assert.equal(await client.evaluate(popupSession,
      '(() => { try { void opener.document; return false; } catch (e) { return e.name === "SecurityError"; } })()'),
    true, 'The popup must have an actual cross-origin WindowProxy');

    let barrier = 0;
    async function rejectedMessage(sessionId, message, label, advanceClock = false) {
      const sequence = ++barrier;
      await client.evaluate(sessionId,
        `opener.postMessage(${JSON.stringify(message)}, ${JSON.stringify(main.origin)});` +
        `opener.postMessage({fixtureBarrier:${sequence}}, ${JSON.stringify(main.origin)});`);
      if (advanceClock) {
        await client.send('Emulation.setVirtualTimePolicy', {policy: 'advance', budget: 100}, app);
      }
      await until(async () => (await state()).barrier === sequence, `${label} event barrier`);
      assert.equal((await state()).status, 'pending', `${label} must be ignored`);
      assert.deepEqual(client.exceptions, [], 'Compiled callback guard must not throw');
    }

    // Correct popup, wrong origin: the guard must reject before reading data.
    await client.send('Page.navigate', {url: `${main.origin}/callback`}, popupSession);
    await until(async () => await client.evaluate(popupSession, 'location.origin') === main.origin,
      'wrong-origin popup navigation');
    await rejectedMessage(popupSession, {state: 'synthetic-state', code: 'wrong-origin'}, 'wrong origin');
    await client.send('Page.navigate', {url: `${callback.origin}/callback`}, popupSession);
    await until(async () => await client.evaluate(popupSession, 'location.origin') === callback.origin,
      'callback-origin popup navigation');

    // Correct origin and state, but another real popup is not the reserved one.
    const beforeRogue = new Set((await client.targets()).map(target => target.targetId));
    await client.evaluate(app, `void window.open(${JSON.stringify(`${callback.origin}/callback`)}, "_blank")`, true);
    const rogue = await until(async () => (await client.targets()).find(target =>
      !beforeRogue.has(target.targetId) && target.url === `${callback.origin}/callback`), 'unrelated popup');
    const rogueSession = await client.attach(rogue.targetId);
    await rejectedMessage(rogueSession, {state: 'synthetic-state', code: 'wrong-source'}, 'wrong source');
    await client.send('Target.closeTarget', {targetId: rogue.targetId});
    await rejectedMessage(popupSession, {state: 'wrong-state', code: 'wrong-state'}, 'wrong state');
    await client.evaluate(app, `window.dispatchEvent(new MessageEvent("message", {` +
      `origin:${JSON.stringify(callback.origin)}, source:null, data:{state:"synthetic-state",code:"null-source"}}))`);
    assert.equal((await state()).status, 'pending', 'A null source must be ignored');

    const accepted = {state: 'synthetic-state', code: 'synthetic-code'};
    await client.evaluate(popupSession,
      `opener.postMessage(${JSON.stringify(accepted)}, ${JSON.stringify(main.origin)})`);
    await until(async () => (await state()).status === 'completed', 'actual Dart callback completion');
    assert.deepEqual((await state()).response, accepted);
    assert.deepEqual(client.exceptions, [], 'Compiled callback must complete without SecurityError');
    assert.ok((await client.targets()).some(target => target.targetId === popup.targetId),
      'Drive keepOpen must preserve the authenticated popup');
    await client.evaluate(app, 'window.intakeAuthBrowserClose()');
    await until(async () => !(await client.targets()).some(target => target.targetId === popup.targetId),
      'explicit popup cleanup');

    // Non-Picker OAuth retains its existing default of closing after success.
    const beforeDefault = new Set((await client.targets()).map(target => target.targetId));
    await client.evaluate(app,
      `window.intakeAuthBrowserStart(${JSON.stringify(url.href)}, false)`, true);
    const defaultPopup = await until(async () => (await client.targets()).find(target =>
      !beforeDefault.has(target.targetId) && target.url === url.href), 'default OAuth popup');
    const defaultSession = await client.attach(defaultPopup.targetId);
    await client.evaluate(defaultSession,
      `opener.postMessage(${JSON.stringify(accepted)}, ${JSON.stringify(main.origin)})`);
    await until(async () => (await state()).status === 'completed', 'default callback completion');
    assert.deepEqual((await state()).response, accepted);
    await until(async () => !(await client.targets()).some(target => target.targetId === defaultPopup.targetId),
      'default popup cleanup');
    assert.equal(await listenerCount(), 0, 'Successful callbacks must remove their listeners');

    // Advance Chrome's test clock through the real ten-minute production limit;
    // no shorter timeout or clock seam is added to the production adapter.
    await client.send('Emulation.setVirtualTimePolicy', {policy: 'pause'}, app);
    const expiringUrl = new URL(url);
    expiringUrl.searchParams.set('state', 'synthetic-expired-state');
    const beforeExpiry = new Set((await client.targets()).map(target => target.targetId));
    const startedAt = await client.evaluate(app, 'Date.now()');
    await client.evaluate(app,
      `window.intakeAuthBrowserStart(${JSON.stringify(expiringUrl.href)}, true)`, true);
    const expiredPopup = await until(async () => (await client.targets()).find(target =>
      !beforeExpiry.has(target.targetId) && target.url === expiringUrl.href), 'expiring OAuth popup');
    assert.equal(await listenerCount(), 1);
    await client.send('Emulation.setVirtualTimePolicy', {policy: 'advance', budget: 599000}, app);
    await until(async () => await client.evaluate(app, 'Date.now()') >= startedAt + 599000,
      'just before the authorization deadline');
    assert.equal((await state()).status, 'pending', 'Consent must remain available before ten minutes');
    await client.send('Emulation.setVirtualTimePolicy', {policy: 'advance', budget: 1001}, app);
    await until(async () => (await state()).status === 'failed', 'authorization deadline');
    assert.equal((await state()).errorCode, 'connection_expired');
    assert.equal((await state()).errorMessage,
      'Connection expired. Connect again to finish authorizing this account.');
    assert.equal((await state()).recoveryAction, 'connect');
    assert.equal(await listenerCount(), 0, 'An expired wait must remove its message listener');
    await until(async () => !(await client.targets()).some(target => target.targetId === expiredPopup.targetId),
      'expired keepOpen popup cleanup');

    // A user retry creates a new session/window/state. The old callback state
    // remains invalid even when it is sent by the new, correctly scoped popup.
    const retryUrl = new URL(url);
    retryUrl.searchParams.set('state', 'synthetic-retry-state');
    const beforeRetry = new Set((await client.targets()).map(target => target.targetId));
    await client.evaluate(app,
      `window.intakeAuthBrowserStart(${JSON.stringify(retryUrl.href)}, false)`, true);
    const retryPopup = await until(async () => (await client.targets()).find(target =>
      !beforeRetry.has(target.targetId) && target.url === retryUrl.href), 'fresh retry popup');
    assert.notEqual(retryPopup.targetId, expiredPopup.targetId);
    const retrySession = await client.attach(retryPopup.targetId);
    await rejectedMessage(retrySession,
      {state: 'synthetic-expired-state', code: 'stale-code'}, 'expired state after retry', true);
    const retried = {state: 'synthetic-retry-state', code: 'synthetic-retry-code'};
    await client.evaluate(retrySession,
      `opener.postMessage(${JSON.stringify(retried)}, ${JSON.stringify(main.origin)})`);
    await client.send('Emulation.setVirtualTimePolicy', {policy: 'advance', budget: 100}, app);
    await until(async () => (await state()).status === 'completed', 'fresh retry callback');
    assert.deepEqual((await state()).response, retried);
    assert.equal(await listenerCount(), 0);
    await until(async () => !(await client.targets()).some(target => target.targetId === retryPopup.targetId),
      'retry popup cleanup');
    assert.deepEqual(client.exceptions, []);
    console.log(JSON.stringify({status: 'passed', evidence: 'actual dart2js -O4 adapter and fresh Chrome on loopback',
      checks: {crossOriginWindowProxy: true, wrongOriginRejected: true, wrongSourceRejected: true,
        wrongStateRejected: true, nullSourceRejected: true, validCallbackCompleted: true,
        pickerKeptOpen: true, defaultPopupClosed: true, tenMinuteConsentWindowPreserved: true,
        expiryHasConnectRecovery: true, expiredPopupClosed: true, listenersRemoved: true,
        expiredStateRejectedAfterRetry: true, freshRetryCompleted: true}}));
  } catch (error) {
    console.error(error);
    if (client?.exceptions.length) console.error(JSON.stringify({browserExceptions: client.exceptions}));
    process.exitCode = 1;
  } finally {
    if (client) {
      await client.send('Browser.close').catch(() => {});
      client.socket.close();
    }
    if (chrome && chrome.exitCode === null) {
      await Promise.race([new Promise(resolve => chrome.once('exit', resolve)), delay(3000)]);
      if (chrome.exitCode === null) chrome.kill('SIGKILL');
    }
    await Promise.all([mainServer, callbackServer].filter(Boolean).map(server =>
      new Promise(resolve => server.close(resolve))));
    await fs.rm(temporary, {recursive: true, force: true, maxRetries: 5, retryDelay: 100});
  }
})();
