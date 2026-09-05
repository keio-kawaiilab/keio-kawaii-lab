from pathlib import Path

fix = Path("scripts/fix_schedule_shell.py")
text = fix.read_text(encoding="utf-8")

if "PERFORMANCE_RECONCILE_JS" not in text:
    marker = "\n\n\ndef canonicalize_public_data() -> dict:\n"
    helper = r'''

PERFORMANCE_RECONCILE_JS = (
    "function performanceTimeMatchKeys(e,o){var day=String((o&&o.date)||e.eventDate||'').slice(0,10),venue=performanceVenueKey(e,o),base=[String(e.group||''),day,eventKind(e),venue].join('|'),out=[],tour=String(e.officialTourUrl||'').trim().toLowerCase().replace(/[?#].*$/,'').replace(/\\/$/,'');if(tour)out.push(base+'|tour:'+tour);var t=performanceTitleKey(e);if(t)out.push(base+'|title:'+t);return out}"
    "function reconcilePerformanceTimes(all){var tm={},om={};function add(map,k,v){if(!v)return;(map[k]||(map[k]={}))[String(v).replace(/\\s+/g,'')]=1}function vals(map,ks){var x={};ks.forEach(function(k){Object.keys(map[k]||{}).forEach(function(v){x[v]=1})});return Object.keys(x)};"
    "(all||[]).forEach(function(e){occ(e).forEach(function(o){var ks=performanceTimeMatchKeys(e,o),st=String(o.startTime||e.startTime||'').replace(/\\s+/g,''),ot=String(o.openTime||e.openTime||'').replace(/\\s+/g,'');ks.forEach(function(k){add(tm,k,st);add(om,k,ot)})})});"
    "return(all||[]).map(function(e){var c=Object.assign({},e),sched=Array.isArray(e.schedule)?e.schedule:null,suppressed=false;if(sched){var ns=[];sched.forEach(function(o){if(!o||!o.date)return;var x=Object.assign({},o),ks=performanceTimeMatchKeys(e,x),ts=vals(tm,ks),os=vals(om,ks),st=String(x.startTime||e.startTime||'').replace(/\\s+/g,'');if(!st&&ts.length===1)x.startTime=ts[0];if(!String(x.openTime||e.openTime||'').replace(/\\s+/g,'')&&os.length===1)x.openTime=os[0];if(!String(x.startTime||e.startTime||'').replace(/\\s+/g,'')&&ts.length>1&&family(e)==='schedule'){suppressed=true;return}ns.push(x)});c.schedule=ns;if(sched.length&&ns.length!==sched.length){c.eventDates=ns.map(function(x){return String(x.date).slice(0,10)});c.eventDate=c.eventDates[0]||null;c.eventEndDate=c.eventDates.length?c.eventDates[c.eventDates.length-1]:null}}else if(e.eventDate){var pseudo={date:e.eventDate,venue:e.venue||'',startTime:e.startTime||'',openTime:e.openTime||''},ks=performanceTimeMatchKeys(e,pseudo),ts=vals(tm,ks),os=vals(om,ks);if(!String(c.startTime||'').replace(/\\s+/g,'')&&ts.length===1)c.startTime=ts[0];if(!String(c.openTime||'').replace(/\\s+/g,'')&&os.length===1)c.openTime=os[0];if(!String(c.startTime||'').replace(/\\s+/g,'')&&ts.length>1&&family(e)==='schedule'){c.eventDate=null;c.eventDates=[];c.eventEndDate=null;suppressed=true}}if(suppressed)c.performanceDuplicateSuppressed=true;return c})}"
)

PREPARE_RECONCILE_OLD = "function prepare(raw){raw=expandCanonicalOffers(raw);var fixed=raw.map(function(e){return repair(e,raw)});fixed=mergePiaDuplicates(fixed);return fixed.filter(function(e){if(playguide(e)&&(family(e)==='fc'||family(e)==='upgrade'))return false;return currentEnough(e)})}"
PREPARE_RECONCILE_NEW = "function prepare(raw){raw=expandCanonicalOffers(raw);var fixed=raw.map(function(e){return repair(e,raw)});fixed=reconcilePerformanceTimes(fixed);fixed=mergePiaDuplicates(fixed);return fixed.filter(function(e){if(playguide(e)&&(family(e)==='fc'||family(e)==='upgrade'))return false;return currentEnough(e)})}"
'''
    if marker not in text:
        raise SystemExit("canonicalize marker not found")
    text = text.replace(marker, helper + marker, 1)

if "def install_performance_reconcile" not in text:
    marker = "def install_application_band_identity(page: str) -> str:\n"
    func = '''def install_performance_reconcile(page: str) -> str:\n    if "function reconcilePerformanceTimes(all)" not in page:\n        anchor = page.find("function prepare(raw)")\n        if anchor < 0:\n            raise RuntimeError("could not locate prepare() for performance reconciliation")\n        page = page[:anchor] + PERFORMANCE_RECONCILE_JS + page[anchor:]\n    if PREPARE_RECONCILE_NEW in page:\n        return page\n    if PREPARE_RECONCILE_OLD not in page:\n        raise RuntimeError("schedule prepare() changed; performance reconciliation could not be installed")\n    return page.replace(PREPARE_RECONCILE_OLD, PREPARE_RECONCILE_NEW, 1)\n\n\n'''
    if marker not in text:
        raise SystemExit("application band installer marker not found")
    text = text.replace(marker, func + marker, 1)

