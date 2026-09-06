#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import build_schedule_snapshot
from normalize_special_event_entities import normalize_payload, validate

PAGE = Path("schedule.html")
DATA = Path("data/live-events.json")

# Public schedule identity is the physical performance itself. Source article,
# ticket type, FC/upgrade status and eventKind must never split one performance
# into multiple public rows. A verified start time remains part of the identity
# so genuine matinee/evening performances on the same day stay separate.
PERFORMANCE_KEY_JS = (
    "function performanceVenueKey(e,o){var v=String((o&&o.venue)||e.venue||'').toLowerCase();"
    "v=v.replace(/^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\\s*/,'').replace(/\\s+/g,'').replace(/[!！・|｜\\-–—_\\[\\]()（）『』「」]/g,'');return v}"
    "function performanceKey(e,o){var day=String((o&&o.date)||e.eventDate||'').slice(0,10),"
    "time=String((o&&o.startTime)||e.startTime||'').replace(/\\s+/g,''),venue=performanceVenueKey(e,o),titleKey=performanceTitleKey(e),group=String(e.group||'').trim();"
    "if(day&&time)return [group,day,'time',time].join('|');"
    "return [group,day,'fallback',venue,titleKey].join('|')}"
)

CANONICAL_OFFER_JS = (
    "function expandCanonicalOffers(raw){var out=[];(raw||[]).forEach(function(e){"
    "if(!e||e.entityType!=='special-event'||!Array.isArray(e.offers)){out.push(e);return}"
    "var base=Object.assign({},e);delete base.offers;out.push(base);"
    "e.offers.forEach(function(o,i){if(!o||typeof o!=='object')return;var x=Object.assign({},base,o),us=[];"
    "x.id=o.sourceRowId||String(base.id||'special')+'-offer-'+i;"
    "x.ticketProvider=o.provider||o.ticketProvider||x.ticketProvider||'official';"
    "if(x.ticketProvider!=='official')x.primarySource=x.ticketProvider;"
    "[o.url].concat(o.urls||[]).concat(base.urls||[]).forEach(function(u){if(u&&us.indexOf(u)<0)us.push(u)});"
    "x.urls=us;if(o.url)x.url=o.url;delete x.sourceRowId;delete x.provider;out.push(x)})});return out}"
)

PREPARE_OLD = "function prepare(raw){var fixed=raw.map(function(e){return repair(e,raw)});fixed=mergePiaDuplicates(fixed);return fixed.filter(function(e){if(playguide(e)&&(family(e)==='fc'||family(e)==='upgrade'))return false;return currentEnough(e)})}"
PREPARE_NEW = "function prepare(raw){raw=expandCanonicalOffers(raw);var fixed=raw.map(function(e){return repair(e,raw)});fixed=mergePiaDuplicates(fixed);return fixed.filter(function(e){if(playguide(e)&&(family(e)==='fc'||family(e)==='upgrade'))return false;return currentEnough(e)})}"
STATUS_LEGACY = "document.getElementById('status').textContent='最終データ更新: '+(data.updatedAt||'不明');render()"
STATUS_DOUBLE = "document.getElementById('status').textContent='最終確認: '+(data.checkedAt||'不明')+' ／ 最終データ更新: '+(data.updatedAt||'不明');render()"
STATUS_NEW = "document.getElementById('status').textContent='最終更新: '+(data.checkedAt||data.updatedAt||'不明');render()"

APPLICATION_BAND_KEY_LEGACY = "function applicationBandKey(e,index){if(!playguide(e))return'event|'+index;return[String(e.group||''),parts(e).slice().sort().join(','),providerId(e),String(e.ticketType||''),String(e.applyStart||''),String(e.applyEnd||''),performanceTitleKey(e)].join('|')}"
APPLICATION_BAND_KEY_NEW = "function applicationBandSubjectKey(e){var u=String(e.officialTourUrl||'').trim();if(u)return'tour:'+u.toLowerCase().replace(/[?#].*$/,'').replace(/\\/$/,'');var t=String(title(e)||'').toLowerCase().replace(/^\\s*20\\d{2}[.\\/-]\\d{1,2}[.\\/-]\\d{1,2}\\s*/,'').replace(/\\s+/g,'').replace(/[!！・|｜\\-–—_\\[\\]()（）『』「」]/g,'');return'title:'+t}function applicationBandKey(e,index){var tour=String(e.officialTourUrl||'').trim();if(!playguide(e)&&!tour)return'event|'+index;return[String(e.group||''),parts(e).slice().sort().join(','),providerId(e),String(e.ticketType||''),String(e.applyStart||''),String(e.applyEnd||''),applicationBandSubjectKey(e)].join('|')}"


