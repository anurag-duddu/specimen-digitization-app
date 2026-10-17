#!/usr/bin/env node
// Synthetic acceptance only. Build test/verification/email_session_browser_app.dart
// and serve its output on loopback; run Auth emulator project demo-login-journey.
// Requires Playwright and Chrome. Uses a fresh, non-persistent browser context.
//
// Local recipe (run the build from apps/specimen_digitization):
//   flutter build web --release --no-pub \
//     --target=test/verification/email_session_browser_app.dart --output=/tmp/email-session-web
//   python3 -m http.server 9412 --bind 127.0.0.1 --directory /tmp/email-session-web
// Start `firebase emulators:start --only auth --project demo-login-journey`
// with a dedicated temporary --config whose emulators object is:
// {"auth":{"host":"127.0.0.1","port":9409},"ui":{"enabled":false},
//  "hub":{"host":"127.0.0.1","port":9410},
//  "logging":{"host":"127.0.0.1","port":9411},"singleProjectMode":true}
// Then run this script from the repository root. EMAIL_SESSION_CHROME selects
// a Chrome executable; NODE_PATH may point to an existing Playwright install.
// EMAIL_SESSION_REPORT optionally saves its bounded JSON result. No live mail,
// production Auth endpoints, or existing browser profiles participate.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const { chromium } = require('playwright');

