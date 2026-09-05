#!/usr/bin/env python3
from __future__ import annotations

import copy

import keisei_official_oshiage_evidence as subject

YOTSU = "odpt.Station:Keisei.Oshiage.Yotsugi"
HONJO = "odpt.Station:Toei.Asakusa.HonjoAzumabashi"


def station_maps() -> tuple[dict[str, str], dict[str, str]]:
    return (
        {"四ツ木": YOTSU, "押上": subject.KEISEI_STATION, "青砥": "odpt.Station:Keisei.Main.Aoto"},
        {"本所吾妻橋": HONJO, "押上": subject.TOEI_STATION},
    )


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


def candidate(direction: str = "keisei-to-toei") -> dict:
    keisei, toei = station_maps()
    return subject.extract_candidates({"trains": [fake_train(direction)]}, keisei, toei)[0][0]


def fragment(fid: str, railway: str, stops: list[list]) -> dict:
    return {"id": fid, "railway": railway, "calendar": "weekday", "stops": stops}


def keisei_source(fid: str, anchor_minute: int = 360) -> dict:
    return fragment(fid, subject.KEISEI_OSHIAGE, [[YOTSU, anchor_minute, anchor_minute], [subject.KEISEI_STATION, 365, 366]])


def toei_target(fid: str, anchor_minute: int = 368) -> dict:
    return fragment(fid, subject.TOEI_ASAKUSA, [[subject.TOEI_STATION, None, 366], [HONJO, anchor_minute, anchor_minute]])


def test_extracts_both_directions() -> None:
    keisei, toei = station_maps()
    candidates, diagnostics = subject.extract_candidates(
        {"trains": [fake_train("keisei-to-toei"), fake_train("toei-to-keisei")]}, keisei, toei
    )
    assert diagnostics["reasons"] == {}
    assert {row["direction"] for row in candidates} == {"keisei-to-toei", "toei-to-keisei"}
    assert all(subject.MARKER in row["evidence"] for row in candidates)
    assert candidates[0]["sourceAdjacentAnchor"]["station"]
    assert candidates[0]["targetAdjacentAnchor"]["station"]


def test_same_operator_neighbours_do_not_claim_boundary() -> None:
    keisei, toei = station_maps()
    train = fake_train()
    train["stops"][2]["station"] = "青砥"
    candidates, diagnostics = subject.extract_candidates({"trains": [train]}, keisei, toei)
    assert candidates == []
    assert diagnostics["reasons"].get("cannot-classify-boundary-neighbours") == 1


def test_exact_singleton_only() -> None:
    matched = subject.match_candidates([candidate()], [keisei_source("k"), toei_target("t")])[0]
    assert matched["matchStatus"] == "matched-singleton"
    assert matched["fromFragment"] == "k"
    assert matched["toFragment"] == "t"
    assert matched["resolvedByAdjacentOfficialAnchor"] is False


def test_boundary_ambiguity_resolves_with_exact_adjacent_anchor() -> None:
    fragments = [keisei_source("right", 360), keisei_source("wrong", 359), toei_target("t")]
    matched = subject.match_candidates([candidate()], fragments)[0]
    assert len(matched["boundarySourceMatches"]) == 2
    assert matched["sourceMatches"] == ["right"]
    assert matched["sourceMatchMethod"] == "resolved-by-adjacent-official-anchor"
    assert matched["matchStatus"] == "matched-singleton"
    assert matched["resolvedByAdjacentOfficialAnchor"] is True


def test_wrong_adjacent_minute_does_not_resolve() -> None:
    fragments = [keisei_source("a", 359), keisei_source("b", 358), toei_target("t")]
    matched = subject.match_candidates([candidate()], fragments)[0]
    assert matched["matchStatus"] == "ambiguous"
    assert matched["sourceMatchMethod"] == "adjacent-anchor-no-exact-match"
    assert len(matched["sourceMatches"]) == 2


def test_nearby_adjacent_minute_is_not_accepted() -> None:
    fragments = [keisei_source("near", 361), keisei_source("far", 358), toei_target("t")]
    matched = subject.match_candidates([candidate()], fragments)[0]
    assert matched["matchStatus"] == "ambiguous"
    assert matched["sourceMatchMethod"] == "adjacent-anchor-no-exact-match"


def test_adjacent_anchor_that_still_matches_two_fails_closed() -> None:
    fragments = [keisei_source("a", 360), keisei_source("b", 360), toei_target("t")]
    matched = subject.match_candidates([candidate()], fragments)[0]
    assert matched["matchStatus"] == "ambiguous"
    assert matched["sourceMatchMethod"] == "still-ambiguous-after-adjacent-anchor"
    assert matched["fromFragment"] is None


def test_nearby_boundary_minute_never_matches() -> None:
    k = fragment("k", subject.KEISEI_OSHIAGE, [[YOTSU, 360, 360], [subject.KEISEI_STATION, 364, 364]])
    t = fragment("t", subject.TOEI_ASAKUSA, [[subject.TOEI_STATION, None, 367], [HONJO, 368, 368]])
    matched = subject.match_candidates([candidate()], [k, t])[0]
    assert matched["matchStatus"] == "unmatched"
    assert matched["sourceMatches"] == []
    assert matched["targetMatches"] == []


def test_train_number_is_not_fragment_selector() -> None:
    first = candidate()
    changed_train = copy.deepcopy(fake_train())
    changed_train["sourceTrainId"] = "completely-different-number"
    keisei, toei = station_maps()
    second = subject.extract_candidates({"trains": [changed_train]}, keisei, toei)[0][0]
    fragments = [keisei_source("k"), toei_target("t")]
    assert subject.match_candidates([first], fragments)[0]["matchStatus"] == "matched-singleton"
    assert subject.match_candidates([second], fragments)[0]["matchStatus"] == "matched-singleton"


def main() -> int:
    test_extracts_both_directions()
    test_same_operator_neighbours_do_not_claim_boundary()
    test_exact_singleton_only()
    test_boundary_ambiguity_resolves_with_exact_adjacent_anchor()
    test_wrong_adjacent_minute_does_not_resolve()
    test_nearby_adjacent_minute_is_not_accepted()
    test_adjacent_anchor_that_still_matches_two_fails_closed()
    test_nearby_boundary_minute_never_matches()
    test_train_number_is_not_fragment_selector()
    print("keisei Oshiage official evidence tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
