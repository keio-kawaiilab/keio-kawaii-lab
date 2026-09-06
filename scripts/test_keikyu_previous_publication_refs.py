#!/usr/bin/env python3
from __future__ import annotations

import unittest

from audit_keikyu_previous_publication_refs import (
    detect_printed_page_number,
    extract_previous_publication_refs,
)
from keikyu_official_pdf import TrainColumnGrid, Word


def word(text: str, x: float, y: float, width: float = 8.0, height: float = 8.0) -> Word:
    return Word(
        text=text,
        x_min=x - width / 2,
        y_min=y - height / 2,
        x_max=x + width / 2,
        y_max=y + height / 2,
    )


class KeikyuPreviousPublicationRefsTest(unittest.TestCase):
    def grid(self) -> TrainColumnGrid:
        return TrainColumnGrid(
            header_y=60.0,
            centers=(100.0, 115.0, 130.0),
            pitch=15.0,
            explicit_numbers=("720C", "870C", "820D"),
        )

    def header_words(self):
        return [
            word("列車番号", 40.0, 20.0, width=30.0),
            word("650K", 100.0, 20.0),
            word("724H", 115.0, 20.0),
            word("前の掲載ページ", 40.0, 35.0, width=55.0),
            word("63", 100.0, 35.0),
            word("63", 115.0, 35.0),
            word("列車番号", 40.0, 60.0, width=30.0),
            word("720C", 100.0, 60.0),
            word("870C", 115.0, 60.0),
            word("820D", 130.0, 60.0),
        ]

    def test_extracts_previous_page_and_train_number_by_current_column(self):
        refs = extract_previous_publication_refs(self.header_words(), self.grid())
        self.assertEqual(
            refs,
            [
                {"previousPrintedPage": 63, "previousTrainNumber": "650K"},
                {"previousPrintedPage": 63, "previousTrainNumber": "724H"},
                {"previousPrintedPage": None, "previousTrainNumber": None},
            ],
        )

    def test_partial_reference_is_preserved_not_inferred(self):
        words = self.header_words()
        words = [item for item in words if not (item.text == "724H" and item.y == 20.0)]
        refs = extract_previous_publication_refs(words, self.grid())
        self.assertEqual(refs[1]["previousPrintedPage"], 63)
        self.assertIsNone(refs[1]["previousTrainNumber"])

    def test_no_previous_header_returns_explicit_empty_metadata(self):
        words = [
            word("列車番号", 40.0, 60.0, width=30.0),
            word("720C", 100.0, 60.0),
            word("870C", 115.0, 60.0),
            word("820D", 130.0, 60.0),
        ]
        refs = extract_previous_publication_refs(words, self.grid())
        self.assertEqual(
            refs,
            [
                {"previousPrintedPage": None, "previousTrainNumber": None},
                {"previousPrintedPage": None, "previousTrainNumber": None},
                {"previousPrintedPage": None, "previousTrainNumber": None},
            ],
        )

    def test_conflicting_values_in_one_column_fail_closed(self):
        words = self.header_words() + [word("651K", 101.0, 20.0)]
        with self.assertRaises(RuntimeError):
            extract_previous_publication_refs(words, self.grid())

    def test_printed_page_number_can_be_on_left_outer_edge(self):
        words = [word("7", 30.0, 970.0)]
        self.assertEqual(detect_printed_page_number(1000.0, 1000.0, words), 7)

    def test_printed_page_number_can_be_on_right_outer_edge(self):
        words = [word("8", 970.0, 970.0)]
        self.assertEqual(detect_printed_page_number(1000.0, 1000.0, words), 8)

    def test_special_connection_page_uses_extreme_outer_gutter(self):
        words = [word("62", 50.0, 910.0)]
        self.assertEqual(detect_printed_page_number(1000.0, 1000.0, words), 62)

    def test_table_side_integer_does_not_hide_outer_gutter_page_number(self):
        words = [word("62", 50.0, 910.0), word("51", 100.0, 970.0)]
        self.assertEqual(detect_printed_page_number(1000.0, 1000.0, words), 62)

    def test_footer_detector_does_not_accept_interior_number(self):
        words = [word("62", 500.0, 910.0)]
        self.assertIsNone(detect_printed_page_number(1000.0, 1000.0, words))

    def test_ambiguous_bottom_edge_page_numbers_fail_closed(self):
        words = [word("7", 30.0, 970.0), word("63", 970.0, 970.0)]
        self.assertIsNone(detect_printed_page_number(1000.0, 1000.0, words))

    def test_ambiguous_outer_gutter_candidates_fail_closed(self):
        words = [word("62", 50.0, 910.0), word("63", 950.0, 910.0)]
        self.assertIsNone(detect_printed_page_number(1000.0, 1000.0, words))


if __name__ == "__main__":
    unittest.main()
