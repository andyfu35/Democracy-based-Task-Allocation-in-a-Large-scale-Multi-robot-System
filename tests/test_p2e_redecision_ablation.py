"""P2E Proposed Method: matched single-round vs multi-round native ablation."""
from __future__ import annotations

from argparse import Namespace
import json
import tempfile
from pathlib import Path
import unittest

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import EmpiricalLatencyProfile
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_p2e_redecision_ablation import (
    LOSSES, MODES, validate_ablation_config, validate_ablation_grid,
    validate_paired_initial_epochs, run_one_ablation_case, summarize_ablation,
    prepare_ablation_evidence,
)
from experiments.p2e_redecision_plot import render_p2e_figure


def synthetic_profile() -> EmpiricalLatencyProfile:
    return EmpiricalLatencyProfile(
        source_repository="test/synthetic", source_commit="synthetic",
        source_blob_sha="synthetic", location="test", location_label="synthetic",
        config="test", config_label="synthetic", steady_start_s=0.0,
        steady_end_s=1.0, samples_ms=(5.0, 7.0, 9.0),
    )


def mock_record(loss, seed, mode, *, native=1, coverage=1.0, checksum="same"):
    # Minimal immutable method-case data for purely read-only audit tests.
    rounds = 1 if mode == "single_round" else 300
    return {
        "loss_percent": loss, "seed": seed, "mode": mode,
        "max_rounds": rounds, "method": "voting",
        "scene_sha256": f"scene-{seed}",
        "first_epoch_sha256": checksum,
        "native_success": native, "final_feasible": native,
        "native_stop_ms": 1000.0 if mode == "single_round" else 2500.0,
        "native_sender_sends": 403 if native else 230,
        "native_sender_bytes": 171648 if native else 109996,
        "rounds_executed": 1 if mode == "single_round" else 7,
        "task_coverage": coverage, "committed_task_count": round(coverage * 100),
        "quality_vs_full_info_greedy": 1.0 if native else "",
        **{f"{p}_sender_sends": x for p, x in (
            ("task", 3), ("cost", 100), ("vote", 100),
            ("score", 100 if native else 17), ("commit", 100 if native else 10)
        )},
        **{f"{p}_sender_bytes": x for p, x in (
            ("task", 3248), ("cost", 81600), ("vote", 81600 if native else 20000),
            ("score", 2400 if native else 4700),
            ("commit", 2800 if native else 448)
        )},
    }


class P2ERedecisionTests(unittest.TestCase):

    def test_frozen_two_modes_and_formal_loss_grid(self):
        self.assertEqual(MODES, ("single_round", "multi_round"))
        self.assertEqual(LOSSES, tuple(range(0, 91, 10)))
        args = Namespace(losses=",".join(f"{p/100:.2f}" for p in LOSSES),
                         seeds=100, first_seed=0, formal=True)
        self.assertEqual(validate_ablation_config(args), LOSSES)
        args.seeds = 99
        with self.assertRaises(ProtocolError) as caught:
            validate_ablation_config(args)
        self.assertEqual(caught.exception.diagnostic.category, "contract")

    def test_real_first_epoch_identical_across_limits_and_paid_sender_bytes(self):
        scene = generate_e0_scenario(0, 5, 5)
        small = run_one_ablation_case(
            scene, synthetic_profile(), p_loss=0.30, max_rounds=1,
        )
        large = run_one_ablation_case(
            scene, synthetic_profile(), p_loss=0.30, max_rounds=300,
        )
        self.assertEqual(small["first_epoch_sha256"], large["first_epoch_sha256"])
        self.assertEqual(small["cost_sender_sends"], 5)
        self.assertEqual(large["cost_sender_sends"], 5)
        self.assertEqual(small["rounds_executed"], 1)
        self.assertLessEqual(large["rounds_executed"], 300)
        for row in (small, large):
            self.assertEqual(row["native_sender_bytes"], sum(
                row[f"{phase}_sender_bytes"] for phase in
                ("task", "cost", "vote", "score", "commit")
            ))
            self.assertEqual(row["native_sender_sends"], sum(
                row[f"{phase}_sender_sends"] for phase in
                ("task", "cost", "vote", "score", "commit")
            ))
            self.assertGreater(row["native_sender_bytes"], 0)
            self.assertEqual(row["task_coverage"],
                             row["committed_task_count"] / 5)
            self.assertLessEqual(row["committed_task_count"], 5)

    def test_first_epoch_mismatch_is_rejected_even_with_same_seed(self):
        a = mock_record(30, 0, "single_round", checksum="first")
        b = mock_record(30, 0, "multi_round", checksum="changed")
        with self.assertRaises(ProtocolError) as caught:
            validate_paired_initial_epochs([a, b], (30,), 0, 1)
        self.assertEqual(caught.exception.diagnostic.code,
                         "P2E_FIRST_EPOCH_NOT_PAIRED")

    def test_missing_native_success_retains_coverage_and_blanks_quality(self):
        a = mock_record(90, 0, "single_round", native=0, coverage=0.1)
        b = mock_record(90, 0, "multi_round", native=1)
        validate_ablation_grid([a, b], (90,), 0, 1)
        validate_paired_initial_epochs([a, b], (90,), 0, 1)
        summary = summarize_ablation([a, b], (90,))
        single = next(r for r in summary if r["mode"] == "single_round")
        self.assertEqual(single["native_complete"], 0)
        self.assertEqual(single["quality_sample_count"], 0)
        self.assertEqual(single["mean_success_quality"], "")
        self.assertAlmostEqual(single["mean_task_coverage"], 0.1)
        self.assertEqual(single["mean_all_seed_sender_bytes"], a["native_sender_bytes"])

    def test_paired_grid_excludes_missing_and_duplicate_method(self):
        with self.assertRaises(ProtocolError):
            validate_ablation_grid([mock_record(0, 0, "single_round")],
                                   (0,), 0, 1)

    def test_figure_has_two_variants_and_no_invented_failed_quality(self):
        a = mock_record(90, 0, "single_round", native=0, coverage=0.1)
        b = mock_record(90, 0, "multi_round")
        data = summarize_ablation([a, b], (90,))
        svg = render_p2e_figure(data, (90,))
        self.assertIn("Proposed (Single-Round)", svg)
        self.assertIn("Proposed (Multi-Round)", svg)
        self.assertIn("n=0", svg)
        self.assertNotIn("Price Auction", svg)

    def test_resume_cannot_change_source_sha_or_pair_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            args = Namespace(output_root=Path(d) / "new",
                             resume=False, seeds=2, first_seed=0,
                             formal=False, rady_json=Path("profile.json"))
            prepare_ablation_evidence(args, "old-sha", (0,))
            args.resume = True
            with self.assertRaises(ProtocolError) as caught:
                prepare_ablation_evidence(args, "different-sha", (0,))
            self.assertEqual(caught.exception.diagnostic.code,
                             "P2E_RESUME_CONFIG_CHANGED")


if __name__ == "__main__":
    unittest.main()
