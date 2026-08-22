import unittest

import update_live_events_deep as deep


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, timeout=20):
        self.calls.append(url)
        page = int(url.split("page=")[-1])
        return FakeResponse(self.pages.get(page, "<html></html>"))


class DeepDiscoveryTests(unittest.TestCase):
    def test_keeps_scanning_past_page_without_ticket_candidates(self):
        pages = {
            1: '<a href="/news/detail/1">普通のお知らせ</a>',
            2: '<a href="/news/detail/2">イベント写真公開</a>',
            3: '<a href="/news/detail/3">2027 LIVE FC先行受付開始</a>',
            4: '<html></html>',
        }
        session = FakeSession(pages)
        candidates, scanned = deep.candidate_links_deep(
            session,
            "FRUITS ZIPPER",
            "https://example.test",
            max_pages=10,
        )
        self.assertEqual(scanned, 3)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://example.test/news/detail/3")

    def test_ignores_merchandise_even_if_title_contains_ticket_hint(self):
        pages = {
            1: '<a href="/news/detail/1">ライブ会場 グッズ受付のお知らせ</a>',
            2: '<html></html>',
        }
        session = FakeSession(pages)
        candidates, _ = deep.candidate_links_deep(
            session,
            "CANDY TUNE",
            "https://example.test",
            max_pages=5,
        )
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