PERFORMANCE_RECONCILE_JS = (
    "function performanceTimeMatchKeys(e,o){var day=String((o&&o.date)||e.eventDate||'').slice(0,10),venue=performanceVenueKey(e,o),base=[String(e.group||''),day,venue].join('|'),out=[],tour=String(e.officialTourUrl||'').trim().toLowerCase().replace(/[?#].*$/,'').replace(/\\/$/,'');if(tour)out.push(base+'|tour:'+tour);var t=performanceTitleKey(e);if(t)out.push(base+'|title:'+t);return out}"
    "function reconcilePerformanceTimes(all){var tm={},om={};function add(map,k,v){if(!v)return;(map[k]||(map[k]={}))[String(v).replace(/\\s+/g,'')]=1}function vals(map,ks){var x={};ks.forEach(function(k){Object.keys(map[k]||{}).forEach(function(v){x[v]=1})});return Object.keys(x)};"
    "(all||[]).forEach(function(e){occ(e).forEach(function(o){var ks=performanceTimeMatchKeys(e,o),st=String(o.startTime||e.startTime||'').replace(/\\s+/g,''),ot=String(o.openTime||e.openTime||'').replace(/\\s+/g,'');ks.forEach(function(k){add(tm,k,st);add(om,k,ot)})})});"
    "return(all||[]).map(function(e){var c=Object.assign({},e),sched=Array.isArray(e.schedule)?e.schedule:null,suppressed=false;if(sched){var ns=[];sched.forEach(function(o){if(!o||!o.date)return;var x=Object.assign({},o),ks=performanceTimeMatchKeys(e,x),ts=vals(tm,ks),os=vals(om,ks),st=String(x.startTime||e.startTime||'').replace(/\\s+/g,''),ot=String(x.openTime||e.openTime||'').replace(/\\s+/g,'');if(!st&&ts.length===1)x.startTime=ts[0];if(st&&ot&&st===ot){var credible=ts.filter(function(v){return v!==ot});if(credible.length===1)x.startTime=credible[0]}if(!ot&&os.length===1)x.openTime=os[0];if(!String(x.startTime||e.startTime||'').replace(/\\s+/g,'')&&ts.length>1&&family(e)==='schedule'){suppressed=true;return}ns.push(x)});c.schedule=ns;if(sched.length&&ns.length!==sched.length){c.eventDates=ns.map(function(x){return String(x.date).slice(0,10)});c.eventDate=c.eventDates[0]||null;c.eventEndDate=c.eventDates.length?c.eventDates[c.eventDates.length-1]:null}}else if(e.eventDate){var pseudo={date:e.eventDate,venue:e.venue||'',startTime:e.startTime||'',openTime:e.openTime||''},ks=performanceTimeMatchKeys(e,pseudo),ts=vals(tm,ks),os=vals(om,ks),st=String(c.startTime||'').replace(/\\s+/g,''),ot=String(c.openTime||'').replace(/\\s+/g,'');if(!st&&ts.length===1)c.startTime=ts[0];if(st&&ot&&st===ot){var credible=ts.filter(function(v){return v!==ot});if(credible.length===1)c.startTime=credible[0]}if(!ot&&os.length===1)c.openTime=os[0];if(!String(c.startTime||'').replace(/\\s+/g,'')&&ts.length>1&&family(e)==='schedule'){c.eventDate=null;c.eventDates=[];c.eventEndDate=null;suppressed=true}}if(suppressed)c.performanceDuplicateSuppressed=true;return c})}"
)

PREPARE_RECONCILE_OLD = "function prepare(raw){raw=expandCanonicalOffers(raw);var fixed=raw.map(function(e){return repair(e,raw)});fixed=mergePiaDuplicates(fixed);return fixed.filter(function(e){if(playguide(e)&&(family(e)==='fc'||family(e)==='upgrade'))return false;return currentEnough(e)})}"
PREPARE_RECONCILE_NEW = "function prepare(raw){raw=expandCanonicalOffers(raw);var fixed=raw.map(function(e){return repair(e,raw)});fixed=reconcilePerformanceTimes(fixed);fixed=mergePiaDuplicates(fixed);return fixed.filter(function(e){if(playguide(e)&&(family(e)==='fc'||family(e)==='upgrade'))return false;return currentEnough(e)})}"



def canonicalize_public_data() -> dict:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    normalized, report = normalize_payload(payload)
    errors = validate(normalized)
    if errors:
        raise RuntimeError("canonical special-event normalization failed: " + "; ".join(errors))
    DATA.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def replace_identity_block(page: str) -> str:
    current_start = page.find("function performanceVenueKey(e,o)")
    legacy_start = page.find("function performanceKey(e,o)")
    if current_start >= 0:
        start = current_start
    elif legacy_start >= 0:
        start = legacy_start
    else:
        raise RuntimeError("could not locate performanceKey() in schedule.html")

    end = page.find("function performanceKeyForEvent", start)
    if end < 0:
        raise RuntimeError("could not locate performanceKeyForEvent() in schedule.html")
    return page[:start] + PERFORMANCE_KEY_JS + page[end:]


