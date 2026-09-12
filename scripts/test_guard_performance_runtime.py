import unittest
from pathlib import Path
from guard_performance_runtime import transform
from fix_missing_application_start_ui import patch_page


class RuntimeGuardTests(unittest.TestCase):
    def test_guard_is_idempotent(self):
        page = Path('schedule.html').read_text(encoding='utf-8')
        self.assertEqual(transform(page), transform(transform(page)))

    def test_unknown_runtime_shape_fails_closed(self):
        with self.assertRaises(RuntimeError):
            transform('<html>unknown runtime</html>')

    def test_static_ticket_rewrite_preserves_dynamic_state(self):
        page = Path('schedule.html').read_text(encoding='utf-8')
        once = patch_page(page)
        twice = patch_page(once)
        self.assertEqual(once, twice)
        offer = twice.split('function offerHtml(o){', 1)[1].split('function detailList', 1)[0]
        self.assertIn("'+state+'</span>", offer)
        self.assertNotIn('class="sale-state">開始日時未取得', offer)


if __name__ == '__main__':
    unittest.main()
