import assert from 'node:assert/strict';
const host=process.env.FIREBASE_DATACONNECT_EMULATOR_HOST;
assert.match(host,/^127\.0\.0\.1:\d+$/);
for(let n=0;n<100;n++) {
  try {const r=await fetch(`http://${host}/`);if(r.status===404) process.exit(0);} catch {}
  await new Promise(resolve=>setTimeout(resolve,100));
}
throw new Error('Local SQL Connect emulator did not become ready');
