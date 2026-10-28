// Run with: node --test tests/test_section_jumps.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'app.py'), 'utf8');
const script = source.match(/_SECTION_JUMP_JS = r"""([\s\S]*?)"""/)[1];

function fixture() {
  let now = 0, serial = 0;
  const timers = new Map(), listeners = new Map(), targets = new Map();
  const images = [];
  const main = {scrollTop: 0, scrollHeight: 10000, clientHeight: 800,
    getBoundingClientRect: () => ({top: 0}),
    querySelectorAll: () => images,
    scrollTo({top, behavior}) { assert.equal(behavior, 'instant'); this.scrollTop = top; }};
  const doc = {
    getElementById: id => targets.get(id),
    querySelector: () => main,
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(fn);
    },
    removeEventListener(type, fn) { listeners.get(type)?.delete(fn); },
  };
  const outer = {document: doc, Date: {now: () => now},
    location: {pathname: '/india', href: 'https://example.test/india', hash: ''},
    history: {pushState(_, __, url) {
      outer.location.href = String(url); outer.location.hash = url.hash;
    }},
    setInterval(fn) { timers.set(++serial, fn); return serial; },
    clearInterval(id) { timers.delete(id); },
  };
  function run() { vm.runInNewContext(script, {window: {parent: outer}, URL}); }
  function emit(type, target, extra = {}) {
    const event = {target, button: 0, preventDefault() { this.prevented = true; }, ...extra};
    for (const fn of [...(listeners.get(type) || [])]) fn(event);
    return event;
  }
  function link(id) {
    const attrs = {href: '#' + id};
    return {getAttribute: key => attrs[key], setAttribute: (key, value) => { attrs[key] = value; },
      removeAttribute: key => { delete attrs[key]; }};
  }
  function click(id, extra = {}) {
    const item = link(id);
    item.closest = selector => selector.startsWith('.tab-jump') ? item : null;
    return {item, event: emit('click', item, extra)};
  }
  function advance(ms) {
    for (let elapsed = 0; elapsed < ms; elapsed += 100) {
      now += 100;
      for (const fn of [...timers.values()]) fn();
    }
  }
  function target(id, y) {
    const element = {y, getBoundingClientRect() { return {top: this.y - main.scrollTop}; }};
    targets.set(id, element); return element;
  }
  run();
  return {outer, main, timers, listeners, images, run, click, advance, target, emit};
}

test('early click survives a long page build and preserves the fragment', () => {
  const f = fixture(), {item, event} = f.click('india-equity-markets');
  assert.equal(event.prevented, true);
  f.advance(30000);
  assert.equal(f.main.scrollTop, 0);
  assert.equal(item.getAttribute('aria-busy'), 'true');
  f.target('india-equity-markets', 4200);
  f.advance(100);
  assert.equal(f.main.scrollTop, 4128);
  assert.equal(f.outer.location.hash, '#india-equity-markets');
  f.advance(1600);
  assert.equal(f.timers.size, 0);
  assert.equal(item.getAttribute('aria-busy'), undefined);
});

test('latest click wins and slow images above the target retain alignment', () => {
  const f = fixture();
  const first = f.click('india-inflation').item;
  f.click('india-equity-markets');
  assert.equal(first.getAttribute('aria-busy'), undefined);
  const target = f.target('india-equity-markets', 4000);
  const image = {complete: false, compareDocumentPosition: () => 4};
  f.images.push(image);
  f.advance(5000);
  assert.equal(f.timers.size, 1);
  target.y = 4800;
  f.advance(100);
  assert.equal(f.main.scrollTop, 4728);
  image.complete = true;
  f.advance(1600);
  assert.equal(f.timers.size, 0);
});

test('manual input cancels both waiting and alignment', () => {
  for (const [type, extra] of [['wheel', {}], ['touchstart', {}], ['keydown', {key: 'PageDown'}], ['pointerdown', {}]]) {
    const f = fixture();
    f.click('india-equity-markets');
    f.emit(type, {closest: () => null}, extra);
    f.target('india-equity-markets', 5000);
    f.advance(1000);
    assert.equal(f.main.scrollTop, 0);
    assert.equal(f.timers.size, 0);
  }
});

test('modified clicks retain native behavior; navigation and reinstall clean up', () => {
  const f = fixture();
  assert.equal(f.click('india-equity-markets', {ctrlKey: true}).event.prevented, undefined);
  assert.equal(f.timers.size, 0);
  f.click('india-equity-markets');
  f.outer.location.pathname = '/world';
  f.advance(100);
  assert.equal(f.timers.size, 0);
  f.click('world-growth');
  f.emit('click', {closest: selector => selector.startsWith('[class*="st-key-ehnav-') ? {} : null});
  assert.equal(f.timers.size, 0);
  f.click('world-growth');
  f.run();
  assert.equal(f.timers.size, 0);
  assert.equal(f.listeners.get('click').size, 2);
  assert.equal(f.listeners.get('wheel').size, 1);
});

test('missing targets time out and short pages clamp to their scroll limit', () => {
  const f = fixture();
  f.click('missing'); f.advance(120100);
  assert.equal(f.timers.size, 0);
  f.main.scrollHeight = 1000;
  f.target('last-section', 900); f.click('last-section');
  assert.equal(f.main.scrollTop, 200);
});
