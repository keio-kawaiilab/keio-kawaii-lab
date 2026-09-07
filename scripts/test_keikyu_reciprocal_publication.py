#!/usr/bin/env python3
import copy
import unittest
from types import SimpleNamespace

from audit_keikyu_reciprocal_publication import resolve_links, extract_section_reference_rows
from audit_sengakuji_published_sequences import (
    sequence_matches, ordered_toei_score, verify_metadata_matches_stops, keikyu_fingerprint, classify_boundary,
)
from keikyu_official_pdf import Word


def reference_pair():
    common = dict(calendar="weekday", section=0, column=0, printedTrainNumber="403T",
                  previousRowY=None, nextRowY=None, previousRowCount=0, nextRowCount=0)
    source = dict(common, id="keikyu-official-pdf:p037:s00:c00", page=37,
                  printedPage=32, previousPrintedPage=None, nextPrintedPage=62,
                  nextRowY=705, nextRowCount=1)
    target = dict(common, id="keikyu-official-pdf:p067:s00:c00", page=67,
                  printedPage=62, previousPrintedPage=32, nextPrintedPage=None,
                  previousRowY=443, previousRowCount=1)
    return [source, target]


class ReciprocalPublicationTest(unittest.TestCase):
    def test_both_printed_page_references_and_number_identify_one_pair(self):
        links, results = resolve_links(reference_pair())
        self.assertEqual(len(links), 1)
        self.assertEqual(results[0]["status"], "reciprocal-publication-candidate")
        self.assertEqual(links[0]["sourceNextPrintedPage"], links[0]["targetPrintedPage"])
        self.assertEqual(links[0]["targetPreviousPrintedPage"], links[0]["sourcePrintedPage"])

    def test_one_way_reference_with_same_number_and_time_is_not_enough(self):
        rows = reference_pair()
        rows[0]["nextPrintedPage"] = None
        for row in rows:
            row["boundaryMinute"] = 299
        self.assertEqual(resolve_links(rows)[0], [])

    def test_wrong_reciprocal_page_is_not_enough(self):
        rows = reference_pair()
        rows[0]["nextPrintedPage"] = 63
        self.assertEqual(resolve_links(rows)[0], [])

    def test_wrong_or_unknown_calendar_rejected(self):
        for value in ("holiday", "unknown", None):
            rows = reference_pair()
            rows[1]["calendar"] = value
            with self.subTest(calendar=value):
                self.assertEqual(resolve_links(rows)[0], [])

    def test_absent_or_different_number_is_not_guessed(self):
        for value in (None, "405T"):
            rows = reference_pair()
            rows[1]["printedTrainNumber"] = value
            with self.subTest(number=value):
                self.assertEqual(resolve_links(rows)[0], [])

    def test_same_number_in_two_sections_is_ambiguous(self):
        rows = reference_pair()
        rows.append(dict(rows[0], id="keikyu-official-pdf:p037:s01:c00", section=1))
        self.assertEqual(resolve_links(rows)[0], [])

    def test_same_printed_page_on_two_pdf_pages_is_ambiguous(self):
        rows = reference_pair()
        rows.append(dict(rows[0], id="keikyu-official-pdf:p038:s00:c00", page=38, printedTrainNumber="405T"))
        self.assertEqual(resolve_links(rows)[0], [])

    def test_duplicate_local_ids_fail_closed(self):
        rows = reference_pair()
        with self.assertRaises(RuntimeError):
            resolve_links(rows + [copy.deepcopy(rows[0])])

    def test_two_targets_from_one_source_are_not_selected_arbitrarily(self):
        rows = reference_pair()
        rows.append(dict(rows[1], id="keikyu-official-pdf:p067:s01:c00", section=1))
        links, results = resolve_links(rows)
        self.assertEqual(links, [])
        self.assertTrue(all(r["status"] == "conflicting-reciprocal-columns" for r in results))

    def test_reciprocal_cycle_rejected(self):
        rows = reference_pair()
        rows[0].update(previousPrintedPage=62, previousRowY=400)
        rows[1].update(nextPrintedPage=32, nextRowY=700)
        links, results = resolve_links(rows)
        self.assertEqual(links, [])
        self.assertTrue(all(r["status"] == "cyclic-publication-reference" for r in results))

    def test_in_section_previous_row_does_not_leak_across_panels(self):
        def word(text, x, y):
            return Word(text, x-4, y-2, x+4, y+2)
        def row(label, number, y):
            return [word(label, 40, y), word(str(number), 100, y)]
        sections = [SimpleNamespace(section_index=0, grid=SimpleNamespace(header_y=60, centers=(100,), pitch=15), y_max=100),
                    SimpleNamespace(section_index=1, grid=SimpleNamespace(header_y=200, centers=(100,), pitch=15), y_max=300)]
        words = row("前の掲載ページ", 99, 20) + row("前の掲載ページ", 32, 80)
        words += row("次の掲載ページ", 62, 150) + row("前の掲載ページ", 33, 220) + row("次の掲載ページ", 63, 350)
        result = extract_section_reference_rows(words, sections)
        self.assertEqual(result[0]["previousPages"], [32])
        self.assertEqual(result[0]["nextPages"], [62])
        self.assertEqual(result[1]["previousPages"], [33])
        self.assertEqual(result[1]["nextPages"], [63])

    def test_metadata_cannot_change_calendar_or_drop_column(self):
        rows = reference_pair()
        stops = {"fragments": copy.deepcopy(rows)}
        verify_metadata_matches_stops({"metadata": rows}, stops)
        rows[0]["calendar"] = "holiday"
        with self.assertRaises(RuntimeError):
            verify_metadata_matches_stops({"metadata": rows}, stops)
        with self.assertRaises(RuntimeError):
            verify_metadata_matches_stops({"metadata": rows[:1]}, stops)


