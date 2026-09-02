#!/usr/bin/env python3
from __future__ import annotations

import json

import reconstruct_shintakashima_downbound_v3 as core


def window(values: list[int], index: int, radius: int = 5) -> list[dict]:
    lo = max(0, index - radius)
    hi = min(len(values), index + radius + 1)
    return [{"index": i, "time": core.fmt(values[i])} for i in range(lo, hi)]


def main() -> int:
    payload = json.loads(core.RAW.read_text(encoding="utf-8"))
    boards = core.board_map(payload)
    yoko = boards[("横浜", core.WEEKDAY)]
    shin = boards[("新高島", core.WEEKDAY)]
    mina = [
        core.to_minute(x)
        for x in json.loads(core.MINA_RECON.read_text(encoding="utf-8"))["departures"]
    ]
    trusted = core.exact_yokohama_match(yoko, shin)
    reverse = {oi: ti for ti, oi in trusted.items()}
    unmatched = [i for i in range(len(shin)) if i not in reverse]
    diagnostics = []
    for oi in unmatched:
        obs = shin[oi]
        previous = [(o, reverse[o]) for o in range(oi - 1, -1, -1) if o in reverse]
        following = [(o, reverse[o]) for o in range(oi + 1, len(shin)) if o in reverse]
        left = previous[0] if previous else (-1, -1)
        right = following[0] if following else (len(shin), len(yoko))
        candidate_rows = []
        for ti in range(left[1] + 1, right[1]):
            candidates = []
            for minute in range(yoko[ti] + 1, yoko[ti] + 6):
                candidates.append({
                    "reconstructed": core.fmt(minute),
                    "correction": abs(minute - obs),
                    "toMinatomirai": mina[ti] - minute,
                })
            candidate_rows.append({
                "trainIndex": ti,
                "yokohama": core.fmt(yoko[ti]),
                "minatomirai": core.fmt(mina[ti]),
                "candidates": candidates,
            })
        diagnostics.append({
            "observedIndex": oi,
            "observed": core.fmt(obs),
            "leftAnchor": None if left[1] < 0 else {
                "observedIndex": left[0],
                "trainIndex": left[1],
                "shintakashima": core.fmt(shin[left[0]]),
                "yokohama": core.fmt(yoko[left[1]]),
                "minatomirai": core.fmt(mina[left[1]]),
            },
            "rightAnchor": None if right[1] >= len(yoko) else {
                "observedIndex": right[0],
                "trainIndex": right[1],
                "shintakashima": core.fmt(shin[right[0]]),
                "yokohama": core.fmt(yoko[right[1]]),
                "minatomirai": core.fmt(mina[right[1]]),
            },
            "observedWindow": window(shin, oi),
            "candidateTrains": candidate_rows,
        })
    print(json.dumps({"trustedCount": len(trusted), "unmatched": diagnostics}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
