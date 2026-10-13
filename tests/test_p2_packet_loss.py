"""P2 validation: exact grid, guards, missing values, and figure source."""
from __future__ import annotations
from argparse import Namespace
import unittest

from democracy_mrta.diagnostics import ProtocolError
from experiments.run_p2_packet_loss import LOSSES, METHODS, validate_config, summarize, validate_complete_grid
from experiments.p2_packet_loss_plot import render_p2_figure


def case(p, seed, method):
    good = not (p == 90 and method == "price_auction" and seed >= 75)
    return {
        "loss_percent": p, "seed": seed, "method": method,
        "robots": 100, "tasks": 100, "capacity": 1,
        "p_loss": p / 100, "scene_sha256": f"seed-{seed}",
        "native_success": int(good), "final_feasible": int(good),
        "first_feasible_seen": int(good), "native_guard_censored": int(not good),
        "native_diagnostic": "", "native_stop_ms": 1000,
        "native_sender_bytes": 300, "final_hungarian_ratio": 1.2 if good else "",
        "method_contract": "native"}


class P2ContractTests(unittest.TestCase):
    def test_formal_grid_frozen(self):
        args = Namespace(losses=",".join(f"{p/100:.2f}" for p in LOSSES),
                         seeds=100, first_seed=0, formal=True,
                         voting_strategy="greedy_batch")
        self.assertEqual(LOSSES, (0, 10, 20, 30, 40, 50, 60, 70, 80, 90))
        self.assertEqual(validate_config(args), LOSSES)
        self.assertEqual(len(LOSSES) * len(METHODS) * args.seeds, 4000)
        args.voting_strategy = "greedy_task"
        with self.assertRaises(ProtocolError):
            validate_config(args)
        args.voting_strategy = "greedy_batch"
        args.losses = "0.00,0.30"
        with self.assertRaises(ProtocolError):
            validate_config(args)
        args.formal = False
        args.losses = "0.00,0.05,0.10"
        with self.assertRaises(ProtocolError):
            validate_config(args)
        args.losses = "0.00,0.30,0.90"
        self.assertEqual(validate_config(args), (0, 30, 90))

    def test_guards_included_and_cost_uses_same_success_cohort(self):
        losses = (0, 90)
        rows = [case(p, seed, method) for p in losses for seed in range(100)
                for method in METHODS]
        validate_complete_grid(rows, losses, 0, 100)
        summary = summarize(rows, losses)
        auction = next(r for r in summary if r["loss_percent"] == 90
                       and r["method"] == "price_auction")
        voting = next(r for r in summary if r["loss_percent"] == 90
                      and r["method"] == "voting")
        self.assertEqual(auction["native_complete"], 75)
        self.assertEqual(auction["guard_censored"], 25)
        self.assertEqual(voting["same_four_success_seeds"], 75)
        self.assertEqual(auction["completion_rate"], .75)
        figure = render_p2_figure(summary, losses)
        self.assertIn("Packet-loss robustness", figure)
        self.assertIn("Batched Greedy", figure)
        self.assertNotIn("Original Voting", figure)
        self.assertIn("stroke-dasharray", figure)
        self.assertIn("concentric markers", figure)
        with self.assertRaises(ProtocolError):
            validate_complete_grid(rows[1:], losses, 0, 100)

    def test_missing_sender_accounting_not_zero(self):
        rows = [case(30, seed, method) for seed in range(100) for method in METHODS]
        rows[0]["native_stop_ms"] = ""
        rows[0]["native_sender_bytes"] = ""
        voting = next(r for r in summarize(rows, (30,)) if r["method"] == "voting")
        self.assertEqual(voting["native_stop_record_count"], 99)
        self.assertEqual(voting["sender_bytes_record_count"], 99)
        self.assertEqual(voting["mean_all_seed_native_stop_ms"], "")
        self.assertEqual(voting["mean_all_seed_sender_bytes"], "")


if __name__ == "__main__":
    unittest.main()
