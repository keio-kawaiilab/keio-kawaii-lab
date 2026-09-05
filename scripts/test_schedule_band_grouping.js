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
assert(source.includes("data-band-apply-start"), 'application bands must expose their exact start for safe deduplication');
assert(source.includes("data-band-group"), 'application bands must expose their group for safe deduplication');
source = source.replace(
  /\}\)\(\);\s*$/,
  "globalThis.__scheduleTest={prepare:prepare,groupedApplicationBands:groupedApplicationBands,eventKind:eventKind,specialHtml:specialHtml,performanceModels:performanceModels,performanceKey:performanceKey};})();",
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

const sweetTourUrl = 'https://sweetsteady.asobisystem.com/feature/sweetsteady_japanhalltour2099';
const sweetTourCommon = {
  group: 'SWEET STEADY',
  ticketType: 'FC先行',
  applyStart: '2099-08-23T20:00',
  applyEnd: '2099-09-13T23:59',
  applicationWindowVerified: true,
  applicationStatus: 'open',
  ticketProvider: 'official',
  sourceType: 'auto',
  officialTourUrl: sweetTourUrl,
};
const sweetTitleVariants = [
  { ...sweetTourCommon, id: 'sweet-derived', title: '「SWEET STEADY JAPAN TOUR 2099 -WINTER-」 開催決定！FC先行開始！', eventDate: '2099-11-13', venue: '神奈川県 厚木市文化会館 大ホール', url: sweetTourUrl },
  { ...sweetTourCommon, id: 'sweet-auto', title: '2099.08.23 「SWEET STEADY JAPAN TOUR 2099 -WINTER-」 開催決定！FC先行開始！', eventDate: '2099-11-13', venue: '神奈川県 厚木市文化会館 大ホール', url: sweetTourUrl },
];
const sweetGrouped = context.__scheduleTest.groupedApplicationBands(context.__scheduleTest.prepare(sweetTitleVariants));
assert.strictEqual(sweetGrouped.length, 1, 'same official FC tour and same application window must render one band even when source titles have date-prefix variants');
assert.strictEqual(sweetGrouped[0].events.length, 2, 'both duplicate official FC source rows must be represented by the one consolidated band');

const otherSweetTourUrl = 'https://sweetsteady.asobisystem.com/feature/a_different_tour';
const otherSweetTour = { ...sweetTourCommon, id: 'sweet-other-tour', title: 'SWEET STEADY JAPAN TOUR 2099 -WINTER-', officialTourUrl: otherSweetTourUrl, eventDate: '2099-11-14', venue: '神奈川県 別会場', url: otherSweetTourUrl };
const separateSweetGrouped = context.__scheduleTest.groupedApplicationBands(context.__scheduleTest.prepare(sweetTitleVariants.concat([otherSweetTour])));
assert.strictEqual(separateSweetGrouped.length, 2, 'different tours must remain separate even when provider and application window match');

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

const sameBenefitPerformance = [
  {
    id: 'benefit-sukisuki',
    group: 'FRUITS ZIPPER',
    title: 'FRUITS ZIPPER 大特典会',
    displayTitle: 'FRUITS ZIPPER 大特典会',
    eventCategory: 'large-benefit',
    eventDate: '2099-09-06',
    venue: 'ベルサール汐留',
    startTime: '10:00',
    ticketProvider: 'sukisuki',
    ticketType: 'FC限定・対象商品応募',
    applyStart: '2099-08-25T21:00',
    applyEnd: '2099-08-26T23:59',
    applicationStatus: 'open',
    url: 'https://sukisuki-shop.com/goods/1',
  },
  {
    id: 'benefit-hmv',
    group: 'FRUITS ZIPPER',
    title: 'FRUITS ZIPPER 大特典会',
    displayTitle: 'FRUITS ZIPPER 大特典会',
    eventCategory: 'large-benefit',
    eventDate: '2099-09-06',
    venue: 'ベルサール汐留',
    startTime: '11:20',
    ticketProvider: 'hmv',
    ticketType: '対象商品予約（参加権付き）',
    applyStart: '2099-08-25T21:00',
    applyEnd: '2099-08-27T11:59',
    applicationStatus: 'open',
    url: 'https://www.hmv.co.jp/product/detail/1',
  },
];
const benefitModels = context.__scheduleTest.performanceModels(context.__scheduleTest.prepare(sameBenefitPerformance));
assert.strictEqual(benefitModels.length, 1, 'same special event must render as one performance even when sale rows have different start times');
assert.strictEqual(benefitModels[0].offers.length, 2, 'all sales channels must remain available inside the consolidated special-event card');
assert.strictEqual(context.__scheduleTest.performanceKey(sameBenefitPerformance[0], { date: '2099-09-06', venue: 'ベルサール汐留', startTime: '10:00' }), context.__scheduleTest.performanceKey(sameBenefitPerformance[1], { date: '2099-09-06', venue: 'ベルサール汐留', startTime: '11:20' }));