old_calls = "    page = install_offer_adapter(page)\n    page = install_application_band_identity(page)\n"
new_calls = "    page = install_offer_adapter(page)\n    page = install_performance_reconcile(page)\n    page = install_application_band_identity(page)\n"
if new_calls not in text:
    if old_calls not in text:
        raise SystemExit("install call marker not found")
    text = text.replace(old_calls, new_calls, 1)

old_required = '        "raw=expandCanonicalOffers(raw)",\n        "function applicationBandSubjectKey(e)",\n'
new_required = '        "raw=expandCanonicalOffers(raw)",\n        "function reconcilePerformanceTimes(all)",\n        "fixed=reconcilePerformanceTimes(fixed)",\n        "function applicationBandSubjectKey(e)",\n'
if new_required not in text:
    if old_required not in text:
        raise SystemExit("required invariant marker not found")
    text = text.replace(old_required, new_required, 1)

fix.write_text(text, encoding="utf-8")

test = Path("scripts/test_schedule_band_grouping.js")
t = test.read_text(encoding="utf-8")
if "same Candy Tune performance must collapse timed and untimed source rows" not in t:
    marker = "const release = {\n"
    regression = r'''const candyTourUrl = 'https://candytune.asobisystem.com/feature/candytune_nationwide_tour2099';
const candyPerformanceRows = [
  {
    id: 'candy-master', group: 'CANDY TUNE', title: 'CANDY TUNE JAPAN TOUR 2099 - AUTUMN -',
    ticketType: '現在受付なし', applicationStatus: 'none', officialTourUrl: candyTourUrl,
    schedule: [{ date: '2099-09-09', venue: '大阪府 グランキューブ大阪 メインホール', openTime: '17:30', startTime: '18:30' }],
    eventDate: '2099-09-09', venue: '大阪府 グランキューブ大阪 メインホール',
  },
  {
    id: 'candy-pia-derived', group: 'CANDY TUNE', title: 'CANDY TUNE JAPAN TOUR 2099 - AUTUMN -',
    ticketType: '現在受付なし', applicationStatus: 'none', sourceType: 'pia', primarySource: 'pia',
    schedule: [{ date: '2099-09-09', venue: '大阪府 グランキューブ大阪 メインホール' }],
    eventDate: '2099-09-09', venue: '大阪府 グランキューブ大阪 メインホール',
  },
  {
    id: 'candy-official-osaka', group: 'CANDY TUNE', title: '「CANDY TUNE JAPAN TOUR 2099 - AUTUMN -」大阪公演',
    ticketType: '現在受付なし', applicationStatus: 'none', officialTourUrl: candyTourUrl,
    schedule: [{ date: '2099-09-09', venue: '大阪府 グランキューブ大阪 メインホール' }],
    eventDate: '2099-09-09', venue: '大阪府 グランキューブ大阪 メインホール',
  },
];
const candyModels = context.__scheduleTest.performanceModels(context.__scheduleTest.prepare(candyPerformanceRows));
assert.strictEqual(candyModels.length, 1, 'same Candy Tune performance must collapse timed and untimed source rows into one item');
assert.strictEqual(candyModels[0].startTime, '18:30', 'the unique verified performance time must be inherited by untimed duplicate rows');

const twoShowRows = [
  { id: 'show-1', group: 'CANDY TUNE', title: 'CANDY TUNE DOUBLE SHOW', ticketType: '現在受付なし', applicationStatus: 'none', officialTourUrl: candyTourUrl, eventDate: '2099-10-01', venue: '東京都 同一会場', startTime: '13:00' },
  { id: 'show-2', group: 'CANDY TUNE', title: 'CANDY TUNE DOUBLE SHOW', ticketType: '現在受付なし', applicationStatus: 'none', officialTourUrl: candyTourUrl, eventDate: '2099-10-01', venue: '東京都 同一会場', startTime: '18:00' },
  { id: 'show-ambiguous-source', group: 'CANDY TUNE', title: 'CANDY TUNE DOUBLE SHOW', ticketType: '現在受付なし', applicationStatus: 'none', officialTourUrl: candyTourUrl, eventDate: '2099-10-01', venue: '東京都 同一会場' },
];
const twoShowModels = context.__scheduleTest.performanceModels(context.__scheduleTest.prepare(twoShowRows));
assert.strictEqual(twoShowModels.length, 2, 'two genuinely different start times must stay as two performances without a third untimed duplicate');

const release = {
'''
    if marker not in t:
        raise SystemExit("release marker not found in test")
    t = t.replace(marker, regression, 1)

test.write_text(t, encoding="utf-8")
