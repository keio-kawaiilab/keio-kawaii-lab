const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('schedule.html', 'utf8');
const helperStart = html.indexOf('function hasRequiredCandyTuneTour(data)');
const helperEnd = html.indexOf("fetchLatestScheduleData('./data/live-events.json", helperStart);
assert(helperStart >= 0 && helperEnd > helperStart, 'browser tour-integrity helper is missing');

const context = {};
vm.createContext(context);
vm.runInContext(html.slice(helperStart, helperEnd), context);
const validate = context.hasRequiredCandyTuneTour;
assert.strictEqual(typeof validate, 'function');

const payload = JSON.parse(fs.readFileSync('data/live-events.json', 'utf8'));
assert.strictEqual(validate(payload), true, 'current canonical JSON must pass the browser guard');

const missing = JSON.parse(JSON.stringify(payload));
const rows = Array.isArray(missing.publicEvents) ? missing.publicEvents : missing.events;
for (const event of rows) {
  if (!event || event.group !== 'CANDY TUNE') continue;
  if (String(event.eventDate || '').slice(0, 10) === '2026-09-19') event.eventDate = null;
  if (Array.isArray(event.eventDates)) {
    event.eventDates = event.eventDates.filter((value) => String(value && typeof value === 'object' ? value.date : value).slice(0, 10) !== '2026-09-19');
  }
  if (Array.isArray(event.schedule)) {
    event.schedule = event.schedule.filter((value) => String(value && value.date || '').slice(0, 10) !== '2026-09-19');
  }
}
assert.strictEqual(validate(missing), false, 'a JSON payload missing one official tour date must be rejected');

console.log('Latest schedule JSON is accepted only with all 23 CANDY TUNE tour dates');