const dedupeSource = fs.readFileSync('schedule-shared-mark-dedupe.js', 'utf8');

function fakeClassList(values) {
  const list = values.slice();
  list.add = function add(name) {
    if (!list.includes(name)) list.push(name);
  };
  list.remove = function remove(name) {
    const index = list.indexOf(name);
    if (index >= 0) list.splice(index, 1);
  };
  return list;
}

function fakeBand({ group, groupClass, applyStart }) {
  const attributes = {
    'data-band-group': group,
    'data-band-provider': 'tower',
    'data-band-ticket-type': '対象商品予約（参加権付き・先着／受付）',
    'data-band-apply-start': applyStart,
    'data-band-apply-end': '2099-09-04T23:59',
  };
  return {
    removed: false,
    title: `${group} 大特典会｜タワーレコード`,
    classList: fakeClassList(['mark', 'band', groupClass, 'special-event']),
    style: { left: 'calc(28.5714285714% + 2px)', width: 'calc(42.8571428571% - 4px)' },
    getAttribute(name) { return attributes[name] || null; },
    setAttribute(name, value) { attributes[name] = String(value); },
    querySelector(selector) {
      if (selector === 'strong') return { textContent: '大特典会' };
      if (selector === 'span') return { textContent: 'タワーレコード｜対象商品予約（参加権付き・先着／受付）｜2099/9/4 23:59まで' };
      return null;
    },
    remove() { this.removed = true; },
  };
}

function runSharedMarkDedupe(marks) {
  const week = {
    clientWidth: 700,
    style: {},
    querySelectorAll(selector) {
      if (selector === '.band') return marks.filter((mark) => !mark.removed);
      return [];
    },
  };
  const calendar = {
    querySelectorAll(selector) { return selector === '.week' ? [week] : []; },
  };
  function MutationObserver() {}
  MutationObserver.prototype.observe = function observe() {};
  vm.runInNewContext(dedupeSource, {
    document: { getElementById(id) { return id === 'calendar' ? calendar : null; } },
    MutationObserver,
    window: {
      addEventListener() {},
      matchMedia() { return { matches: false }; },
      setTimeout(callback) { callback(); },
    },
  });
  return marks.filter((mark) => !mark.removed);
}

const candyBand = fakeBand({ group: 'CANDY TUNE', groupClass: 'g-CANDY', applyStart: '2099-09-02T20:00' });
const sweetBand = fakeBand({ group: 'SWEET STEADY', groupClass: 'g-SWEET', applyStart: '2099-09-02T23:00' });
let remaining = runSharedMarkDedupe([candyBand, sweetBand]);
assert.strictEqual(remaining.length, 2, 'different groups must keep separate application bands');
assert(candyBand.classList.includes('g-CANDY'), 'CANDY TUNE band must keep its group color');
assert(sweetBand.classList.includes('g-SWEET'), 'SWEET STEADY band must keep its group color');
assert(!candyBand.classList.includes('g-LAB'), 'CANDY TUNE band must not become a joint black band');

const earlyCandyBand = fakeBand({ group: 'CANDY TUNE', groupClass: 'g-CANDY', applyStart: '2099-09-02T20:00' });
const lateCandyBand = fakeBand({ group: 'CANDY TUNE', groupClass: 'g-CANDY', applyStart: '2099-09-02T23:00' });
remaining = runSharedMarkDedupe([earlyCandyBand, lateCandyBand]);
assert.strictEqual(remaining.length, 2, 'different exact start times must not be deduplicated');

const duplicateCandyA = fakeBand({ group: 'CANDY TUNE', groupClass: 'g-CANDY', applyStart: '2099-09-02T20:00' });
const duplicateCandyB = fakeBand({ group: 'CANDY TUNE', groupClass: 'g-CANDY', applyStart: '2099-09-02T20:00' });
remaining = runSharedMarkDedupe([duplicateCandyA, duplicateCandyB]);
assert.strictEqual(remaining.length, 1, 'true same-group duplicates should still collapse');
assert(duplicateCandyA.classList.includes('g-CANDY'), 'deduplicated same-group band must keep its color');
assert(!duplicateCandyA.title.includes('複数グループ共通'), 'same-group deduplication must not claim a joint event');

console.log('Schedule band grouping tests passed');
