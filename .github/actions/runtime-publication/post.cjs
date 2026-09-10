'use strict';
// Separate entrypoint: missing state can NEVER fall through into authentication.
const { cleanupOwned } = require('./index.cjs');
try {
  cleanupOwned(process.env.STATE_owned_directory, process.env);
} catch {
  process.stderr.write('Owned local publication cleanup could not be verified.\n');
  process.exitCode = 1;
}
