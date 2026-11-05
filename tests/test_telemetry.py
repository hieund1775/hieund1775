"""Unit tests for public telemetry normalization and SVG rendering."""
from datetime import date
from pathlib import Path
import sys
import unittest
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from generate_telemetry import count_streaks, language_rows, render_svg  # noqa: E402


class TelemetryTests(unittest.TestCase):
    def test_current_streak_counts_yesterday(self):
        days = {'2026-11-02': 1, '2026-11-03': 3, '2026-11-04': 2, '2026-11-05': 0}
        self.assertEqual(count_streaks(days, date(2026, 11, 5)), (3, 3))

    def test_current_streak_resets_after_two_inactive_days(self):
        days = {'2026-11-02': 1, '2026-11-03': 0, '2026-11-04': 0}
        self.assertEqual(count_streaks(days, date(2026, 11, 5)), (0, 1))

    def test_streak_today_counts(self):
        days = {'2026-11-04': 1, '2026-11-05': 1}
        self.assertEqual(count_streaks(days, date(2026, 11, 5)), (2, 2))

    def test_language_aggregation_is_bytes(self):
        rows = language_rows({'JavaScript': 600, 'TypeScript': 300, 'HTML': 100})
        self.assertEqual(rows[0], ('JavaScript', 60.0))
        self.assertEqual(rows[1], ('TypeScript', 30.0))

    def test_no_fabricated_data_if_languages_missing(self):
        self.assertEqual(language_rows({}), [])

    def test_svgs_valid_for_both_themes(self):
        data = {'username':'hieund1775','as_of':'2026-11-05', 'contributions':722,
                'current_streak':10, 'longest_streak':24,'commits':578,
                'pull_requests':29,'issues':0,'reviews':0,'stars':1,
                'languages':{'JavaScript':6024,'TypeScript':3031,'C#':722,'Other':123}}
        for theme in ('dark', 'light'):
            with self.subTest(theme=theme):
                svg = render_svg(data, theme, demo=False)
                ElementTree.fromstring(svg)
                self.assertIn('722', svg)
                self.assertIn('JavaScript', svg)
                self.assertNotIn('PREVIEW DATA', svg)


if __name__ == '__main__':
    unittest.main()
