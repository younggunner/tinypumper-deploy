const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(root, 'assets/js/tp-attr.js'), 'utf8');

function visit(href, previous) {
  let current = new URL(href), cookie = previous ? 'tp_attr=' + encodeURIComponent(JSON.stringify(previous)) : '';
  const handlers = {}, beacons = [];
  const state = { navigation: 'preserved' };
  const window = {
    get location() { return current; }, scrollY: 0, innerHeight: 600,
    addEventListener(name, cb) { handlers[name] = cb; },
    history: { state, replaceState(next, unused, url) { assert.equal(next, state); current = new URL(url); } }
  };
  const document = {
    referrer: '', visibilityState: 'visible',
    get cookie() { return cookie; }, set cookie(v) { cookie = v.split(';')[0]; },
    documentElement: { scrollHeight: 1000 }, body: { scrollHeight: 1000, innerText: 'Product information' },
    addEventListener(name, cb) { handlers[name] = cb; }
  };
  vm.runInNewContext(source, {
    window, document, URL, URLSearchParams, Date, Blob, setInterval() {},
    localStorage: { getItem() { return null; }, setItem() {} },
    navigator: { sendBeacon(url, blob) { beacons.push(blob); return true; } }
  });
  handlers.pagehide();
  return { url: current, attr: JSON.parse(decodeURIComponent(cookie.split('=')[1])), beacons };
}

test('the unchanged printed URL becomes a KIOGA visit and engagement beacon', async () => {
  const result = visit('https://www.tinypumper.com?comet_custom=KIOGA');
  assert.equal(result.url.searchParams.get('utm_source'), 'kioga');
  assert.equal(result.url.searchParams.get('utm_medium'), 'print');
  assert.equal(result.url.searchParams.get('utm_campaign'), 'tp-kioga');
  assert.equal(result.url.searchParams.has('comet_custom'), false);
  assert.equal(result.attr.utm_source, 'kioga');
  const beacon = JSON.parse(await result.beacons[0].text());
  assert.equal(beacon.brand, 'tp');
  assert.equal(beacon.utm_source, 'kioga');
  assert.equal(beacon.utm_campaign, 'tp-kioga');
  assert.equal(beacon.attr_from, 'url');
});

test('existing first touch survives, while the new visit beacon says KIOGA', async () => {
  const result = visit('https://www.tinypumper.com?comet_custom=KIOGA', {
    utm_source: 'google', utm_medium: 'paid-search', utm_campaign: 'tp-search-exact'
  });
  assert.equal(result.attr.utm_source, 'google');
  assert.equal(result.attr.utm_campaign, 'tp-search-exact');
  assert.equal(JSON.parse(await result.beacons[0].text()).utm_source, 'kioga');
});

test('unrelated parameters, hash, case, and history state survive normalization', () => {
  const result = visit('https://www.tinypumper.com/?comet_custom=%20kioga%20&foo=bar#pricing');
  assert.equal(result.attr.utm_source, 'kioga');
  assert.equal(result.url.searchParams.get('foo'), 'bar');
  assert.equal(result.url.hash, '#pricing');
});

test('other publications and direct visits are not guessed to be KIOGA', () => {
  for (const query of ['', '?comet_custom=OTHER', '?comet_custom=KIOGA-OTHER']) {
    const url = 'https://www.tinypumper.com/' + query;
    const result = visit(url);
    assert.equal(result.url.href, url);
    assert.equal(result.attr.utm_source, undefined);
  }
});

test('explicit attribution and click IDs are never replaced or mixed', () => {
  for (const query of ['utm_source=facebook&utm_medium=paid-social', 'utm_campaign=another',
    'utm_source=', 'utm_content=creative', 'utm_id=42', 'gclid=click', 'fbclid=click',
    'msclkid=click', 'dclid=click', 'wbraid=click', 'gbraid=click']) {
    const url = 'https://www.tinypumper.com/?comet_custom=KIOGA&' + query;
    const result = visit(url);
    assert.equal(result.url.href, url);
    assert.notEqual(result.attr.utm_source, 'kioga');
  }
});

test('revisiting an already normalized URL is idempotent', () => {
  const first = visit('https://www.tinypumper.com?comet_custom=KIOGA');
  assert.equal(visit(first.url.href).url.href, first.url.href);
});

test('homepage runs attribution once, synchronously, before analytics', () => {
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const scripts = [...html.matchAll(/<script\b[^>]*>[\s\S]*?<\/script>/g)].map(m => m[0]);
  assert.equal(scripts.filter(s => s.includes('/assets/js/tp-attr.js')).length, 1);
  assert.match(scripts[0], /^<script src="\/assets\/js\/tp-attr.js"><\/script>$/);
});