def install_offer_adapter(page: str) -> str:
    if "function expandCanonicalOffers(raw)" not in page:
        anchor = page.find("function prepare(raw)")
        if anchor < 0:
            raise RuntimeError("could not locate prepare() for canonical special-event adapter")
        page = page[:anchor] + CANONICAL_OFFER_JS + page[anchor:]

    if "raw=expandCanonicalOffers(raw)" in page:
        return page
    if PREPARE_OLD not in page:
        raise RuntimeError("schedule prepare() changed; canonical special-event offers could not be installed")
    return page.replace(PREPARE_OLD, PREPARE_NEW, 1)


def install_performance_reconcile(page: str) -> str:
    # Always replace the generated reconcile block when present so an old
    # release shell can never preserve obsolete eventKind-based matching.
    start = page.find("function performanceTimeMatchKeys(e,o)")
    if start >= 0:
        end = page.find("function prepare(raw)", start)
        if end < 0:
            raise RuntimeError("could not locate prepare() after performance reconciliation")
        page = page[:start] + PERFORMANCE_RECONCILE_JS + page[end:]
    else:
        anchor = page.find("function prepare(raw)")
        if anchor < 0:
            raise RuntimeError("could not locate prepare() for performance reconciliation")
        page = page[:anchor] + PERFORMANCE_RECONCILE_JS + page[anchor:]

    if "fixed=reconcilePerformanceTimes(fixed)" in page:
        return page
    if PREPARE_RECONCILE_OLD not in page:
        raise RuntimeError("schedule prepare() changed; performance reconciliation could not be installed")
    return page.replace(PREPARE_RECONCILE_OLD, PREPARE_RECONCILE_NEW, 1)


def install_application_band_identity(page: str) -> str:
    if APPLICATION_BAND_KEY_NEW in page:
        return page
    if APPLICATION_BAND_KEY_LEGACY not in page:
        raise RuntimeError("schedule applicationBandKey() changed; stable tour identity could not be installed")
    return page.replace(APPLICATION_BAND_KEY_LEGACY, APPLICATION_BAND_KEY_NEW, 1)


def install_truthful_status(page: str) -> str:
    if STATUS_NEW in page:
        return page
    if STATUS_DOUBLE in page:
        return page.replace(STATUS_DOUBLE, STATUS_NEW, 1)
    if STATUS_LEGACY in page:
        return page.replace(STATUS_LEGACY, STATUS_NEW, 1)
    raise RuntimeError("schedule status renderer changed; public update timestamp could not be installed")


def main() -> int:
    # This is the final release boundary. Collectors/audits may temporarily work
    # with one row per source, but no source row may change physical performance
    # identity. Rebuild the page from canonical data, then install the one-event
    # identity and reconciliation code as the final shell step.
    report = canonicalize_public_data()
    if build_schedule_snapshot.main() != 0:
        raise RuntimeError("failed to rebuild schedule after canonical special-event normalization")

    page = PAGE.read_text(encoding="utf-8")
    page = replace_identity_block(page)
    page = install_offer_adapter(page)
    page = install_performance_reconcile(page)
    page = install_application_band_identity(page)
    page = install_truthful_status(page)

    required = (
        "function performanceTitleKey(e)",
        "function performanceVenueKey(e,o)",
        "function performanceKey(e,o)",
        "if(day&&time)return [group,day,'time',time].join('|')",
        "function expandCanonicalOffers(raw)",
        "raw=expandCanonicalOffers(raw)",
        "function reconcilePerformanceTimes(all)",
        "fixed=reconcilePerformanceTimes(fixed)",
        "function applicationBandSubjectKey(e)",
        "e.officialTourUrl",
        "function performanceModels(vis)",
        "perfSeen[pk]",
        "data-performance-key",
        "最終更新:",
        "data.checkedAt",
    )
    missing = [token for token in required if token not in page]
    if missing:
        raise RuntimeError(f"schedule performance identity invariant missing: {missing}")

    performance_block = page[page.find("function performanceKey(e,o)"):page.find("function performanceKeyForEvent")]
    if "eventKind(e)" in performance_block:
        raise RuntimeError("release shell reintroduced eventKind into physical performance identity")

    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [script for script in scripts if "(function(){'use strict';" in script]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")

    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")
    PAGE.write_text(page, encoding="utf-8")
    print("Schedule renders one physical performance per group/date/start time")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
