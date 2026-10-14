"""Four new native method curves + black dashed full-info reference."""
import unittest
from experiments.p2d_plot import render_p2d_figure


def sample():
    rows=[]
    for loss in (0,90):
        for method in ("voting","cbaa","cbba","centralized"):
            complete=0 if loss==90 and method=="centralized" else 100
            rows.append({
                "loss_percent":loss,"method":method,"trials":100,
                "native_complete":complete,"completion_rate":complete/100,
                "mean_all_seed_native_stop_ms":5000.0,
                "mean_all_seed_sender_bytes":10000.0,
                "quality_sample_count":complete,
                "mean_cost_over_full_info_greedy":(
                    1.0 if loss==0 else
                    ("" if not complete else 1.2)),
                "mean_task_coverage":0.5 if method=="centralized" else "",
            })
    return rows


class P2DPlotTests(unittest.TestCase):
    def test_plot_keeps_four_methods_and_offline_baseline(self):
        svg=render_p2d_figure(sample(),(0,90))
        for label in ("Proposed Method","CBAA","CBBA","Centralized Method",
                      "Full-Info Baseline"):
            self.assertIn(label,svg)
        self.assertNotIn("Price Auction",svg)
        self.assertIn('stroke="#000000"',svg)
        self.assertIn('stroke-dasharray=',svg)

    def test_missing_native_success_does_not_create_zero_quality(self):
        svg=render_p2d_figure(sample(),(0,90))
        self.assertIn("quality conditional on native success",svg)
        self.assertIn("n=0",svg)

    def test_invalid_grid_rejected(self):
        from democracy_mrta.diagnostics import ProtocolError
        with self.assertRaises(ProtocolError):
            render_p2d_figure(sample()[:-1],(0,90))


if __name__=="__main__":
    unittest.main()