class BoundaryClassificationTest(unittest.TestCase):
    def classify(self, marker="↓", branch="...", direction="keikyu-to-toei", branch_row=True):
        def word(text, x, y):
            return dict(text=text, x0=x-2, x1=x+2, top=y-1, bottom=y+1)
        cache = dict(words=[word(marker, 200, 110)], rows=[])
        if branch_row:
            cache["rows"].append(dict(text="西馬込発", y=120))
            cache["words"].append(word(branch, 200, 120))
        candidate = dict(columnX=200, direction=direction,
                         rowGeometry=dict(sourceBoundaryY=100, boundaryTrainNumberY=110, targetBoundaryY=130))
        return classify_boundary(cache, candidate)["status"]

    def test_explicit_arrow_and_no_branch_train(self):
        self.assertEqual(self.classify(), "official-continuation-arrow")

    def test_number_plus_nishimagome_train_is_transfer_even_at_same_minute(self):
        self.assertEqual(self.classify("931N", "929"), "official-transfer-via-nishimagome")

    def test_arrow_conflicting_with_branch_train_rejected(self):
        self.assertEqual(self.classify("↓", "929"), "unresolved-boundary-marker")

    def test_blank_marker_is_not_continuation(self):
        self.assertEqual(self.classify(""), "unresolved-boundary-marker")

    def test_missing_branch_row_cannot_prove_northbound_continuation(self):
        self.assertEqual(self.classify(branch_row=False), "unresolved-boundary-marker")

    def test_printed_train_number_alone_is_not_transfer_proof(self):
        self.assertEqual(self.classify("931N"), "unresolved-boundary-marker")

    def test_unreadable_or_missing_branch_cell_is_not_blank_proof(self):
        for value in ("", "?", "(cid:4)", "bad-text"):
            self.assertEqual(self.classify(branch=value), "unresolved-boundary-marker")

    def test_southbound_arrow_requires_empty_branch_cell_not_missing_row(self):
        self.assertEqual(self.classify(direction="toei-to-keikyu"), "official-continuation-arrow")
        self.assertEqual(self.classify(direction="toei-to-keikyu", branch_row=False), "unresolved-boundary-marker")
        self.assertEqual(self.classify(direction="toei-to-keikyu", branch="929"), "unresolved-boundary-marker")


class PublishedSequenceTest(unittest.TestCase):
    def setUp(self):
        self.fp = [dict(station="品川", minute=297), dict(station="泉岳寺", minute=299)]
        self.fragment = dict(stopTimes=[dict(station="品川", time="457"), dict(station="泉岳寺", time="459")])

    def test_exact_station_sequence_matches(self):
        self.assertTrue(sequence_matches(self.fp, self.fragment))

    def test_one_station_cannot_identify_local_train(self):
        self.assertFalse(sequence_matches(self.fp[:1], self.fragment))

    def test_nearby_time_is_not_exact(self):
        self.fragment["stopTimes"][0]["time"] = "458"
        self.assertFalse(sequence_matches(self.fp, self.fragment))

    def test_matching_times_in_reverse_station_order_rejected(self):
        self.fragment["stopTimes"].reverse()
        self.assertFalse(sequence_matches(self.fp, self.fragment))

    def test_missing_published_station_rejected(self):
        self.fp.insert(0, dict(station="羽田空港第３ターミナル", minute=275))
        self.assertFalse(sequence_matches(self.fp, self.fragment))

    def test_toei_points_require_printed_order(self):
        fp = [dict(station="泉岳寺", minute=300), dict(station="三田", minute=302), dict(station="大門", minute=304)]
        trip = dict(stops={"Sengakuji": (None, 300), "Mita": (None, 302), "Daimon": (None, 304)})
        self.assertTrue(ordered_toei_score(fp, trip)["printedOrderMatches"])
        result = ordered_toei_score(list(reversed(fp)), trip)
        self.assertTrue(result["allMatched"])
        self.assertFalse(result["printedOrderMatches"])

    def test_keikyu_fingerprint_stops_at_boundary_number_row(self):
        def word(text, x, y):
            return dict(text=text, x0=x-4, x1=x+4, top=y-2, bottom=y+2)
        words = [word("列車番号", 40, 20), word("列車番号", 40, 110), word("列車番号", 40, 200)]
        for label, value, y in (("品川発", "457", 80), ("泉岳寺着", "459", 100), ("泉岳寺〃", "500", 120)):
            words.extend([word(label, 40, y), word(value, 200, y)])
        c = dict(direction="keikyu-to-toei", columnX=200,
                 rowGeometry=dict(sourceBoundaryY=100, targetBoundaryY=120))
        fp = keikyu_fingerprint(words, c)
        self.assertEqual([(p["station"], p["minute"]) for p in fp], [("品川", 297), ("泉岳寺", 299)])


if __name__ == "__main__":
    unittest.main()
