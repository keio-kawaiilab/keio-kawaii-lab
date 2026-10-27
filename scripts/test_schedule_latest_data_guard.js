const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('schedule.html', 'utf8');
const helperStart = html.indexOf('function hasRequiredCandyTuneTour(data)');
const helperEnd = html.indexOf("fetchLatestScheduleData('./data/live-events.json", helperStart);
assert(helperStart >= 0 && helperEnd > helperStart, 'browser tour-integrity helper is missing');

const RealDate = Date;
class FixedDate extends RealDate {
  static now() { return RealDate.parse('2026-10-27T00:00:00+09:00'); }
}
const context = {Date: FixedDate};
vm.createContext(context);
vm.runInContext(html.slice(helperStart, helperEnd), context);
const validate = context.hasRequiredCandyTuneTour;
assert.strictEqual(typeof validate, 'function');

const payload = JSON.parse(fs.readFileSync('data/live-events.json', 'utf8'));
assert.strictEqual(validate(payload), true, 'current canonical JSON must pass the browser guard');

const futureOnly = JSON.parse(JSON.stringify(payload));
const futureRows = Array.isArray(futureOnly.publicEvents) ? futureOnly.publicEvents : futureOnly.events;
for (const event of futureRows) {
  if (!event || event.group !== 'CANDY TUNE') continue;
  if (String(event.eventDate || '').slice(0, 10) < '2026-10-27') event.eventDate = null;
  if (Array.isArray(event.eventDates)) {
    event.eventDates = event.eventDates.filter((value) => String(value && typeof value === 'object' ? value.date : value).slice(0, 10) >= '2026-10-27');
  }
  if (Array.isArray(event.schedule)) {
    event.schedule = event.schedule.filter((value) => String(value && value.date || '').slice(0, 10) >= '2026-10-27');
  }
}
assert.strictEqual(validate(futureOnly), true, 'expired tour dates may be pruned from the live JSON');

const missing = JSON.parse(JSON.stringify(payload));
const rows = Array.isArray(missing.publicEvents) ? missing.publicEvents : missing.events;
for (const event of rows) {
  if (!event || event.group !== 'CANDY TUNE') continue;
  if (String(event.eventDate || '').slice(0, 10) === '2026-11-19') event.eventDate = null;
  if (Array.isArray(event.eventDates)) {
    event.eventDates = event.eventDates.filter((value) => String(value && typeof value === 'object' ? value.date : value).slice(0, 10) !== '2026-11-19');
  }
  if (Array.isArray(event.schedule)) {
    event.schedule = event.schedule.filter((value) => String(value && value.date || '').slice(0, 10) !== '2026-11-19');
  }
}
assert.strictEqual(validate(missing), false, 'a JSON payload missing one official tour date must be rejected');

console.log('Latest schedule JSON is accepted with all unfinished CANDY TUNE tour dates');
