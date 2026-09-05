from pathlib import Path

fix = Path("scripts/fix_schedule_shell.py")
text = fix.read_text(encoding="utf-8")

status_anchor = '''STATUS_NEW = "document.getElementById('status').textContent='最終更新: '+(data.checkedAt||data.updatedAt||'不明');render()"\n'''
constants = r'''
APPLICATION_BAND_KEY_LEGACY = "function applicationBandKey(e,index){if(!playguide(e))return'event|'+index;return[String(e.group||''),parts(e).slice().sort().join(','),providerId(e),String(e.ticketType||''),String(e.applyStart||''),String(e.applyEnd||''),performanceTitleKey(e)].join('|')}"
APPLICATION_BAND_KEY_NEW = "function applicationBandSubjectKey(e){var u=String(e.officialTourUrl||'').trim();if(u)return'tour:'+u.toLowerCase().replace(/[?#].*$/,'').replace(/\\/$/,'');var t=String(title(e)||'').toLowerCase().replace(/^\\s*20\\d{2}[.\\/-]\\d{1,2}[.\\/-]\\d{1,2}\\s*/,'').replace(/\\s+/g,'').replace(/[!！・|｜\\-–—_\\[\\]()（）『』「」]/g,'');return'title:'+t}function applicationBandKey(e,index){var tour=String(e.officialTourUrl||'').trim();if(!playguide(e)&&!tour)return'event|'+index;return[String(e.group||''),parts(e).slice().sort().join(','),providerId(e),String(e.ticketType||''),String(e.applyStart||''),String(e.applyEnd||''),applicationBandSubjectKey(e)].join('|')}"
'''
if "APPLICATION_BAND_KEY_NEW" not in text:
    if status_anchor not in text:
        raise SystemExit("status anchor not found in fix_schedule_shell.py")
    text = text.replace(status_anchor, status_anchor + constants + "\n", 1)

function_anchor = "def install_truthful_status(page: str) -> str:\n"
new_function = '''def install_application_band_identity(page: str) -> str:
    if APPLICATION_BAND_KEY_NEW in page:
        return page
    if APPLICATION_BAND_KEY_LEGACY not in page:
        raise RuntimeError("schedule applicationBandKey() changed; stable tour identity could not be installed")
    return page.replace(APPLICATION_BAND_KEY_LEGACY, APPLICATION_BAND_KEY_NEW, 1)


'''
if "def install_application_band_identity" not in text:
    if function_anchor not in text:
        raise SystemExit("function anchor not found")
    text = text.replace(function_anchor, new_function + function_anchor, 1)

call_old = "    page = install_offer_adapter(page)\n    page = install_truthful_status(page)\n"
call_new = "    page = install_offer_adapter(page)\n    page = install_application_band_identity(page)\n    page = install_truthful_status(page)\n"
if call_new not in text:
    if call_old not in text:
        raise SystemExit("main install call anchor not found")
    text = text.replace(call_old, call_new, 1)

required_old = '        "raw=expandCanonicalOffers(raw)",\n        "function performanceModels(vis)",\n'
required_new = '        "raw=expandCanonicalOffers(raw)",\n        "function applicationBandSubjectKey(e)",\n        "e.officialTourUrl",\n        "function performanceModels(vis)",\n'
if required_new not in text:
    if required_old not in text:
        raise SystemExit("required invariant anchor not found")
    text = text.replace(required_old, required_new, 1)

fix.write_text(text, encoding="utf-8")

test = Path("scripts/test_schedule_band_grouping.js")
t = test.read_text(encoding="utf-8")
anchor = "assert.strictEqual(lawson.events.length, 2);\n\nconst release = {\n"
regression = r'''assert.strictEqual(lawson.events.length, 2);

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
'''
if "same official FC tour and same application window must render one band" not in t:
    if anchor not in t:
        raise SystemExit("test insertion anchor not found")
    t = t.replace(anchor, regression, 1)
test.write_text(t, encoding="utf-8")
