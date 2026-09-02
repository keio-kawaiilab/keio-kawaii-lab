#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

RAW = Path("data/transit/yokohama-minatomirai/official-downbound-departures.json")
MINA = Path("data/transit/yokohama-minatomirai/reconstructed-minatomirai-downbound.json")
WEEKDAY = "odpt.Calendar:Weekday"
HOLIDAY = "odpt.Calendar:SaturdayHoliday"


def to_minute(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m


def fmt(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def boards(payload: dict):
    return {
        (row["stationTitle"], row["calendar"]): [to_minute(x) for x in row["departures"]]
        for row in payload["boards"]
    }


def ordered_match(upstream: list[int], downstream: list[int]):
    n, m = len(upstream), len(downstream)
    bad = (-10**9, -10**9)
    dp = [[bad] * (m + 1) for _ in range(n + 1)]
    mv = [[""] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = (0, 0)
    for i in range(n + 1):
        for j in range(m + 1):
            state = dp[i][j]
            if state == bad:
                continue
            if i < n and state > dp[i + 1][j]:
                dp[i + 1][j] = state; mv[i + 1][j] = "u"
            if j < m and state > dp[i][j + 1]:
                dp[i][j + 1] = state; mv[i][j + 1] = "d"
            if i < n and j < m:
                delta = downstream[j] - upstream[i]
                if 1 <= delta <= 4:
                    cand = (state[0] + 1, state[1] - abs(delta - 2))
                    if cand > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = cand; mv[i + 1][j + 1] = "m"
    mapping = {}
    i, j = n, m
    while i or j:
        action = mv[i][j]
        if action == "m":
            mapping[i - 1] = j - 1; i -= 1; j -= 1
        elif action == "u": i -= 1
        elif action == "d": j -= 1
        elif i: i -= 1
        else: j -= 1
    return mapping


def main() -> int:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    b = boards(raw)
    mina_payload = json.loads(MINA.read_text(encoding="utf-8"))
    result = {}
    for calendar in (HOLIDAY, WEEKDAY):
        mina = [to_minute(x) for x in mina_payload["calendars"][calendar]["departures"]]
        basha = b[("馬車道", calendar)]
        nihon = b[("日本大通り", calendar)]
        mapping = ordered_match(mina, basha)
        reverse = {oi: ti for ti, oi in mapping.items()}
        used_trains = set(mapping)
        unmatched = []
        for oi, obs in enumerate(basha):
            if oi in reverse:
                continue
            prev = [(o, reverse[o]) for o in range(oi - 1, -1, -1) if o in reverse]
            nxt = [(o, reverse[o]) for o in range(oi + 1, len(basha)) if o in reverse]
            left = prev[0] if prev else (-1, -1)
            right = nxt[0] if nxt else (len(basha), len(mina))
            candidate_trains = []
            for ti in range(left[1] + 1, right[1]):
                if ti in used_trains:
                    continue
                candidates = [
                    minute for minute in range(mina[ti] + 1, mina[ti] + 5)
                ]
                candidate_trains.append({
                    "trainIndex": ti,
                    "minatomirai": fmt(mina[ti]),
                    "candidateDepartures": [fmt(x) for x in candidates],
                    "bestCorrection": min(abs(x - obs) for x in candidates),
                })
            unmatched.append({
                "observedIndex": oi,
                "bashamichiObserved": fmt(obs),
                "nihonOdoriSameIndex": fmt(nihon[oi]) if oi < len(nihon) else None,
                "leftAnchor": None if left[1] < 0 else {
                    "observedIndex": left[0], "trainIndex": left[1],
                    "minatomirai": fmt(mina[left[1]]), "bashamichi": fmt(basha[left[0]])
                },
                "rightAnchor": None if right[1] >= len(mina) else {
                    "observedIndex": right[0], "trainIndex": right[1],
                    "minatomirai": fmt(mina[right[1]]), "bashamichi": fmt(basha[right[0]])
                },
                "candidateTrains": candidate_trains,
            })
        result[calendar] = {
            "masterTrainCount": len(mina),
            "bashamichiRawCount": len(basha),
            "trustedMatchCount": len(mapping),
            "unmatched": unmatched,
        }
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
