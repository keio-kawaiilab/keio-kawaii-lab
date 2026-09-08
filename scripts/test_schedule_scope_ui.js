const fs = require('fs');

const page = fs.readFileSync('schedule.html', 'utf8');
function check(condition, message) {
  if (!condition) throw new Error(message);
}

check(/class="scope-btn active"[^>]+data-scope="kawaii-lab"/.test(page), 'hosted scope must be the default button');
check(/data-scope="all"/.test(page), 'external-inclusive button is missing');
check(/selectedScope='kawaii-lab'/.test(page), 'runtime default scope is not hosted');
check(/match\(e,selected\)&&scopeMatch\(e\)/.test(page), 'calendar render does not enforce scope');
check(/scope-badge">外部出演/.test(page), 'external card badge is missing');
check(/start=moment\(o\.applyStart,false\),end=moment\(o\.applyEnd,true\),ended=!!end&&end<now/.test(page), 'ticket start/end moments are not compared with the current time');
check(/scheduled=!missingStart&&!!start&&start>now/.test(page), 'future ticket receptions are not detected');
check(/open=!missingStart&&!ended&&!scheduled/.test(page), 'open ticket state ignores ended or future receptions');
check(/state=ended\?'受付終了':missingStart\?'開始日時未取得':scheduled\?'受付予定':'受付中'/.test(page), 'ticket reception state labels are incomplete');
check(/detailOnly=ended\|\|missingStart/.test(page), 'ended or unknown-start receptions still expose an application CTA');
check(/sale-state ended">受付終了/.test(page), 'server-rendered cards do not expose an ended reception state');
check(/data-action-mode="detail"/.test(page), 'server-rendered ended/unknown receptions do not use detail-only links');
check(!/申込開始開始日時未取得/.test(page), 'duplicate missing-start wording remains');
check(/exactEnd&&exactEnd<now/.test(page), 'expired same-day calendar bands are not hidden');

const snapshotMatch = page.match(/<script id="snapshot-data" type="application\/json">([\s\S]*?)<\/script>/);
check(snapshotMatch, 'snapshot JSON is missing');
const snapshot = JSON.parse(snapshotMatch[1]);
check(snapshot.events.some(event => event.eventScope === 'kawaii-lab'), 'snapshot has no hosted events');
check(snapshot.events.some(event => event.eventScope === 'external'), 'snapshot has no external events');

const cardsMatch = page.match(/<div class="cards" id="cards">([\s\S]*?)<\/div>\s*<script id="snapshot-data"/);
check(cardsMatch, 'server-rendered cards are missing');
check(!/data-scope="external"/.test(cardsMatch[1]), 'default server-rendered cards leaked an external event');

console.log('Schedule scope UI tests passed');