const origin = new URL(process.env.EMAIL_SESSION_ORIGIN || 'http://127.0.0.1:9412');
const authOrigin = new URL(process.env.EMAIL_SESSION_AUTH_ORIGIN || 'http://127.0.0.1:9409');
for (const value of [origin, authOrigin]) {
  assert.equal(value.protocol, 'http:');
  assert.ok(['localhost', '127.0.0.1'].includes(value.hostname));
  assert.equal(value.username + value.password + value.search + value.hash, '');
}
const project = 'demo-login-journey';
const email = 'browser-acceptance@fieldmuseum.org';
const output = process.env.EMAIL_SESSION_REPORT;

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.EMAIL_SESSION_CHROME ? {executablePath: process.env.EMAIL_SESSION_CHROME} : {}),
  });
  try {
    const context = await browser.newContext({viewport: {width: 1280, height: 900}});
    context.setDefaultTimeout(20000);
    context.setDefaultNavigationTimeout(30000);
    const rejected = [];
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      const local = [origin.origin, authOrigin.origin].includes(url.origin);
      const staticSdk = url.protocol === 'https:' && url.hostname === 'www.gstatic.com' &&
        (url.pathname.startsWith('/firebasejs/') || url.pathname.startsWith('/flutter-canvaskit/'));
      const fonts = url.protocol === 'https:' && ['fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname);
      if (local || staticSdk || fonts) return route.continue();
      rejected.push(url.origin + url.pathname); // Never record query strings.
      return route.abort();
    });
    const a = await context.newPage();
    await a.goto(origin.href);
    await a.waitForFunction(() => typeof window.emailSessionAcceptanceState === 'function');
    const state = page => page.evaluate(() => JSON.parse(window.emailSessionAcceptanceState()));
    assert.equal((await state(a)).signedIn, false);
    assert.equal((await state(a)).scopeLoads, 0);
    // Flutter's semantics textbox is a proxy for its focused editing control;
    // use keyboard events so the Dart TextEditingController receives input.
    await a.getByRole('textbox', {name: 'Email address', exact: true}).click();
    await a.keyboard.type(email);
    await a.keyboard.press('Tab');
    await a.getByRole('button', {name: 'Send link to sign in', exact: true}).click();
    await a.getByRole('heading', {name: 'Check your email', exact: true}).waitFor();
    await a.getByRole('button', {name: 'Open Gmail', exact: true}).waitFor();
    const codesResponse = await fetch(`${authOrigin.origin}/emulator/v1/projects/${project}/oobCodes`);
    assert.equal(codesResponse.status, 200);
    const codes = (await codesResponse.json()).oobCodes;
    const request = [...codes].reverse().find(item => item.email === email && item.requestType === 'EMAIL_SIGNIN');
    assert.ok(request && typeof request.oobCode === 'string', 'Auth emulator must receive the synthetic request');
    const b = await context.newPage();
    await b.goto(`${origin.origin}/?fixtureCode=${encodeURIComponent(request.oobCode)}`);
    await b.waitForFunction(() => typeof window.emailSessionAcceptanceState === 'function' &&
      JSON.parse(window.emailSessionAcceptanceState()).verified);
    await a.waitForFunction(() => JSON.parse(window.emailSessionAcceptanceState()).verified);
    await a.waitForFunction(() => JSON.parse(window.emailSessionAcceptanceState()).scopeLoads > 0);
    await b.waitForFunction(() => JSON.parse(window.emailSessionAcceptanceState()).scopeLoads > 0);
    const aState = await state(a), bState = await state(b);
    assert.ok(aState.uid.length > 0);
    assert.equal(aState.uid, bState.uid);
    assert.ok(aState.scopeLoads > 0 && bState.scopeLoads > 0);
    await a.waitForURL(url => decodeURIComponent(url.hash) === '#/c/browser/acceptance/queue?status=held');
    await a.getByRole('button', {name: `Account menu, signed in as ${email}`, exact: true}).click();
    await a.getByRole('menuitem', {name: 'Sign out', exact: true}).click();
    await a.waitForFunction(() => !JSON.parse(window.emailSessionAcceptanceState()).signedIn);
    await b.waitForFunction(() => !JSON.parse(window.emailSessionAcceptanceState()).signedIn);
    await a.getByRole('textbox', {name: 'Email address', exact: true}).waitFor();
    assert.equal(await a.getByRole('heading', {name: 'Check your email', exact: true}).count(), 0);
    assert.equal(await a.evaluate(() => localStorage.getItem('flutter.specimen.emailLink.email')), null);
    await a.reload();
    await a.getByRole('textbox', {name: 'Email address', exact: true}).waitFor();
    assert.equal(await a.getByRole('heading', {name: 'Check your email', exact: true}).count(), 0);
    assert.equal((await state(a)).signedIn, false);
    const blockedPaths = [...new Set(rejected)];
    // google_sign_in_web registers its public GIS script even though this
    // fixture never invokes that provider. Keep the request blocked; any other
    // unexpected remote request is a failure, including production Auth APIs.
    assert.deepEqual(blockedPaths.filter(path => path !== 'https://accounts.google.com/gsi/client'), []);
    const report = {
      status: 'passed', project, origin: origin.origin,
      evidence: 'isolated Chrome plus real Firebase Auth emulator and real app routing; Firebase built-in email-link flow in the emulator and synthetic collection data',
      checks: {originalTabAuthenticated: true, sameUidBothTabs: true,
        originalIntendedRoutePreserved: true, signOutSynchronized: true,
        staleSentStateCleared: true, reloadRemainsSignedOut: true,
        dispatchedProductionAuthRequests: 0},
      blockedProductionOriginAttempts: blockedPaths.map(path => ({
        origin: 'https://accounts.google.com', path: '/gsi/client',
        category: 'Google Identity Services static SDK auto-registration',
        attempts: rejected.filter(value => value === path).length,
        outcome: 'blocked before network dispatch',
      })),
    };
    if (output) await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
  } catch (error) {
    for (const page of browser.contexts().flatMap(context => context.pages())) {
      console.error(await page.evaluate(() => ({
        route: location.hash,
        state: typeof window.emailSessionAcceptanceState === 'function'
          ? JSON.parse(window.emailSessionAcceptanceState()) : null,
        text: document.body.innerText.slice(0, 1600),
      })));
    }
    throw error;
  } finally {
    await browser.close();
  }
})().catch(error => {
  // Playwright call logs can contain entered values; all inputs here are fixed
  // synthetic test data. Never add production credentials to this harness.
  console.error(error);
  process.exitCode = 1;
});
