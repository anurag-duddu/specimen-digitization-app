'use strict';
// The runner supplies Node24. This adapter never requests Google credentials.
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const PREFIX = 'specimen-publication-';

function need(condition) {
  if (!condition) throw new Error('Invalid private publication state');
}
function syncDirectory(directory) {
  const fd = fs.openSync(directory, fs.constants.O_RDONLY);
  try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
}
function owner(env) {
  need(/^[1-9][0-9]*$/.test(env.GITHUB_RUN_ID || '') && /^[1-9][0-9]*$/.test(env.GITHUB_RUN_ATTEMPT || ''));
  return { version: 1, run_id: env.GITHUB_RUN_ID, attempt: env.GITHUB_RUN_ATTEMPT };
}
function createOwned(env) {
  const parent = fs.realpathSync(env.RUNNER_TEMP);
  need(!/[\r\n]/.test(parent) && env.GITHUB_STATE);
  const directory = fs.mkdtempSync(path.join(parent, PREFIX));
  fs.chmodSync(directory, 0o700);
  const fd = fs.openSync(path.join(directory, 'owner.json'), 'wx', 0o600);
  try {
    fs.writeFileSync(fd, JSON.stringify(owner(env)) + '\n');
    fs.fsyncSync(fd);
  } finally { fs.closeSync(fd); }
  syncDirectory(directory);
  syncDirectory(parent);
  // This is the only runner state. Persist it before any auth child can start.
  const state = fs.openSync(env.GITHUB_STATE, 'a');
  try {
    fs.writeFileSync(state, `owned_directory=${directory}\n`);
    fs.fsyncSync(state);
  } finally { fs.closeSync(state); }
  return directory;
}
function cleanupOwned(directory, env) {
  if (!directory) return;
  const parent = fs.realpathSync(env.RUNNER_TEMP);
  need(path.dirname(directory) === parent && path.basename(directory).startsWith(PREFIX));
  if (!fs.existsSync(directory)) return;
  const info = fs.lstatSync(directory);
  need(info.isDirectory() && !info.isSymbolicLink() && info.uid === process.getuid() && (info.mode & 0o077) === 0);
  const marker = path.join(directory, 'owner.json');
  const mi = fs.lstatSync(marker);
  need(mi.isFile() && !mi.isSymbolicLink() && mi.uid === process.getuid() && mi.size < 4096 && (mi.mode & 0o077) === 0);
  const actual = JSON.parse(fs.readFileSync(marker, 'utf8'));
  need(JSON.stringify(actual) === JSON.stringify(owner(env)));
  // Fixed local files only; reject unbounded trees. Never follow child symlinks.
  let count = 0;
  function check(current, depth) {
    need(depth <= 3);
    for (const name of fs.readdirSync(current)) {
      need(++count <= 32);
      const entry = path.join(current, name);
      const st = fs.lstatSync(entry);
      if (st.isDirectory() && !st.isSymbolicLink()) check(entry, depth + 1);
    }
  }
  check(directory, 0);
  fs.rmSync(directory, { recursive: true, force: true, maxRetries: 0 });
}
async function main() {
  need(Number(process.versions.node.split('.')[0]) === 24);
  const root = path.resolve(__dirname, '../../..');
  need(fs.realpathSync(process.env.GITHUB_WORKSPACE) === root);
  const owned = createOwned(process.env);
  const childEnv = { ...process.env };
  delete childEnv.NODE_OPTIONS;
  delete childEnv.NODE_PATH;
  const args = [path.join(root, 'scripts/ci/release_publication_deadline.py'),
    '--node', process.execPath, '--auth-source', path.join(root, '.release-tools/google-auth'),
    '--packet', process.env.INPUT_PACKET, '--role', process.env.INPUT_ROLE,
    '--output', process.env.INPUT_OUTPUT, '--owned', owned];
  const child = spawn(path.join(root, '.venv/bin/python'), args, { cwd: root, env: childEnv, stdio: 'inherit' });
  const forward = () => child.kill('SIGTERM');
  process.on('SIGINT', forward);
  process.on('SIGTERM', forward);
  try {
    const code = await new Promise((resolve, reject) => {
      child.once('error', reject);
      child.once('exit', (status) => resolve(status === null ? 1 : status));
    });
    process.exitCode = code;
  } finally {
    process.removeListener('SIGINT', forward);
    process.removeListener('SIGTERM', forward);
    cleanupOwned(owned, process.env);
  }
}
module.exports = { createOwned, cleanupOwned };
if (require.main === module) {
  main().catch(() => { process.stderr.write('Supervised publication failed; reconcile retained evidence.\n'); process.exitCode = 1; });
}
