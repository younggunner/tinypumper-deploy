// Greg, 2026-10-18: remove anything Cometly. No published page may load the Cometly
// tracker; /approved keeps its LinkedIn Insight and Calendly scripts.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');

function htmlFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => {
    if (e.name.startsWith('.') || e.name === 'node_modules') return [];
    const p = path.join(dir, e.name);
    return e.isDirectory() ? htmlFiles(p) : e.name.endsWith('.html') ? [p] : [];
  });
}

test('no page loads the Cometly tracker', () => {
  const hits = htmlFiles(root).filter(f => /cometlytrack\.com/i.test(fs.readFileSync(f, 'utf8')));
  assert.deepEqual(hits.map(f => path.relative(root, f)), []);
});

test('/approved keeps LinkedIn Insight and Calendly', () => {
  const html = fs.readFileSync(path.join(root, 'approved/index.html'), 'utf8');
  assert.match(html, /snap\.licdn\.com\/li\.lms-analytics\/insight\.min\.js/);
  assert.match(html, /assets\.calendly\.com/);
});
