import assert from 'node:assert/strict';
import test from 'node:test';
import { isLocalClientOrigin } from './src/policy.mjs';

test('downloaded clients only receive CORS access from local HTTP origins', () => {
  assert.equal(isLocalClientOrigin('http://localhost:15174'), true);
  assert.equal(isLocalClientOrigin('http://127.0.0.1:5173'), true);
  for (const value of ['null', 'https://evil.com', 'http://localhost.evil.com', 'http://localhost:15174@evil.com']) assert.equal(isLocalClientOrigin(value), false);
});
