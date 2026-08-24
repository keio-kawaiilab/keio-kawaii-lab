#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const page = fs.readFileSync('schedule.html', 'utf8');
const scripts = [...page.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
let source = scripts.find((script) => script.includes("(function(){'use strict';"));
assert(source, 'schedule inline script not found');
source = source.replace(
  /\}\)\(\);\s*$/,
  "globalThis.__scheduleTest={prepare:prepare,groupedApplicationBands:groupedApplicationBands};})();",
);

function element() {
  return {
    appendChild() {},
    classList: { add() {}, remove() {}, toggle() {} },
    innerHTML: '',
    style: {},
    textContent: '',
  };
}

const elements = new Map([
  ['snapshot-data', { textContent: '{"events":[]}' }],
  ['calendar', element()],
  ['range', element()],
  ['prev', element()],
  ['next', element()],
  ['cards', element()],
  ['summary', element()],
  ['status', element()],
]);
const context = {
  console,
  Date,
  encodeURIComponent,
  setTimeout() {},
  document: {
    createElement: element,
    getElementById(id) { return elements.get(id) || element(); },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  },
  window: { matchMedia() { return { matches: false }; } },
  fetch() { return Promise.reject(new Error('disabled in unit test')); },
};
context.globalThis = context;
vm.runInNewContext(source, context);

const common = {
  group: 'CANDY TUNE',
  title: 'CANDY TUNE JAPAN TOUR 2099',
  ticketType: 'プレオーダー受付',
  applyStart: '2099-08-01T12:00',
  applyEnd: '2099-08-10T23:59',
  applicationWindowVerified: true,
  applicationStatus: 'open',
};
const events = [
  { ...common, id: 'e1', ticketProvider: 'eplus', sourceType: 'eplus', eventDate: '2099-10-01', venue: '新潟県 新潟県民会館', url: 'https://eplus.jp/e1' },
  { ...common, id: 'e2', ticketProvider: 'eplus', sourceType: 'eplus', eventDate: '2099-10-02', venue: '福島県 けんしん郡山文化センター', url: 'https://eplus.jp/e2' },
  { ...common, id: 'l1', ticketProvider: 'lawson', sourceType: 'lawson', eventDate: '2099-10-01', venue: '新潟県 新潟県民会館', url: 'https://l-tike.com/l1' },
  { ...common, id: 'l2', ticketProvider: 'lawson', sourceType: 'lawson', eventDate: '2099-10-02', venue: '福島県 けんしん郡山文化センター', url: 'https://l-tike.com/l2' },
  { ...common, id: 'e3', ticketProvider: 'eplus', sourceType: 'eplus', applyEnd: '2099-08-11T23:59', eventDate: '2099-10-03', venue: '宮城県 仙台サンプラザホール', url: 'https://eplus.jp/e3' },
];

const grouped = context.__scheduleTest.groupedApplicationBands(context.__scheduleTest.prepare(events));
assert.strictEqual(grouped.length, 3, 'same provider and same window should share one band');
const eplus = grouped.find((item) => item.event.ticketProvider === 'eplus' && item.events.length === 2);
const lawson = grouped.find((item) => item.event.ticketProvider === 'lawson');
assert(eplus, 'eplus windows were not grouped');
assert(lawson, 'lawson windows were not grouped');
assert.strictEqual(eplus.location, '新潟・福島');
assert.strictEqual(lawson.location, '新潟・福島');
assert.strictEqual(lawson.events.length, 2);
console.log('Schedule band grouping tests passed');
