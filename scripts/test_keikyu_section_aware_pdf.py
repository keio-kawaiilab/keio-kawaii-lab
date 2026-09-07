#!/usr/bin/env python3
from __future__ import annotations

import unittest

from build_keikyu_official_stop_times import fragment_id
from keikyu_official_pdf import Word, detect_train_column_sections, time_cells


def w(text: str, x: float, y: float, width: float = 8.0, height: float = 5.0) -> Word:
    return Word(text=text, x_min=x, y_min=y, x_max=x + width, y_max=y + height)


def header(y: float, numbers: list[str]) -> list[Word]:
    words = [w('列車番号', 10, y, width=32)]
    for index, number in enumerate(numbers):
        words.append(w(number, 96 + index * 15.0, y))
    return words


def timed_rows(start_y: float, values: list[list[str]]) -> list[Word]:
    words: list[Word] = []
    for row_index, row in enumerate(values):
        y = start_y + row_index * 10.0
        for column, value in enumerate(row):
            words.append(w(value, 96 + column * 15.0, y))
    return words


class SectionAwarePdfTests(unittest.TestCase):
    def test_sparse_train_number_metadata_is_hard_boundary(self) -> None:
        words: list[Word] = []
        words += header(10, ['101A', '103A', '105A'])
        words += timed_rows(25, [
            ['500', '501', '502'],
            ['510', '511', '512'],
            ['520', '521', '522'],
        ])
        # This is not a timetable grid, but it must terminate section 0.
        words += [w('列車番号', 10, 60, width=32), w('999A', 96, 60)]
        words += header(80, ['201A', '203A', '205A'])
        words += timed_rows(95, [
            ['600', '601', '602'],
            ['610', '611', '612'],
            ['620', '621', '622'],
        ])

        sections = detect_train_column_sections(words)
        self.assertEqual(2, len(sections))
        self.assertEqual([0, 1], [section.section_index for section in sections])
        self.assertEqual([0, 2], [section.header_ordinal for section in sections])

        first_times = {cell.text for _column, cell in time_cells(list(sections[0].words), sections[0].grid)}
        second_times = {cell.text for _column, cell in time_cells(list(sections[1].words), sections[1].grid)}
        self.assertIn('500', first_times)
        self.assertIn('620', second_times)
        self.assertNotIn('600', first_times)
        self.assertNotIn('500', second_times)

    def test_fragment_id_contains_section_identity(self) -> None:
        self.assertEqual('keikyu-official-pdf:p067:s02:c04', fragment_id(67, 2, 4))

    def test_header_without_three_timed_rows_is_not_identity_section(self) -> None:
        words = header(10, ['101A', '103A', '105A'])
        words += timed_rows(25, [
            ['500', '501', '502'],
            ['510', '511', '512'],
        ])
        self.assertEqual([], detect_train_column_sections(words))


if __name__ == '__main__':
    unittest.main()
