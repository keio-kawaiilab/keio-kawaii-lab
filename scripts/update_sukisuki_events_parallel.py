#!/usr/bin/env python3
"""Compatibility entrypoint plus fresh SUKISUKI discovery.

SUKISUKI's public goods list can lag behind product links announced by official
accounts.  The maintained collector still owns parsing/merging; this wrapper
supplements its discovered URLs by probing a small bounded range immediately
after the newest numeric goods id seen on the public list.  Every probed page
must still pass the normal detail-page group/type/date parser before it can be
published.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests

import update_sukisuki_events

PROBE_AHEAD = 64
PROBE_TIMEOUT = 4


def _probe_one(goods_id: int, headers: dict[str, str]) -> str | None:
    """Return URL only when a not-yet-listed detail page is a valid future online event."""
    url = f"https://sukisuki-shop.com/goods/{goods_id}"
    session = requests.Session()
    session.headers.update(headers)
    try:
        # parse_goods performs the same official detail-page validation used by
        # normal listed products: KAWAII LAB. group, online-event signal, date.
        event = update_sukisuki_events.parse_goods(
            session,
            url,
            datetime.now(update_sukisuki_events.JST).date(),
        )
        return url if event else None
    except Exception:
        return None
    finally:
        session.close()


def install_fresh_probe(workers: int) -> None:
    original_discover = update_sukisuki_events.discover

    def discover_with_probe(session: requests.Session):
        listed_urls, failures = original_discover(session)
        ranks = [update_sukisuki_events.goods_rank(url) for url in listed_urls]
        ranks = [rank for rank in ranks if rank > 0]
        if not ranks:
            return listed_urls, failures

        newest = max(ranks)
        headers = {str(k): str(v) for k, v in session.headers.items()}
        found: list[str] = []
        probe_workers = max(4, min(16, workers * 2))

        with ThreadPoolExecutor(max_workers=probe_workers) as pool:
            futures = {
                pool.submit(_probe_one, newest + offset, headers): newest + offset
                for offset in range(1, PROBE_AHEAD + 1)
            }
            for future in as_completed(futures):
                url = future.result()
                if url:
                    found.append(url)

        combined = set(listed_urls)
        combined.update(found)
        ordered = sorted(
            combined,
            key=lambda url: (update_sukisuki_events.goods_rank(url), url),
            reverse=True,
        )
        print(json.dumps({
            "sukisukiFreshProbe": {
                "listedNewestGoodsId": newest,
                "probeStartGoodsId": newest + 1,
                "probeEndGoodsId": newest + PROBE_AHEAD,
                "freshOnlineGoods": sorted(
                    found,
                    key=update_sukisuki_events.goods_rank,
                    reverse=True,
                ),
            }
        }, ensure_ascii=False))
        return ordered, failures

    update_sukisuki_events.discover = discover_with_probe


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the maintained SUKISUKI collector")
    parser.add_argument("--workers", type=int, default=1, help="Worker hint used by bounded fresh-goods probing")
    args = parser.parse_args()

    install_fresh_probe(max(1, args.workers))

    # The maintained collector has its own argparse parser and does not know the
    # historical --workers option. Remove wrapper-only arguments before handing
    # control to it.
    original_argv = sys.argv[:]
    try:
        sys.argv = [original_argv[0]]
        return update_sukisuki_events.main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
