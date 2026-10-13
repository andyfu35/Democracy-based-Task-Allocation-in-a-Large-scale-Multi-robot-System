"""E9N presentation-only non-overlapping three-panel SVG regression."""
import re
import unittest

from experiments.plot_e9n_unified import LABELS, render_five_method_svg


class TestE9NPlotLayout(unittest.TestCase):
    def test_panel_titles_annotations_and_footnotes_are_separated(self):
        rows = [
            {"robots": n, "method": method,
             "mean_stop_s": float(n), "mean_sender_bytes": float(n * 100),
             "success_rate": "" if method in ("voting_e9i", "cbaa_e9j") else 1.0}
            for n in range(5, 101, 5) for method in LABELS
        ]
        svg = render_five_method_svg(rows)
        self.assertIn('viewBox="0 0 1240 1240"', svg)
        self.assertEqual(svg.count("E9I/J complete rates omitted"), 1)
        def locate(marker):
            match = re.search(r'<text[^>]*y="([0-9.]+)"[^>]*>' + re.escape(marker), svg)
            self.assertIsNotNone(match, marker)
            return float(match.group(1))
        captions = [float(value) for value in re.findall(
            r'<text x="620" y="([0-9.]+)"[^>]*>Robots = Tasks', svg)]
        self.assertEqual(len(captions), 3)
        self.assertGreater(locate("B. Attempted") - captions[0], 30)
        self.assertGreater(locate("C. Complete") - captions[1], 30)
        self.assertGreater(locate("E9I/J complete rates omitted") - captions[2], 20)
        self.assertGreater(locate("Not equal end guarantees") - locate("E9I/J complete rates omitted"), 30)
        self.assertLess(locate("Not equal end guarantees"), 1240)


if __name__ == "__main__":
    unittest.main()
