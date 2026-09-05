#!/usr/bin/env python3
from __future__ import annotations

import copy

import keisei_official_oshiage_evidence as subject


def fake_entities() -> dict:
    def station(name: str) -> dict:
        return {"odpt:stationTitle": {"ja": name}}
    return {"Station": [station("四ツ木"), station("押上"), station("青砥")]}


def fake_train(direction: str = "keisei-to-toei") -> dict:
    if direction == "keisei-to-toei":
        stops = [
            {"station": "四ツ木", "arrival": "06:00", "departure": "06:00"},
            {"station": "押上", "arrival": "06:05", "departure": "06:06"},
            {"station": "本所吾妻橋", "arrival": "06:08", "departure": "06:08"},
        ]
    else:
        stops = [
            {"station": "本所吾妻橋", "arrival": "06:03", "departure": "06:03"},
            {"station": "押上", "arrival": "06:05", "departure": "06:06"},
            {"station": "四ツ木", "arrival": "06:10", "departure": "06:10"},
        ]
    return {
        "sourceTrainId": "official-do-not-use-as-selector",
        "calendar": "weekday",
        "url": "https://example.test/official-train",
        "stops": stops,
    }


def fragment(fid: str, railway: str, station: str, first: bool, arrival: int | None, departure: int | None) -> dict:
    other = ["manual.Station:test.Other", 350, 350]
    boundary = [station, arrival, departure]
    stops = [boundary, other] if first else [other, boundary]
    return {
        "id": fid,
        "railway": railway,
        "calendar": "weekday",
        "stops": stops,
    }


def test_extracts_both_directions() -> None:
    names = subject.keisei_station_names(fake_entities())
    candidates, diagnostics = subject.extract_candidates(
        {"trains": [fake_train("keisei-to-toei"), fake_train("toei-to-keisei")]},
        names,
    )
    assert diagnostics["reasons"] == {}
    assert {row["direction"] for row in candidates} == {"keisei-to-toei", "toei-to-keisei"}
    assert all(subject.MARKER in row["evidence"] for row in candidates)


def test_same_operator_neighbours_do_not_claim_boundary() -> None:
    names = subject.keisei_station_names(fake_entities())
    train = fake_train()
    train["stops"][2]["station"] = "青砥"
    candidates, diagnostics = subject.extract_candidates({"trains": [train]}, names)
    assert candidates == []
    assert diagnostics["reasons"].get("cannot-classify-boundary-neighbours") == 1


def test_exact_singleton_only() -> None:
    names = subject.keisei_station_names(fake_entities())
    candidate = subject.extract_candidates({"trains": [fake_train()]}, names)[0][0]
    fragments = [
        fragment("k", subject.KEISEI_OSHIAGE, subject.KEISEI_STATION, False, 365, 366),
        fragment("t", subject.TOEI_ASAKUSA, subject.TOEI_STATION, True, None, 366),
    ]
    matched = subject.match_candidates([candidate], fragments)[0]
    assert matched["matchStatus"] == "matched-singleton"
    assert matched["fromFragment"] == "k"
    assert matched["toFragment"] == "t"


def test_nearby_minute_never_matches() -> None:
    names = subject.keisei_station_names(fake_entities())
    candidate = subject.extract_candidates({"trains": [fake_train()]}, names)[0][0]
    fragments = [
        fragment("k", subject.KEISEI_OSHIAGE, subject.KEISEI_STATION, False, 364, 364),
        fragment("t", subject.TOEI_ASAKUSA, subject.TOEI_STATION, True, None, 367),
    ]
    matched = subject.match_candidates([candidate], fragments)[0]
    assert matched["matchStatus"] == "unmatched"
    assert matched["sourceMatches"] == []
    assert matched["targetMatches"] == []


def test_ambiguity_fails_closed() -> None:
    names = subject.keisei_station_names(fake_entities())
    candidate = subject.extract_candidates({"trains": [fake_train()]}, names)[0][0]
    fragments = [
        fragment("k1", subject.KEISEI_OSHIAGE, subject.KEISEI_STATION, False, 365, 366),
        fragment("k2", subject.KEISEI_OSHIAGE, subject.KEISEI_STATION, False, 365, 366),
        fragment("t", subject.TOEI_ASAKUSA, subject.TOEI_STATION, True, None, 366),
    ]
    matched = subject.match_candidates([candidate], fragments)[0]
    assert matched["matchStatus"] == "ambiguous"
    assert matched["fromFragment"] is None


def test_train_number_is_not_fragment_selector() -> None:
    names = subject.keisei_station_names(fake_entities())
    first = subject.extract_candidates({"trains": [fake_train()]}, names)[0][0]
    changed_train = copy.deepcopy(fake_train())
    changed_train["sourceTrainId"] = "completely-different-number"
    second = subject.extract_candidates({"trains": [changed_train]}, names)[0][0]
    fragments = [
        fragment("k", subject.KEISEI_OSHIAGE, subject.KEISEI_STATION, False, 365, 366),
        fragment("t", subject.TOEI_ASAKUSA, subject.TOEI_STATION, True, None, 366),
    ]
    assert subject.match_candidates([first], fragments)[0]["matchStatus"] == "matched-singleton"
    assert subject.match_candidates([second], fragments)[0]["matchStatus"] == "matched-singleton"


def main() -> int:
    test_extracts_both_directions()
    test_same_operator_neighbours_do_not_claim_boundary()
    test_exact_singleton_only()
    test_nearby_minute_never_matches()
    test_ambiguity_fails_closed()
    test_train_number_is_not_fragment_selector()
    print("keisei Oshiage official evidence tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
