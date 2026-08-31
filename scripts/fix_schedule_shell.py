#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import build_schedule_snapshot
from normalize_special_event_entities import normalize_payload, validate

PAGE = Path("schedule.html")
DATA = Path("data/live-events.json")

# Public schedule identity is based on the actual performance, not the sale row.
# Normal live performances can have two shows on the same day, so a verified
# start time remains part of their identity. Release events and large benefit
# events are canonical event entities; any sales channels live below them in
# offers[]. The renderer temporarily expands those offers only for application
# bands, while performance identity still collapses them into one real event.
PERFORMANCE_KEY_JS = (
    "function performanceVenueKey(e,o){var v=String((o&&o.venue)||e.venue||'').toLowerCase();"
    "v=v.replace(/^(?:北海道|東京都|京都府|大阪府|.{2,3}県)\\s*/,'').replace(/\\s+/g,'').replace(/[!！・|｜\\-–—_\\[\\]()（）『』「」]/g,'');return v}"
    "function performanceKey(e,o){var day=String((o&&o.date)||'').slice(0,10),kind=eventKind(e),"
    "time=String((o&&o.startTime)||e.startTime||'').replace(/\\s+/g,''),venue=performanceVenueKey(e,o),titleKey=performanceTitleKey(e),base=[String(e.group||''),day,kind];"
    "if(kind==='release'||kind==='benefit')return base.concat(['special',venue,titleKey]).join('|');"
    "if(time)return base.concat(['time',time]).join('|');"
    "return base.concat(['fallback',venue,titleKey]).join('|')}"
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
STATUS_OLD = "document.getElementById('status').textContent='最終データ更新: '+(data.updatedAt||'不明');render()"
STATUS_NEW = "document.getElementById('status').textContent='最終確認: '+(data.checkedAt||'不明')+' ／ 最終データ更新: '+(data.updatedAt||'不明');render()"


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

    if PREPARE_NEW in page:
        return page
    if PREPARE_OLD not in page:
        raise RuntimeError("schedule prepare() changed; canonical special-event offers could not be installed")
    return page.replace(PREPARE_OLD, PREPARE_NEW, 1)


def install_truthful_status(page: str) -> str:
    if STATUS_NEW in page:
        return page
    if STATUS_OLD not in page:
        raise RuntimeError("schedule status renderer changed; truthful refresh status could not be installed")
    return page.replace(STATUS_OLD, STATUS_NEW, 1)


def main() -> int:
    # This is the final release boundary. Collectors/audits may temporarily work
    # with one row per source, but no such row can reach the public JSON. Always
    # collapse to one real event + child offers, then rebuild the page from that
    # canonical data before applying the client-side compatibility adapter.
    report = canonicalize_public_data()
    if build_schedule_snapshot.main() != 0:
        raise RuntimeError("failed to rebuild schedule after canonical special-event normalization")

    page = PAGE.read_text(encoding="utf-8")
    page = replace_identity_block(page)
    page = install_offer_adapter(page)
    page = install_truthful_status(page)

    required = (
        "function performanceTitleKey(e)",
        "function performanceVenueKey(e,o)",
        "function performanceKey(e,o)",
        "kind==='release'||kind==='benefit'",
        "function expandCanonicalOffers(raw)",
        "raw=expandCanonicalOffers(raw)",
        "function performanceModels(vis)",
        "perfSeen[pk]",
        "data-performance-key",
        "最終確認:",
        "data.checkedAt",
    )
    missing = [token for token in required if token not in page]
    if missing:
        raise RuntimeError(f"schedule performance identity invariant missing: {missing}")

    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", page, re.S)
    executable = [script for script in scripts if "(function(){'use strict';" in script]
    if len(executable) != 1:
        raise RuntimeError(f"expected one executable inline script, found {len(executable)}")

    Path("/tmp/schedule-inline.js").write_text(executable[0], encoding="utf-8")
    PAGE.write_text(page, encoding="utf-8")
    print("Schedule renders canonical special-event entities with truthful refresh timestamps")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
