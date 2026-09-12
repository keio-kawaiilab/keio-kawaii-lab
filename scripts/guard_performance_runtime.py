#!/usr/bin/env python3
"""Keep canonical performances and their offers out of legacy ticket-row merging."""
from pathlib import Path


def replace_once(page: str, old: str, new: str) -> str:
    if new in page:
        return page
    if page.count(old) != 1:
        raise RuntimeError(f"Runtime shape changed; refusing unsafe publication: {old[:90]}")
    return page.replace(old, new, 1)


def transform(page: str) -> str:
    # An explicit offer provider wins over unrelated links attached to a show.
    page = replace_once(page, "function providerId(e){", "function providerId(e){var explicit=String(e.ticketProvider||e.primarySource||'').toLowerCase();if(/^(official|pia|lawson|eplus|sukisuki|kawaii-store|rakuten|hmv|tower)$/.test(explicit))return explicit;")
    # A show is not a sale. Never inherit a ticket deadline onto the show row.
    page = replace_once(page,
        "var base=Object.assign({},e);delete base.offers;out.push(base);",
        "var base=Object.assign({},e);delete base.offers;base.canonicalRuntimeRole='performance';base.ticketType='現在受付なし';base.applicationStatus='none';base.ticketProvider='official';base.primarySource='official';['applyStart','applyEnd','resultDate','paymentEnd'].forEach(function(k){delete base[k]});out.push(base);")
    page = replace_once(page,
        "x.id=o.sourceRowId||String(base.id||'special')+'-offer-'+i;",
        "x.canonicalRuntimeRole='offer';x.applicationStatus=o.applicationStatus||'unknown';x.ticketType=o.ticketType||'';x.id=o.sourceRowId||String(base.id||'special')+'-offer-'+i;")
    page = replace_once(page,
        "if(x.ticketProvider!=='official')x.primarySource=x.ticketProvider;",
        "x.primarySource=x.ticketProvider;")
    page = replace_once(page,
        "[o.url].concat(o.urls||[]).concat(base.urls||[]).forEach(function(u){if(u&&us.indexOf(u)<0)us.push(u)});",
        "[o.url].concat(o.urls||[]).forEach(function(u){if(u&&us.indexOf(u)<0)us.push(u)});if(!us.length)us=[base.url||''];")
    page = replace_once(page, "function repair(e,all){", "function repair(e,all){if(e.canonicalRuntimeRole)return Object.assign({},e);")
    page = replace_once(page,
        "function mergePiaDuplicates(all){var out=[],idx={};all.forEach(function(e){",
        "function mergePiaDuplicates(all){var out=[],idx={};all.forEach(function(e){if(e.canonicalRuntimeRole){out.push(e);return}")
    # Expired offers remain as history, while expired application bands continue
    # to be hidden by effectiveBand(). Past shows still disappear normally.
    page = replace_once(page,
        "var endDay=p(e.applyEnd),endMoment=moment(e.applyEnd,true);",
        "if(e.canonicalRuntimeRole)return !(last&&last<today);var endDay=p(e.applyEnd),endMoment=moment(e.applyEnd,true);")
    page = replace_once(page,
        "return fixed.filter(function(e){if(playguide(e)",
        "return fixed.filter(function(e){if(e.canonicalRuntimeRole)return currentEnough(e);if(playguide(e)")
    return page


def main() -> int:
    path = Path('schedule.html')
    path.write_text(transform(path.read_text(encoding='utf-8')), encoding='utf-8')
    print('Canonical performances survive ticket deduplication and ended receptions')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
