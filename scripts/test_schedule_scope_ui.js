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

check(/バックアップを表示中。最新データを確認しています/.test(page), 'initial backup/loading status is missing');
check(/function fetchLatestScheduleData\(url,timeoutMs\)/.test(page), 'latest schedule data fetch has no bounded loading helper');
check(/fetchLatestScheduleData\('\.\/data\/live-events\.json\?ts='\+Date\.now\(\),10000\)/.test(page), 'latest schedule data fetch is not capped at 10 seconds');
check(!/fetch\('\.\/data\/live-events\.json\?ts='\+Date\.now\(\),\{cache:'no-store'\}\)/.test(page), 'legacy unbounded latest-data fetch remains');
check(/textContent='最終更新: '\+\(data\.checkedAt\|\|data\.updatedAt\|\|'不明'\)/.test(page), 'successful latest-data load does not clear the checking status');
check(/最新JSONの読込に失敗したため、自動生成済みバックアップを表示しています/.test(page), 'failed or timed-out latest-data load has no terminal fallback status');

const snapshotMatch = page.match(/<script id="snapshot-data" type="application\/json">([\s\S]*?)<\/script>/);
check(snapshotMatch, 'snapshot JSON is missing');
const snapshot = JSON.parse(snapshotMatch[1]);
check(snapshot.events.some(event => event.eventScope === 'kawaii-lab'), 'snapshot has no hosted events');
check(snapshot.events.some(event => event.eventScope === 'external'), 'snapshot has no external events');

const kawacolle = snapshot.events.filter(event => {
  const title = [event.eventTitle, event.displayTitle, event.title].filter(Boolean).join(' ');
  return String(event.eventDate || '').slice(0, 10) === '2026-10-12' && /COLLECTION produced by TGC/i.test(title);
});
check(kawacolle.length === 1, `2026-10-12 Kawacolle must be one public event, got ${kawacolle.length}`);
check(kawacolle[0].eventScope === 'external', '2026-10-12 Kawacolle is incorrectly classified as KAWAII LAB.-hosted');
const expectedKawacolleParticipants = ['FRUITS ZIPPER', 'CANDY TUNE', 'SWEET STEADY', 'CUTIE STREET', 'MORE STAR', 'KAWAII LAB. SOUTH'];
check(expectedKawacolleParticipants.every(group => (kawacolle[0].participants || []).includes(group)), '2026-10-12 Kawacolle lost participating groups while deduplicating');
check(new Set(kawacolle[0].participants || []).size === 6, '2026-10-12 Kawacolle participant list is not the six announced groups');

const liveOrTreat = snapshot.events.filter(event => {
  const title = [event.eventTitle, event.displayTitle, event.title].filter(Boolean).join(' ');
  return String(event.eventDate || '').slice(0, 10) === '2026-10-17' && /Live or Treat 2026/i.test(title);
});
check(liveOrTreat.length === 1, `2026-10-17 Live or Treat must be one public event, got ${liveOrTreat.length}`);
check(liveOrTreat[0].eventScope === 'external', '2026-10-17 Live or Treat is incorrectly classified as KAWAII LAB.-hosted');

const cardsMatch = page.match(/<div class="cards" id="cards">([\s\S]*?)<\/div>\s*<script id="snapshot-data"/);
check(cardsMatch, 'server-rendered cards are missing');
check(!/data-scope="external"/.test(cardsMatch[1]), 'default server-rendered cards leaked an external event');
check(!/COLLECTION produced by TGC/i.test(cardsMatch[1]), '2026-10-12 Kawacolle leaked into the hosted-only default cards');
check(!/Live or Treat 2026/i.test(cardsMatch[1]), '2026-10-17 Live or Treat leaked into the hosted-only default cards');

console.log('Schedule scope UI tests passed');
