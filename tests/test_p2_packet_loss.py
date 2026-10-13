"""P2 validation: exact grid, guards, missing values, and figure source."""
from __future__ import annotations
from argparse import Namespace, SimpleNamespace
import json
import tempfile
from pathlib import Path
import unittest

from democracy_mrta.diagnostics import ProtocolError
from experiments.run_p2_packet_loss import LOSSES, METHODS, validate_config, summarize, validate_complete_grid, prepare_evidence, validate_batched_voting_evidence, keys
from experiments.p2_packet_loss_plot import render_p2_figure
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.optimizer import solve_visible_batched_greedy_assignment
from democracy_mrta.task_information import encode_task_announcement


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
                         voting_strategy="greedy_batch",
                         baseline_zip=Path("/original/verified-p2.zip"))
        self.assertEqual(LOSSES, (0, 10, 20, 30, 40, 50, 60, 70, 80, 90))
        self.assertEqual(validate_config(args), LOSSES)
        self.assertEqual(len(LOSSES) * 1 * args.seeds, 1000)
        self.assertEqual(len(keys(LOSSES, 0, 100)), 1000)
        self.assertEqual({method for _p, _seed, method in keys(LOSSES, 0, 100)}, {"voting"})
        self.assertEqual(len(LOSSES) * len(METHODS) * args.seeds, 4000)
        args.baseline_zip = None
        with self.assertRaises(ProtocolError) as cm:
            validate_config(args)
        self.assertEqual(cm.exception.diagnostic.code, "P2_REUSE_BASELINE_ZIP_REQUIRED")
        args.baseline_zip = Path("/original/verified-p2.zip")
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
        validate_complete_grid(rows, losses, 0, 100, methods=METHODS)
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
            validate_complete_grid(rows[1:], losses, 0, 100, methods=METHODS)

    def test_old_sequential_source_cannot_resume_batched_formal(self):
        with tempfile.TemporaryDirectory() as root:
            args = Namespace(
                output_root=Path(root) / "study", resume=False,
                losses="0.00", first_seed=0, seeds=2, formal=False,
                voting_strategy="greedy_batch", rady_json=Path("profile.json"),
            )
            prepare_evidence(args, "new-batched-git-sha", (0,))
            config = args.output_root / "run_config_p2.json"
            stored = json.loads(config.read_text(encoding="utf-8"))
            stored["voting_strategy"] = "greedy_task"
            config.write_text(json.dumps(stored), encoding="utf-8")
            args.resume = True
            with self.assertRaises(ProtocolError) as cm:
                prepare_evidence(args, "new-batched-git-sha", (0,))
            self.assertEqual(cm.exception.diagnostic.code, "P2_RESUME_CONFIG_MISMATCH")

    def test_per_seed_native_batch_task_cost_and_zero_loss_greedy_gate(self):
        scene = generate_e0_scenario(0, 2, 2)
        optimum_greedy = solve_visible_batched_greedy_assignment(
            scene.cost_matrix, frozenset(range(scene.num_robots)))
        evidence = {
            "task_announcement_sender_frames": len(encode_task_announcement(scene.task_positions)),
            "cost_sender_frames": 2, "vote_sender_frames": 2,
            "score_sender_frames": 2, "commit_sender_frames": 2,
            "phase_timing": {
                "task_ms": 1.0, "cost_once_ms": 2.0,
                "vote_and_score_ms": 3.0, "commit_ms": 4.0,
                "total_ms": 10.0, "epochs": 1,
            },
        }
        row = {
            "method": "voting", "loss_percent": 0,
            "native_diagnostic": "",
            "native_success": 1, "native_stop_ms": 10.0,
            "native_assignment_json": json.dumps(optimum_greedy.assigned_pairs),
            "original_traffic_ledger_json": json.dumps({"batch": evidence}),
        }
        validate_batched_voting_evidence(scene, row)
        evidence["cost_sender_frames"] = 4
        row["original_traffic_ledger_json"] = json.dumps({"batch": evidence})
        with self.assertRaises(ProtocolError) as cm:
            validate_batched_voting_evidence(scene, row)
        self.assertEqual(cm.exception.diagnostic.code, "P2_BATCH_ONE_TIME_PHASE_CONTRACT")
        evidence["cost_sender_frames"] = 2
        evidence["phase_timing"]["epochs"] = 2
        row["original_traffic_ledger_json"] = json.dumps({"batch": evidence})
        with self.assertRaises(ProtocolError) as cm:
            validate_batched_voting_evidence(scene, row)
        self.assertEqual(cm.exception.diagnostic.code, "P2_BATCH_NO_LOSS_REQUIRES_ONE_EPOCH")

    def test_zero_loss_rejects_historical_task_id_greedy_pairing(self):
        scene = SimpleNamespace(
            num_robots=2, num_tasks=2,
            task_positions=((0.0, 0.0), (1.0, 1.0)),
            cost_matrix=((2.0, 1.0), (3.0, 100.0)),
        )
        frame_count = len(encode_task_announcement(scene.task_positions))
        batch = {
            "task_announcement_sender_frames": frame_count,
            "cost_sender_frames": 2, "commit_sender_frames": 2,
            "phase_timing": {
                "task_ms": 1.0, "cost_once_ms": 1.0,
                "vote_and_score_ms": 1.0, "commit_ms": 1.0,
                "epochs": 1,
            },
        }
        old_task_first = ((0, 0), (1, 1))
        row = {
            "method": "voting", "loss_percent": 0,
            "native_diagnostic": "", "native_success": 1,
            "native_stop_ms": 4.0,
            "native_assignment_json": json.dumps(old_task_first),
            "original_traffic_ledger_json": json.dumps({"batch": batch}),
        }
        with self.assertRaises(ProtocolError) as cm:
            validate_batched_voting_evidence(scene, row)
        self.assertEqual(
            cm.exception.diagnostic.code, "P2_GLOBAL_GREEDY_NO_LOSS_MISMATCH"
        )
        # The same real stage-count and time evidence should admit the GLOBAL plan.
        row["native_assignment_json"] = json.dumps(((1, 0), (0, 1)))
        validate_batched_voting_evidence(scene, row)

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
