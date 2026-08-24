#!/usr/bin/env node
'use strict';

const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const page = fs.readFileSync('schedule.html', 'utf8');
const scripts = [...page.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
let source = scripts.find((script) => script.includes("(function(){'use strict';"));
assert(source, 'schedule inline script not found');
assert(source.includes("cell.textContent=dt<start?'':sd(dt)"), 'calendar dates must always include the month');
assert(source.includes("dateAndTime=performanceDate(m.date)"), 'performance details must include the event date');
assert(source.includes("'時刻未発表'"), 'missing times need an explicit time-only fallback');
assert(source.includes('function initPullRefresh()'), 'touch pull-to-refresh must be initialized');
assert(source.includes("'離して更新'"), 'pull-to-refresh needs a release affordance');
assert(source.includes('window.location.reload()'), 'pull-to-refresh must reload the page');
assert(page.includes('.special-event{background-image:radial-gradient'), 'special-event calendar items need a polka-dot background');
assert(page.includes('.card.release-card,.card.benefit-card{'), 'special-event detail cards need a shared polka-dot treatment');
assert(source.includes("?' special-event':''"), 'release and large-benefit items need the special-event class');
source = source.replace(
  /\}\)\(\);\s*$/,
  "globalThis.__scheduleTest={prepare:prepare,groupedApplicationBands:groupedApplicationBands,eventKind:eventKind,specialHtml:specialHtml};})();",
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

const release = {
  group: 'MORE STAR',
  title: 'MORE STAR リリースイベント',
  eventCategory: 'release-event',
  purchaseMethod: 'アプリで整理券を取得して対象商品を購入',
  ticketIssueMethod: 'KAWAII LAB. STOREアプリ',
  ticketName: '商品購入整理券',
  salesStartTime: '10:00',
  gatheringTime: '13:20',
  product: '通常盤 1,200円',
  numberedCallTimes: [{ numbers: '1〜200番', time: '09:50' }],
  ticketBenefits: ['通常盤1枚でお見送り会参加券1枚'],
};
assert.strictEqual(context.__scheduleTest.eventKind(release), 'release');
const special = context.__scheduleTest.specialHtml(release);
assert(special.includes('参加方法・整理券'));
assert(special.includes('1〜200番'));
assert(special.includes('09:50'));
assert(special.includes('通常盤1枚でお見送り会参加券1枚'));
console.log('Schedule band grouping tests passed');
