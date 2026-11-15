import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const vendor = new URL('../docs/vendor/three/', import.meta.url);

test('the preview uses the pinned Three.js bundle and keeps it within the byte budget', () => {
  const manifest = JSON.parse(readFileSync(new URL('origin.json', vendor), 'utf8'));
  const bundle = readFileSync(new URL('three-wmm.mjs', vendor));
  assert.equal(manifest.version, '0.187.0');
  assert.equal(bundle.byteLength, manifest.bundle.bytes);
  assert.ok(bundle.byteLength < 600_000);
  assert.equal(createHash('sha256').update(bundle).digest('hex'), manifest.bundle.sha256);
  assert.match(readFileSync(new URL('LICENSE', vendor), 'utf8'), /Permission is hereby granted/);
  const page = readFileSync(new URL('../docs/index.html', import.meta.url), 'utf8');
  assert.match(page, /src="wmm-hero.mjs"/);
  assert.match(page, /src="images\/wmm-console.webp"/);
});
