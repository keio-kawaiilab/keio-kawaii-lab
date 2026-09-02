#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import reconstruct_minatomirai_weekday_downbound_v3 as core

RAW = Path("data/transit/yokohama-minatomirai/official-downbound-departures.json")
MINA = Path("data/transit/yokohama-minatomirai/reconstructed-minatomirai-downbound.json")


def board_map(payload):
    return {
        (row["stationTitle"], row["calendar"]): [core.to_minute(x) for x in row["departures"]]
        for row in payload["boards"]
    }


def simple_match(upstream, downstream, lo=1, hi=4, target=2):
    return core.partial_ordered_match(upstream, downstream, lo=lo, hi=hi, target=target)


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    b = board_map(raw)
    recon = json.loads(MINA.read_text(encoding="utf-8"))
    output = {}
    for calendar in (core.HOLIDAY, core.WEEKDAY):
        yoko = b[("横浜", calendar)]
        raw_mina = b[("みなとみらい", calendar)]
        final_mina = [core.to_minute(x) for x in recon["calendars"][calendar]["departures"]]
        basha = b[("馬車道", calendar)]
        nihon = b[("日本大通り", calendar)]

        mina_map, raw_mina_unmatched, yoko_without_raw = simple_match(yoko, raw_mina, lo=2, hi=6, target=4)
        trusted_mina = {ti: raw_mina[oi] for ti, (oi, _) in mina_map.items()}
        basha_map, basha_unmatched, _ = simple_match(final_mina, basha, lo=1, hi=4, target=2)
        reverse_basha = {oi: ti for ti, (oi, _) in basha_map.items()}

        rows = []
        for oi in basha_unmatched:
            obs = basha[oi]
            previous = [(o, reverse_basha[o]) for o in range(oi - 1, -1, -1) if o in reverse_basha]
            following = [(o, reverse_basha[o]) for o in range(oi + 1, len(basha)) if o in reverse_basha]
            left = previous[0] if previous else (-1, -1)
            right = following[0] if following else (len(basha), len(yoko))
            candidates = []
            for ti in range(left[1] + 1, right[1]):
                if ti in basha_map:
                    continue
                y = yoko[ti]
                fm = final_mina[ti]
                trusted = ti in trusted_mina
                # Nearby raw Mina rows are useful when current final Mina was synthetic.
                nearby_raw = [
                    core.fmt(value) for value in raw_mina
                    if abs(value - fm) <= 5 or (y + 2 <= value <= obs - 1)
                ]
                candidates.append({
                    "trainIndex": ti,
                    "yokohama": core.fmt(y),
                    "finalMinatomirai": core.fmt(fm),
                    "minatomiraiIsTrustedRaw": trusted,
                    "trustedRawMinatomirai": core.fmt(trusted_mina[ti]) if trusted else None,
                    "nearbyRawMinatomirai": nearby_raw,
                    "physicallyValidUsingCurrentMina": fm < obs,
                    "possibleMinatomiraiBeforeObservedBashamichi": [
                        core.fmt(x) for x in range(y + 2, min(y + 7, obs))
                    ],
                })
            rows.append({
                "bashamichiObservedIndex": oi,
                "bashamichiObserved": core.fmt(obs),
                "nihonOdoriSameIndex": core.fmt(nihon[oi]) if oi < len(nihon) else None,
                "leftAnchor": None if left[1] < 0 else {
                    "observedIndex": left[0], "trainIndex": left[1],
                    "minatomirai": core.fmt(final_mina[left[1]]),
                    "bashamichi": core.fmt(basha[left[0]]),
                },
                "rightAnchor": None if right[1] >= len(yoko) else {
                    "observedIndex": right[0], "trainIndex": right[1],
                    "minatomirai": core.fmt(final_mina[right[1]]),
                    "bashamichi": core.fmt(basha[right[0]]),
                },
                "candidateTrains": candidates,
            })

        output[calendar] = {
            "rawMinatomiraiUnmatched": [core.fmt(raw_mina[i]) for i in raw_mina_unmatched],
            "yokohamaWithoutTrustedRawMinatomirai": [core.fmt(yoko[i]) for i in yoko_without_raw],
            "bashamichiUnmatchedRows": rows,
        }
    print(json.dumps(output, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
